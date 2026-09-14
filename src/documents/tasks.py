import datetime
import logging
import shutil
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from tempfile import mkstemp

from celery import Task
from celery import shared_task
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db import transaction
from django.db.models.signals import post_save
from django.utils import timezone
from filelock import FileLock

from documents import sanity_checker
from documents.barcodes import BarcodePlugin
from documents.bulk_download import ArchiveOnlyStrategy
from documents.bulk_download import OriginalsOnlyStrategy
from documents.caching import clear_document_caches
from documents.classifier import DocumentClassifier
from documents.classifier import load_classifier
from documents.consumer import AsnCheckPlugin
from documents.consumer import ConsumeFileDuplicateError
from documents.consumer import ConsumerPlugin
from documents.consumer import ConsumerPreflightPlugin
from documents.consumer import WorkflowTriggerPlugin
from documents.consumer import should_produce_archive
from documents.data_models import ConsumableDocument
from documents.data_models import ConsumeFileDuplicateResult
from documents.data_models import ConsumeFileStoppedResult
from documents.data_models import ConsumeFileSuccessResult
from documents.data_models import DocumentMetadataOverrides
from documents.double_sided import CollatePlugin
from documents.file_handling import create_source_path_directory
from documents.file_handling import generate_unique_filename
from documents.matching import prefilter_documents_by_workflowtrigger
from documents.models import Correspondent
from documents.models import CustomFieldInstance
from documents.models import Document
from documents.models import DocumentType
from documents.models import PaperlessTask
from documents.models import ShareLink
from documents.models import ShareLinkBundle
from documents.models import StoragePath
from documents.models import Tag
from documents.models import WorkflowRun
from documents.models import WorkflowTrigger
from documents.plugins.base import ConsumeTaskPlugin
from documents.plugins.base import StopConsumeTaskError
from documents.plugins.helpers import ProgressManager
from documents.plugins.helpers import ProgressStatusOptions
from documents.sanity_checker import SanityCheckFailedException
from documents.search._backend import SearchIndexLockError
from documents.signals import document_updated
from documents.signals.handlers import cleanup_document_deletion
from documents.signals.handlers import run_workflows
from documents.signals.handlers import send_websocket_document_updated
from documents.utils import IterWrapper
from documents.utils import compute_checksum
from documents.utils import identity
from documents.versioning import annotate_effective_content
from documents.workflows.utils import get_workflows_for_trigger
from paperless.config import AIConfig
from paperless.config import RemoteOCRConfig
from paperless.logging import consume_task_id
from paperless.parsers import ParserContext
from paperless.parsers.registry import get_parser_registry
from paperless_ai.exceptions import LLMTimeoutError
from paperless_ai.indexing import llm_index_add_or_update_document
from paperless_ai.indexing import llm_index_remove_document
from paperless_ai.indexing import update_llm_index

if settings.AUDIT_LOG_ENABLED:
    from auditlog.models import LogEntry
logger = logging.getLogger("paperless.tasks")


@shared_task
def index_optimize() -> None:
    logger.info(
        "index_optimize is a no-op — Tantivy manages segment merging automatically.",
    )


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(SearchIndexLockError,),
    max_retries=5,
    retry_backoff=60,
    retry_jitter=True,
)
def index_document(self, document_id: int) -> None:
    """
    Deferred single-document index write.

    Used as a self-healing fallback when add_or_update() exhausts its lock retry
    budget during high-concurrency consumption. Runs via batch_update() directly
    to avoid re-entering the deferred scheduling path in add_or_update().

    If the document was deleted before this task runs, it exits cleanly.
    """
    from documents.search import get_backend

    try:
        document = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.info(
            "index_document: document %d no longer exists; skipping",
            document_id,
        )
        return
    with get_backend().batch_update() as batch:
        batch.add_or_update(document)


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(SearchIndexLockError,),
    max_retries=5,
    retry_backoff=60,
    retry_jitter=True,
)
def remove_document_from_index(self, doc_id: int) -> None:
    """
    Deferred single-document index removal.

    Used as a self-healing fallback when remove() exhausts its lock retry budget.
    Operates only on the Tantivy index; no database lookup required.
    If the document has already been removed, the term-query delete is a no-op.
    """
    from documents.search import get_backend

    with get_backend().batch_update() as batch:
        batch.remove(doc_id)


@shared_task
def train_classifier(
    *,
    status_callback: Callable[[str], None] | None = None,
) -> str:
    if (
        not Tag.objects.filter(matching_algorithm=Tag.MATCH_AUTO).exists()
        and not DocumentType.objects.filter(matching_algorithm=Tag.MATCH_AUTO).exists()
        and not Correspondent.objects.filter(matching_algorithm=Tag.MATCH_AUTO).exists()
        and not StoragePath.objects.filter(matching_algorithm=Tag.MATCH_AUTO).exists()
    ):
        result = "No automatic matching items, not training"
        logger.info(result)
        # Special case, items were once auto and trained, so remove the model
        # and prevent its use again
        if settings.MODEL_FILE.exists():  # pragma: no cover
            logger.info(f"Removing {settings.MODEL_FILE} so it won't be used")
            settings.MODEL_FILE.unlink()
        return result

    classifier = load_classifier()

    if not classifier:
        classifier = DocumentClassifier()

    if classifier.train(status_callback=status_callback):
        logger.info(
            f"Saving updated classifier model to {settings.MODEL_FILE}...",
        )
        classifier.save()
        return "Training completed successfully"
    else:
        logger.debug("Training data unchanged.")
        return "Training data unchanged"


@shared_task(bind=True)
def consume_file(
    self: Task,
    input_doc: ConsumableDocument,
    overrides: DocumentMetadataOverrides | None = None,
) -> (
    ConsumeFileSuccessResult
    | ConsumeFileStoppedResult
    | ConsumeFileDuplicateResult
    | None
):
    token = consume_task_id.set((self.request.id or "")[:8])
    try:
        # Default no overrides
        if overrides is None:
            overrides = DocumentMetadataOverrides()

        plugins: list[type[ConsumeTaskPlugin]] = (
            [
                ConsumerPreflightPlugin,
                ConsumerPlugin,
            ]
            if input_doc.root_document_id is not None
            else [
                ConsumerPreflightPlugin,
                AsnCheckPlugin,
                CollatePlugin,
                BarcodePlugin,
                AsnCheckPlugin,  # Re-run ASN check after barcode reading
                WorkflowTriggerPlugin,
                ConsumerPlugin,
            ]
        )

        with (
            ProgressManager(
                overrides.filename or input_doc.original_file.name,
                self.request.id,
            ) as status_mgr,
            TemporaryDirectory(dir=settings.SCRATCH_DIR) as tmp_dir,
        ):
            tmp_dir = Path(tmp_dir)
            msg = None
            for plugin_class in plugins:
                plugin_name = plugin_class.NAME

                plugin = plugin_class(
                    input_doc,
                    overrides,
                    status_mgr,
                    tmp_dir,
                    self.request.id,
                )

                if not plugin.able_to_run:
                    logger.debug(f"Skipping plugin {plugin_name}")
                    continue

                try:
                    logger.debug(f"Executing plugin {plugin_name}")
                    plugin.setup()

                    msg = plugin.run()

                    if msg is not None:
                        logger.info(f"{plugin_name} completed with: {msg}")
                    else:
                        logger.info(f"{plugin_name} completed with no message")

                    overrides = plugin.metadata

                except StopConsumeTaskError as e:
                    logger.info(f"{plugin_name} requested task exit: {e.message}")
                    return ConsumeFileStoppedResult(reason=e.message)

                except ConsumeFileDuplicateError as e:
                    logger.info(f"{plugin_name} rejected duplicate: {e}")
                    return ConsumeFileDuplicateResult(
                        duplicate_of=e.duplicate_id,
                        duplicate_in_trash=e.in_trash,
                    )

                except Exception as e:
                    logger.exception(f"{plugin_name} failed: {e}")
                    status_mgr.send_progress(
                        ProgressStatusOptions.FAILED,
                        f"{e}",
                        100,
                        100,
                    )
                    raise

                finally:
                    plugin.cleanup()

        return msg
    finally:
        consume_task_id.reset(token)


@shared_task
def sanity_check(*, raise_on_error: bool = True) -> str:
    messages = sanity_checker.check_sanity()
    messages.log_messages()

    if not messages.has_error and not messages.has_warning and not messages.has_info:
        return "No issues detected."

    parts: list[str] = []
    if messages.document_error_count:
        parts.append(f"{messages.document_error_count} document(s) with errors")
    if messages.document_warning_count:
        parts.append(f"{messages.document_warning_count} document(s) with warnings")
    if messages.document_info_count:
        parts.append(f"{messages.document_info_count} document(s) with infos")
    if messages.global_warning_count:
        parts.append(f"{messages.global_warning_count} global warning(s)")

    summary = ", ".join(parts) + " found."

    if messages.has_error:
        message = summary + " Check logs for details."
        if raise_on_error:
            raise SanityCheckFailedException(message)
        return message

    return summary


@shared_task
def bulk_update_documents(document_ids) -> None:
    from documents.search import get_backend

    document_ids = list(document_ids)
    # Annotated so indexing below doesn't query the versions of each document
    documents = annotate_effective_content(
        Document.objects.filter(id__in=document_ids),
    )

    for doc in documents:
        clear_document_caches(doc.pk)
        document_updated.send(
            sender=None,
            document=doc,
            logging_group=uuid.uuid4(),
            skip_ai_index=True,  # bulk path calls update_llm_index once below
        )
        post_save.send(Document, instance=doc, created=False)

    with get_backend().batch_update() as batch:
        for doc in documents:
            batch.add_or_update(doc)

    ai_config = AIConfig()
    if ai_config.llm_index_enabled:
        update_llm_index(
            rebuild=False,
            document_ids=document_ids,
        )


@shared_task
def update_document_content_maybe_archive_file(
    document_id,
    *,
    remote_ocr: bool = False,
) -> None:
    """
    Re-creates OCR content and thumbnail for a document, and archive file if
    it exists.

    Remote OCR is used only when the engine is configured to handle everything
    or if explicitly asked for via ``remote_ocr``.
    """
    document = Document.objects.get(id=document_id)

    mime_type = document.mime_type

    parser_class = get_parser_registry().get_parser_for_file(
        mime_type,
        document.original_filename or "",
        document.source_path,
        allow_remote=remote_ocr or RemoteOCRConfig().remote_ocr_by_default,
    )

    if not parser_class:
        logger.error(
            f"No parser found for mime type {mime_type}, cannot "
            f"archive document {document} (ID: {document_id})",
        )
        return

    with parser_class() as parser:
        parser.configure(ParserContext())

        try:
            produce_archive = should_produce_archive(
                parser,
                mime_type,
                document.source_path,
            )
            parser.parse(
                document.source_path,
                mime_type,
                produce_archive=produce_archive,
            )

            thumbnail = parser.get_thumbnail(document.source_path, mime_type)

            with transaction.atomic():
                oldDocument = Document.objects.get(pk=document.pk)
                if parser.get_archive_path():
                    checksum = compute_checksum(parser.get_archive_path())
                    # I'm going to save first so that in case the file move
                    # fails, the database is rolled back.
                    # We also don't use save() since that triggers the filehandling
                    # logic, and we don't want that yet (file not yet in place)
                    document.archive_filename = generate_unique_filename(
                        document,
                        archive_filename=True,
                    )
                    Document.objects.filter(pk=document.pk).update(
                        archive_checksum=checksum,
                        content=parser.get_text(),
                        archive_filename=document.archive_filename,
                    )
                    newDocument = Document.objects.get(pk=document.pk)
                    if settings.AUDIT_LOG_ENABLED:
                        LogEntry.objects.log_create(
                            instance=oldDocument,
                            changes={
                                "content": [oldDocument.content, newDocument.content],
                                "archive_checksum": [
                                    oldDocument.archive_checksum,
                                    newDocument.archive_checksum,
                                ],
                                "archive_filename": [
                                    oldDocument.archive_filename,
                                    newDocument.archive_filename,
                                ],
                            },
                            additional_data={
                                "reason": "Update document content",
                            },
                            action=LogEntry.Action.UPDATE,
                        )
                else:
                    Document.objects.filter(pk=document.pk).update(
                        content=parser.get_text(),
                    )

                    if settings.AUDIT_LOG_ENABLED:
                        LogEntry.objects.log_create(
                            instance=oldDocument,
                            changes={
                                "content": [oldDocument.content, parser.get_text()],
                            },
                            additional_data={
                                "reason": "Update document content",
                            },
                            action=LogEntry.Action.UPDATE,
                        )

                with FileLock(settings.MEDIA_LOCK):
                    if parser.get_archive_path():
                        create_source_path_directory(document.archive_path)
                        shutil.move(parser.get_archive_path(), document.archive_path)
                    shutil.move(thumbnail, document.thumbnail_path)

            document.refresh_from_db()
            logger.info(
                f"Updating index for document {document_id} ({document.archive_checksum})",
            )
            from documents.search import get_backend

            get_backend().add_or_update(document)

            ai_config = AIConfig()
            if ai_config.llm_index_enabled:
                llm_index_add_or_update_document(document)

            clear_document_caches(document.pk)

        except Exception:
            logger.exception(
                f"Error while parsing document {document} (ID: {document_id})",
            )


@shared_task
def empty_trash(doc_ids=None) -> None:
    if doc_ids is None:
        logger.info("Emptying trash of all expired documents")
    documents = (
        Document.deleted_objects.filter(id__in=doc_ids)
        if doc_ids is not None
        else Document.deleted_objects.filter(
            deleted_at__lt=timezone.localtime(timezone.now())
            - datetime.timedelta(
                days=settings.EMPTY_TRASH_DELAY,
            ),
        )
    )

    try:
        deleted_document_ids = list(documents.values_list("id", flat=True))
        # Temporarily connect the cleanup handler
        models.signals.post_delete.connect(cleanup_document_deletion, sender=Document)
        documents.delete()  # this is effectively a hard delete
        logger.info(f"Deleted {len(deleted_document_ids)} documents from trash")

        if settings.AUDIT_LOG_ENABLED:
            # Delete the audit log entries for documents that dont exist anymore
            LogEntry.objects.filter(
                content_type=ContentType.objects.get_for_model(Document),
                object_id__in=deleted_document_ids,
            ).delete()
    except Exception as e:  # pragma: no cover
        logger.exception(f"Error while emptying trash: {e}")
    finally:
        models.signals.post_delete.disconnect(
            cleanup_document_deletion,
            sender=Document,
        )


@shared_task
def check_scheduled_workflows() -> None:
    """
    Check and run all enabled scheduled workflows.

    Scheduled triggers are evaluated based on a target date field (e.g. added, created, modified, or a custom date field),
    combined with a day offset:
        - Positive offsets mean the workflow should trigger AFTER the specified date (e.g., offset = +7 → trigger 7 days after)
        - Negative offsets mean the workflow should trigger BEFORE the specified date (e.g., offset = -7 → trigger 7 days before)

    Once a document satisfies this condition, and recurring/non-recurring constraints are met, the workflow is run.
    """
    scheduled_workflows = get_workflows_for_trigger(
        WorkflowTrigger.WorkflowTriggerType.SCHEDULED,
    )
    if scheduled_workflows.count() > 0:
        logger.debug(f"Checking {len(scheduled_workflows)} scheduled workflows")
        now = timezone.now()
        for workflow in scheduled_workflows:
            schedule_triggers = workflow.triggers.filter(
                type=WorkflowTrigger.WorkflowTriggerType.SCHEDULED,
            )
            trigger: WorkflowTrigger
            for trigger in schedule_triggers:
                documents = Document.objects.none()
                offset_td = datetime.timedelta(days=trigger.schedule_offset_days)
                threshold = now - offset_td
                logger.debug(
                    f"Trigger {trigger.id}: checking if (date + {offset_td}) <= now ({now})",
                )

                match trigger.schedule_date_field:
                    case WorkflowTrigger.ScheduleDateField.ADDED:
                        documents = Document.objects.filter(
                            root_document__isnull=True,
                            added__lte=threshold,
                        )

                    case WorkflowTrigger.ScheduleDateField.CREATED:
                        documents = Document.objects.filter(
                            root_document__isnull=True,
                            created__lte=threshold,
                        )

                    case WorkflowTrigger.ScheduleDateField.MODIFIED:
                        documents = Document.objects.filter(
                            root_document__isnull=True,
                            modified__lte=threshold,
                        )

                    case WorkflowTrigger.ScheduleDateField.CUSTOM_FIELD:
                        # cap earliest date to avoid massive scans
                        earliest_date = now - datetime.timedelta(days=365)
                        if offset_td.days < -365:
                            logger.warning(
                                f"Trigger {trigger.id} has large negative offset ({offset_td.days}), "
                                f"limiting earliest scan date to {earliest_date}",
                            )

                        cf_filter_kwargs = {
                            "field": trigger.schedule_date_custom_field,
                            "value_date__isnull": False,
                            "value_date__lte": threshold,
                            "value_date__gte": earliest_date,
                        }

                        recent_cf_instances = CustomFieldInstance.objects.filter(
                            **cf_filter_kwargs,
                        )

                        matched_ids = [
                            cfi.document_id
                            for cfi in recent_cf_instances
                            if cfi.value_date
                            and (
                                timezone.make_aware(
                                    datetime.datetime.combine(
                                        cfi.value_date,
                                        datetime.time.min,
                                    ),
                                )
                                + offset_td
                                <= now
                            )
                        ]

                        documents = Document.objects.filter(
                            root_document__isnull=True,
                            id__in=matched_ids,
                        )

                if documents.exists():
                    documents = prefilter_documents_by_workflowtrigger(
                        documents,
                        trigger,
                    )

                if documents.exists():
                    logger.debug(
                        f"Found {documents.count()} documents for trigger {trigger}",
                    )
                    for document in documents:
                        workflow_runs = WorkflowRun.objects.filter(
                            document=document,
                            type=WorkflowTrigger.WorkflowTriggerType.SCHEDULED,
                            workflow=workflow,
                        ).order_by("-run_at")
                        if not trigger.schedule_is_recurring and workflow_runs.exists():
                            logger.debug(
                                f"Skipping document {document} for non-recurring workflow {workflow} as it has already been run",
                            )
                            continue

                        if (
                            trigger.schedule_is_recurring
                            and workflow_runs.exists()
                            and (
                                workflow_runs.first().run_at
                                > now
                                - datetime.timedelta(
                                    days=trigger.schedule_recurring_interval_days,
                                )
                            )
                        ):
                            # schedule is recurring but the last run was within the number of recurring interval days
                            logger.debug(
                                f"Skipping document {document} for recurring workflow {workflow} as the last run was within the recurring interval",
                            )
                            continue
                        run_workflows(
                            trigger_type=WorkflowTrigger.WorkflowTriggerType.SCHEDULED,
                            workflow_to_run=workflow,
                            document=document,
                        )
                        # Scheduled workflows dont send document_updated signal, so send a websocket update here to ensure clients are updated
                        send_websocket_document_updated(
                            sender=None,
                            document=document,
                        )


def update_document_parent_tags(tag: Tag, new_parent: Tag) -> None:
    """
    When a tag's parent changes, ensure all documents containing the tag also have
    the parent tag (and its ancestors) applied.
    """
    doc_tag_relationship = Document.tags.through

    doc_ids: list[int] = list(
        Document.objects.filter(tags=tag).values_list("pk", flat=True),
    )

    if not doc_ids:
        return

    parent_ids = [new_parent.id, *new_parent.get_ancestors_pks()]

    parent_ids = list(dict.fromkeys(parent_ids))

    existing_pairs = set(
        doc_tag_relationship.objects.filter(
            document_id__in=doc_ids,
            tag_id__in=parent_ids,
        ).values_list("document_id", "tag_id"),
    )

    to_create: list = []
    affected: set[int] = set()

    for doc_id in doc_ids:
        for parent_id in parent_ids:
            if (doc_id, parent_id) in existing_pairs:
                continue

            to_create.append(
                doc_tag_relationship(document_id=doc_id, tag_id=parent_id),
            )
            affected.add(doc_id)

    if to_create:
        doc_tag_relationship.objects.bulk_create(
            to_create,
            ignore_conflicts=True,
        )

    if affected:
        bulk_update_documents.apply_async(
            kwargs={"document_ids": list(affected)},
            headers={"trigger_source": PaperlessTask.TriggerSource.SYSTEM},
        )


@shared_task
def llmindex_index(
    *,
    iter_wrapper: IterWrapper[Document] = identity,
    rebuild: bool = False,
) -> str | None:
    ai_config = AIConfig()
    if not ai_config.llm_index_enabled:  # pragma: no cover
        logger.info("LLM index is disabled, skipping update.")
        return None

    from paperless_ai.indexing import update_llm_index

    return update_llm_index(
        iter_wrapper=iter_wrapper,
        rebuild=rebuild,
    )


@shared_task(
    bind=True,
    autoretry_for=(LLMTimeoutError,),
    max_retries=3,
    retry_backoff=60,
    retry_backoff_max=600,
    retry_jitter=True,
)
def apply_ai_suggestions(self, action_id: int, document_id: int) -> None:
    """
    Deferred "apply AI suggestions" workflow action.
    """
    from documents.models import WorkflowAction
    from documents.workflows.ai import apply_ai_suggestions_to_document

    try:
        action = WorkflowAction.objects.get(pk=action_id)
        document = Document.objects.select_related("owner").get(pk=document_id)
    except (WorkflowAction.DoesNotExist, Document.DoesNotExist):
        logger.warning(
            "Workflow action %s or document %s no longer exists, "
            "not applying AI suggestions",
            action_id,
            document_id,
        )
        return

    if not apply_ai_suggestions_to_document(action, document):
        return

    # No document_updated signal to avoid loop
    clear_document_caches(document.pk)
    index_document.delay(document.pk)

    ai_config = AIConfig()
    if ai_config.llm_index_enabled:
        update_document_in_llm_index.apply_async(kwargs={"document": document})


@shared_task
def update_document_in_llm_index(document) -> None:
    llm_index_add_or_update_document(document)


@shared_task
def remove_document_from_llm_index(document) -> None:
    llm_index_remove_document(document)


@shared_task
def build_share_link_bundle(bundle_id: int) -> None:
    try:
        bundle = (
            ShareLinkBundle.objects.filter(pk=bundle_id)
            .prefetch_related("documents")
            .get()
        )
    except ShareLinkBundle.DoesNotExist:
        logger.warning("Share link bundle %s no longer exists.", bundle_id)
        return

    bundle.remove_file()
    bundle.status = ShareLinkBundle.Status.PROCESSING
    bundle.last_error = None
    bundle.size_bytes = None
    bundle.built_at = None
    bundle.file_path = ""
    bundle.save(
        update_fields=[
            "status",
            "last_error",
            "size_bytes",
            "built_at",
            "file_path",
        ],
    )

    documents = list(bundle.documents.all().order_by("pk"))

    _, temp_zip_path_str = mkstemp(suffix=".zip", dir=settings.SCRATCH_DIR)
    temp_zip_path = Path(temp_zip_path_str)

    try:
        strategy_class = (
            ArchiveOnlyStrategy
            if bundle.file_version == ShareLink.FileVersion.ARCHIVE
            else OriginalsOnlyStrategy
        )
        with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            strategy = strategy_class(zipf)
            for document in documents:
                strategy.add_document(document)

        output_dir = settings.SHARE_LINK_BUNDLE_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        final_path = (output_dir / f"{bundle.slug}.zip").resolve()
        if final_path.exists():
            final_path.unlink()
        shutil.move(temp_zip_path, final_path)

        bundle.file_path = f"{bundle.slug}.zip"
        bundle.size_bytes = final_path.stat().st_size
        bundle.status = ShareLinkBundle.Status.READY
        bundle.built_at = timezone.now()
        bundle.last_error = None
        bundle.save(
            update_fields=[
                "file_path",
                "size_bytes",
                "status",
                "built_at",
                "last_error",
            ],
        )
        logger.info("Built share link bundle %s", bundle.pk)
    except Exception as exc:
        logger.exception(
            "Failed to build share link bundle %s: %s",
            bundle_id,
            exc,
        )
        bundle.status = ShareLinkBundle.Status.FAILED
        bundle.last_error = {
            "bundle_id": bundle_id,
            "exception_type": exc.__class__.__name__,
            "message": str(exc),
            "timestamp": timezone.now().isoformat(),
        }
        bundle.save(update_fields=["status", "last_error"])
        try:
            temp_zip_path.unlink()
        except OSError:
            pass
        raise
    finally:
        try:
            temp_zip_path.unlink(missing_ok=True)
        except OSError:
            pass


@shared_task
def cleanup_expired_share_link_bundles() -> None:
    now = timezone.now()
    expired_qs = ShareLinkBundle.objects.filter(
        expiration__isnull=False,
        expiration__lt=now,
    )
    count = 0
    for bundle in expired_qs.iterator():
        count += 1
        try:
            bundle.delete()
        except Exception as exc:
            logger.warning(
                "Failed to delete expired share link bundle %s: %s",
                bundle.pk,
                exc,
            )
    if count:
        logger.info("Deleted %s expired share link bundle(s)", count)


@shared_task
def run_ai_review_task(document_id: int, use_deepseek_ocr: bool = False) -> dict:
    """Async wrapper around documents.rentshield.service.run_ai_review() --
    dispatched from documents/rentshield_views.py's analyze_uploaded_view
    (a Workflow webhook action, which paperless-ngx only allows 5 seconds
    to respond) and from a scheduled Workflow that auto-fires it on any
    document tagged "Tenancy Contract" or whose filename contains
    "contract" (see manage.py create_rentshield_workflows). Imports done
    inside the task body to avoid a documents.tasks <-> documents.rentshield
    circular import at module load time.
    """
    from documents.models import Document
    from documents.rentshield.service import run_ai_review

    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.warning("run_ai_review_task: no such document %s", document_id)
        return {"error": f"Document {document_id} does not exist"}

    return run_ai_review(document, use_deepseek_ocr=use_deepseek_ocr)


@shared_task
def run_notarization_task(document_id: int) -> dict:
    """Async wrapper around documents.rentshield.service.request_notarization()
    -- the same function the manual POST .../notarize/ endpoint calls --
    dispatched from documents/rentshield_views.py's notarize_uploaded_view
    (a Workflow webhook action, which paperless-ngx only allows 5 seconds
    to respond). That Workflow ("RentShield: send confirmed notice to
    notary") only fires once a Property Owner/Lawyer has reviewed a
    notice with notarization requested and ticked its "Details Confirmed"
    custom field -- see manage.py create_rentshield_workflows. Imports
    done inside the task body to avoid a documents.tasks <->
    documents.rentshield circular import at module load time.
    """
    from documents.models import Document
    from documents.rentshield.service import request_notarization
    from documents.rentshield.service import sync_notarization_stage_tag

    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.warning("run_notarization_task: no such document %s", document_id)
        return {"error": f"Document {document_id} does not exist"}

    try:
        result = request_notarization(document)
    except Exception as exc:
        logger.exception(
            "run_notarization_task: notarization dispatch failed for document %s: %s",
            document_id,
            exc,
        )
        sync_notarization_stage_tag(document, "failed")
        return {"error": str(exc)}

    sync_notarization_stage_tag(document, result["status"])
    return result


@shared_task
def notify_notice_served_task(document_id: int, status: str) -> dict:
    """Async wrapper around documents.rentshield.service's served_date
    stamping + _notify_notice_served() -- dispatched from documents/
    rentshield/signals.py's on_commit hook rather than run inline there.
    Verified for real that running this inline (even via
    transaction.on_commit()) inside the CustomFieldInstance post_save
    signal that fires mid-save of the "Notary Public Status" field does
    NOT reliably persist: the write is visible to its own connection
    immediately afterward but silently absent moments later, through the
    exact same real DRF PATCH .../api/documents/<id>/ path the notary
    officer's browser uses -- some ambient transaction state from that
    request appears to roll it back after the fact, even though nothing
    raises. A Celery task gets its own fresh connection/transaction with
    nothing ambient to interact with, same reasoning as
    run_ai_review_task/run_notarization_task above for keeping this off
    the request's own transaction entirely. Imports done inside the task
    body to avoid a documents.tasks <-> documents.rentshield circular
    import at module load time.
    """
    from django.utils import timezone

    from documents.models import Document
    from documents.rentshield.service import _notify_notice_served
    from documents.rentshield.service import _set_custom_field_value

    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.warning("notify_notice_served_task: no such document %s", document_id)
        return {"error": f"Document {document_id} does not exist"}

    if status == "completed":
        _set_custom_field_value(document, "served_date", timezone.now().date())
    _notify_notice_served(document)
    return {"document_id": document_id, "status": status}


@shared_task
def run_notary_provider_scan_task() -> dict:
    """Scheduled daily (PAPERLESS_RENTSHIELD_NOTARY_SCAN_CRON, default
    03:15) via CELERY_BEAT_SCHEDULE in paperless/settings/__init__.py --
    runs documents.rentshield.notary_research.scanner.scan_all_targets()
    and emails settings.RENTSHIELD_NOTARY_RESEARCH_NOTIFY_EMAIL only
    when a target shows a NEW api/developer/integration signal it didn't
    have last scan, not on every run. A no-op, logged not raised, when
    SCRAPFLY_API_KEY isn't configured -- same graceful-degradation
    pattern as every other optional external integration here.
    """
    from django.conf import settings
    from django.core.mail import send_mail

    if not settings.SCRAPFLY_API_KEY:
        logger.debug("run_notary_provider_scan_task: SCRAPFLY_API_KEY is unset -- skipping.")
        return {"skipped": "SCRAPFLY_API_KEY not configured"}

    from documents.rentshield.notary_research.scanner import scan_all_targets

    result = scan_all_targets()
    logger.info(
        "run_notary_provider_scan_task: scanned %s target(s), %s error(s), %s new signal(s)",
        len(result["scanned"]),
        len(result["errors"]),
        len(result["new_signals"]),
    )

    recipient = settings.RENTSHIELD_NOTARY_RESEARCH_NOTIFY_EMAIL
    if result["new_signals"] and recipient:
        lines = [
            f"- {entry['name']} ({entry['url']}): {', '.join(entry['new_keywords'])}"
            for entry in result["new_signals"]
        ]
        try:
            send_mail(
                subject="RentShield: new notary-provider API signal found",
                message=(
                    "The notary-provider research scan found new mentions of "
                    "possible API/developer/integration access on:\n\n"
                    + "\n".join(lines)
                    + "\n\nWorth a manual look before assuming anything -- "
                    "these are keyword matches, not confirmed API access."
                ),
                from_email=None,
                recipient_list=[recipient],
                fail_silently=False,
            )
        except Exception:
            logger.exception(
                "run_notary_provider_scan_task: failed to send notification email to %r",
                recipient,
            )

    return result


@shared_task
def finalize_paid_notice_task(order_id: int) -> dict:
    """Async wrapper around documents.rentshield_billing.views.finalize_paid_order()
    -- dispatched from stripe_webhook_view once a real Stripe payment is
    confirmed, so the webhook handler itself doesn't block on notice
    generation (same reasoning as run_ai_review_task/
    run_notarization_task being dispatched from their own webhook
    views). Imports done inside the task body to avoid a documents.tasks
    <-> documents.rentshield_billing circular import at module load time.
    """
    from documents.rentshield_billing.models import Order
    from documents.rentshield_billing.views import finalize_paid_order

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        logger.warning("finalize_paid_notice_task: no such order %s", order_id)
        return {"error": f"Order {order_id} does not exist"}

    try:
        finalize_paid_order(order)
    except Exception as exc:
        logger.exception(
            "finalize_paid_notice_task: notice generation failed for paid order %s: %s",
            order_id,
            exc,
        )
        order.status = order.Status.FAILED
        order.save(update_fields=["status"])
        return {"error": str(exc)}

    return {"order_id": order.id, "document_id": order.document_id}


@shared_task
def run_identity_prescreen_task(verification_id: int) -> dict:
    """Async wrapper around documents.rentshield_identity.ai_prescreen.
    summarize_for_notary() -- dispatched from documents/rentshield_identity/
    views.py's upload_video_view right after a verification reaches
    AWAITING_NOTARY_REVIEW, so the AI summary is usually already sitting
    there by the time a Notary opens it, without making their own request
    wait on an LLM call. Never blocks or fails the pipeline itself: a
    missing ANTHROPIC_API_KEY or any API error just leaves
    ai_prescreen_summary blank, same "advisory only" pattern as the
    chip-vs-selfie face match. Imports done inside the task body to avoid
    a documents.tasks <-> documents.rentshield_identity circular import
    at module load time, same reasoning as this file's other tasks.
    """
    from documents.rentshield_identity.ai_prescreen import AiPrescreenError
    from documents.rentshield_identity.ai_prescreen import summarize_for_notary
    from documents.rentshield_identity.models import IdentityVerification

    try:
        record = IdentityVerification.objects.get(id=verification_id)
    except IdentityVerification.DoesNotExist:
        logger.warning("run_identity_prescreen_task: no such verification %s", verification_id)
        return {"error": f"IdentityVerification {verification_id} does not exist"}

    try:
        summary = summarize_for_notary(record)
    except AiPrescreenError as exc:
        logger.warning("run_identity_prescreen_task: skipped for verification %s: %s", verification_id, exc)
        return {"skipped": str(exc)}

    record.ai_prescreen_summary = summary
    record.save(update_fields=["ai_prescreen_summary", "updated_at"])
    return {"verification_id": verification_id, "summary": summary}


@shared_task
def run_video_call_reminder_task() -> dict:
    """Scheduled every few minutes (see CELERY_BEAT_SCHEDULE in
    paperless/settings/__init__.py) -- emails both sides of a CONFIRMED
    IdentityVerificationCall shortly before it starts. `reminder_sent_at`
    is stamped the moment the email fires so a call straddling two runs
    of this task never gets a second reminder -- same single-use-stamp
    pattern as DevicePairingCode's own `claimed_at`."""
    from django.core.mail import send_mail
    from django.utils import timezone

    from documents.rentshield_identity.models import IdentityVerificationCall

    now = timezone.now()
    due = IdentityVerificationCall.objects.filter(
        status=IdentityVerificationCall.Status.CONFIRMED,
        reminder_sent_at__isnull=True,
        scheduled_at__gte=now,
        scheduled_at__lte=now + datetime.timedelta(minutes=30),
    ).select_related("identity_verification__user", "proposed_by")

    sent = 0
    for call in due:
        recipients = [
            email
            for email in (
                call.identity_verification.user.email,
                call.proposed_by.email if call.proposed_by else "",
            )
            if email
        ]
        subject = "RentShield: Your video call starts soon"
        message = (
            "Reminder: your RentShield identity-verification video call is "
            f"scheduled for {call.scheduled_at:%Y-%m-%d %H:%M %Z}, coming up soon. "
            "Join from RentShield when it's time.\n"
        )
        for recipient in recipients:
            try:
                send_mail(subject=subject, message=message, from_email=None, recipient_list=[recipient], fail_silently=False)
            except Exception:
                logger.exception("run_video_call_reminder_task: failed to email %r for call %s", recipient, call.id)
        call.reminder_sent_at = now
        call.save(update_fields=["reminder_sent_at", "updated_at"])
        sent += 1
    return {"reminders_sent": sent}


@shared_task
def run_video_call_recording_ingest_task() -> dict:
    """Scheduled every few minutes -- Jibri (docker-compose's
    `jitsi-jibri` service) writes each finished recording into its own
    `<room_name>/` subdirectory under
    settings.RENTSHIELD_JIBRI_RECORDINGS_DIR (a shared volume, not a
    network call). This looks for a subdirectory matching a call still
    missing `recording_file`, attaches the first video file found, and
    deletes the source directory so it's never re-ingested. A periodic
    scan instead of a Jibri finalize-script webhook -- avoids
    overriding internals of the vendored Jibri image for what's
    otherwise a rare, non-latency-sensitive event."""
    import shutil
    from pathlib import Path

    from django.conf import settings
    from django.core.files import File

    from documents.rentshield_identity.models import IdentityVerificationCall

    recordings_dir = Path(settings.RENTSHIELD_JIBRI_RECORDINGS_DIR)
    if not recordings_dir.is_dir():
        return {"skipped": "recordings directory does not exist"}

    pending = {
        call.room_name: call
        for call in IdentityVerificationCall.objects.filter(recording_file="").filter(
            status__in=[
                IdentityVerificationCall.Status.CONFIRMED,
                IdentityVerificationCall.Status.COMPLETED,
                IdentityVerificationCall.Status.NO_SHOW,
            ],
        )
    }
    if not pending:
        return {"ingested": 0}

    ingested = 0
    for room_dir in recordings_dir.iterdir():
        call = pending.get(room_dir.name)
        if not call or not room_dir.is_dir():
            continue
        video_file = next(
            (f for f in room_dir.iterdir() if f.suffix.lower() in (".mp4", ".webm", ".mkv")),
            None,
        )
        if not video_file:
            continue
        with video_file.open("rb") as fh:
            call.recording_file.save(video_file.name, File(fh), save=False)
        call.save(update_fields=["recording_file", "updated_at"])
        shutil.rmtree(room_dir, ignore_errors=True)
        ingested += 1
    return {"ingested": ingested}
