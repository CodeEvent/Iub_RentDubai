import json

from django.conf import settings
from django.core.management.base import BaseCommand
from documents.models import CustomField
from documents.models import DocumentType
from documents.models import StoragePath
from documents.models import Tag
from documents.models import Workflow
from documents.models import WorkflowAction
from documents.models import WorkflowActionEmail
from documents.models import WorkflowActionWebhook
from documents.models import WorkflowTrigger
from documents.rentshield.custom_fields import AI_REVIEWED_TAG_NAME
from documents.rentshield.custom_fields import BEING_NOTARIZED_TAG_NAME
from documents.rentshield.custom_fields import NEEDS_AI_REVIEW_TAG_NAME
from documents.rentshield.custom_fields import NOTARIZATION_FAILED_TAG_NAME
from documents.rentshield.custom_fields import NOTARIZED_TAG_NAME
from documents.rentshield.custom_fields import PENDING_REVIEW_TAG_NAME
from documents.rentshield.custom_fields import RENTSHIELD_TAG_NAME
from documents.rentshield.custom_fields import TENANCY_CONTRACT_TAG_NAME
from documents.rentshield.custom_fields import key_to_id_map
from documents.rentshield.custom_fields import notarization_pending_query as _shared_notarization_pending_query
from documents.rentshield.custom_fields import old_buggy_notarization_pending_query as _shared_old_buggy_notarization_pending_query

STATUTORY_REASONS = ["sale", "personal", "demolition", "renovation"]
BREACH_REASONS = ["nonpayment", "sublease"]

# Deliberately fake -- there is no way to know the real recipient here,
# and this repo must never carry a hardcoded personal address. Edit the
# created email workflows in Settings > Workflows before relying on them,
# and set PAPERLESS_EMAIL_* so paperless-ngx can actually send mail.
PLACEHOLDER_ALERT_EMAIL = getattr(
    settings,
    "RENTSHIELD_ALERT_EMAIL",
    None,
) or "changeme@example.com"

PLACEHOLDER_WEBHOOK_URL = "https://example.com/rentshield-webhook"


class Command(BaseCommand):
    help = (
        "Idempotently creates the 13 RentShield paperless-ngx Workflows "
        "(see README.md 'Workflows' section for what each one does and "
        "why). Safe to re-run -- looks up existing Workflows by name and "
        "leaves them alone if already present, so edits made in the UI "
        "afterward are not clobbered."
    )

    def handle(self, *args, **options):
        ids = key_to_id_map()
        missing = [
            k
            for k in (
                "notice_date",
                "reason",
                "add_notarization",
                "add_ai_review",
                "esign_status",
                "details_confirmed",
            )
            if k not in ids
        ]
        if missing:
            self.stderr.write(
                self.style.ERROR(
                    "Missing RentShield custom fields: "
                    f"{missing}. Run `manage.py migrate` first "
                    "(documents.0026/0027/0028_rentshield_* migrations create them).",
                ),
            )
            return

        rentshield_tag, _ = Tag.objects.get_or_create(
            name=RENTSHIELD_TAG_NAME,
            defaults={"color": "#10b981"},
        )
        needs_ai_review_tag, _ = Tag.objects.get_or_create(
            name=NEEDS_AI_REVIEW_TAG_NAME,
            defaults={"color": "#f59e0b"},
        )
        Tag.objects.get_or_create(
            name=AI_REVIEWED_TAG_NAME,
            defaults={"color": "#059669"},
        )
        tenancy_contract_tag, _ = Tag.objects.get_or_create(
            name=TENANCY_CONTRACT_TAG_NAME,
            defaults={"color": "#6366f1"},
        )
        pending_review_tag, _ = Tag.objects.get_or_create(
            name=PENDING_REVIEW_TAG_NAME,
            defaults={"color": "#f59e0b"},
        )
        being_notarized_tag, _ = Tag.objects.get_or_create(
            name=BEING_NOTARIZED_TAG_NAME,
            defaults={"color": "#6366f1"},
        )
        Tag.objects.get_or_create(
            name=NOTARIZED_TAG_NAME,
            defaults={"color": "#059669"},
        )
        Tag.objects.get_or_create(
            name=NOTARIZATION_FAILED_TAG_NAME,
            defaults={"color": "#dc2626"},
        )
        statutory_type, _ = DocumentType.objects.get_or_create(
            name="12-Month Statutory Notice",
        )
        breach_type, _ = DocumentType.objects.get_or_create(
            name="30-Day Breach Notice",
        )
        notices_path, _ = StoragePath.objects.get_or_create(
            name="Tenancy Notices",
            defaults={"path": "Tenancy Notices/{created_year}/{title}"},
        )

        reason_field = ids["reason"]
        notarization_field = ids["add_notarization"]
        ai_review_field = ids["add_ai_review"]
        esign_status_field = ids["esign_status"]
        details_confirmed_field = ids["details_confirmed"]
        notice_date_custom_field = CustomField.objects.get(id=ids["notice_date"])

        def reason_query(keys):
            return json.dumps([reason_field, "in", keys])

        # See documents/rentshield/custom_fields.py's
        # notarization_pending_query() docstring for why `exists: False`,
        # not `isnull: True` -- shared with create_rentshield_dashboards.py,
        # which needs the identical query for its Saved View filter.
        def notarization_pending_query():
            return _shared_notarization_pending_query(notarization_field, esign_status_field)

        def old_buggy_notarization_pending_query():
            return _shared_old_buggy_notarization_pending_query(notarization_field, esign_status_field)

        self._create_workflow(
            name="RentShield: statutory expiry reminder",
            order=1,
            trigger_kwargs={
                "type": WorkflowTrigger.WorkflowTriggerType.SCHEDULED,
                "schedule_date_field": WorkflowTrigger.ScheduleDateField.CUSTOM_FIELD,
                "schedule_date_custom_field": notice_date_custom_field,
                "schedule_offset_days": 335,
                "schedule_is_recurring": False,
                "filter_custom_field_query": reason_query(STATUTORY_REASONS),
            },
            trigger_tags=[rentshield_tag],
            action_kwargs={"type": WorkflowAction.WorkflowActionType.EMAIL},
            email_kwargs={
                "subject": "RentShield: notice expiring soon - {{ title }}",
                "body": (
                    "The 12-month statutory notice \"{{ title }}\" was served on "
                    "{{ added }} and its legal period is ending within 30 days. "
                    "Review it and follow up (RDSC filing if the tenant hasn't "
                    "vacated): {{ doc_url }}"
                ),
                "to": PLACEHOLDER_ALERT_EMAIL,
            },
            enabled=False,
        )

        self._create_workflow(
            name="RentShield: breach deadline reminder",
            order=2,
            trigger_kwargs={
                "type": WorkflowTrigger.WorkflowTriggerType.SCHEDULED,
                "schedule_date_field": WorkflowTrigger.ScheduleDateField.CUSTOM_FIELD,
                "schedule_date_custom_field": notice_date_custom_field,
                "schedule_offset_days": 25,
                "schedule_is_recurring": False,
                "filter_custom_field_query": reason_query(BREACH_REASONS),
            },
            trigger_tags=[rentshield_tag],
            action_kwargs={"type": WorkflowAction.WorkflowActionType.EMAIL},
            email_kwargs={
                "subject": "RentShield: breach notice deadline approaching - {{ title }}",
                "body": (
                    "The 30-day breach notice \"{{ title }}\" was served on "
                    "{{ added }} and its compliance deadline is in about 5 days. "
                    "Review it: {{ doc_url }}"
                ),
                "to": PLACEHOLDER_ALERT_EMAIL,
            },
            enabled=False,
        )

        self._create_workflow(
            name="RentShield: notarization requested, not dispatched",
            order=3,
            trigger_kwargs={
                "type": WorkflowTrigger.WorkflowTriggerType.DOCUMENT_ADDED,
                "filter_custom_field_query": notarization_pending_query(),
            },
            trigger_tags=[rentshield_tag],
            action_kwargs={"type": WorkflowAction.WorkflowActionType.WEBHOOK},
            webhook_kwargs={
                "url": PLACEHOLDER_WEBHOOK_URL,
                "use_params": True,
                "as_json": True,
                "params": {
                    "event": "notarization_pending",
                    "title": "{{ title }}",
                    "doc_id": "{{ doc_id }}",
                    "doc_url": "{{ doc_url }}",
                },
                "include_document": False,
            },
            enabled=False,
        )

        self._create_workflow(
            name="RentShield: notarization stalled (recurring)",
            order=4,
            trigger_kwargs={
                "type": WorkflowTrigger.WorkflowTriggerType.SCHEDULED,
                "schedule_date_field": WorkflowTrigger.ScheduleDateField.ADDED,
                "schedule_offset_days": 2,
                "schedule_is_recurring": True,
                "schedule_recurring_interval_days": 2,
                "filter_custom_field_query": notarization_pending_query(),
            },
            trigger_tags=[rentshield_tag],
            action_kwargs={"type": WorkflowAction.WorkflowActionType.WEBHOOK},
            webhook_kwargs={
                "url": PLACEHOLDER_WEBHOOK_URL,
                "use_params": True,
                "as_json": True,
                "params": {
                    "event": "notarization_stalled",
                    "title": "{{ title }}",
                    "doc_id": "{{ doc_id }}",
                    "doc_url": "{{ doc_url }}",
                },
                "include_document": False,
            },
            enabled=False,
        )

        self._create_workflow(
            name="RentShield: file into Tenancy Notices path",
            order=5,
            trigger_kwargs={"type": WorkflowTrigger.WorkflowTriggerType.DOCUMENT_ADDED},
            trigger_tags=[rentshield_tag],
            action_kwargs={
                "type": WorkflowAction.WorkflowActionType.ASSIGNMENT,
                "assign_storage_path": notices_path,
            },
        )

        self._create_workflow(
            name="RentShield: AI-review queue tag",
            order=6,
            trigger_kwargs={
                "type": WorkflowTrigger.WorkflowTriggerType.DOCUMENT_ADDED,
                "filter_custom_field_query": json.dumps([ai_review_field, "exact", True]),
            },
            trigger_tags=[rentshield_tag],
            action_kwargs={"type": WorkflowAction.WorkflowActionType.ASSIGNMENT},
            action_tags=[needs_ai_review_tag],
        )

        self._create_workflow(
            name="RentShield: tag statutory notices as document type",
            order=7,
            trigger_kwargs={
                "type": WorkflowTrigger.WorkflowTriggerType.DOCUMENT_ADDED,
                "filter_custom_field_query": reason_query(STATUTORY_REASONS),
            },
            trigger_tags=[rentshield_tag],
            action_kwargs={
                "type": WorkflowAction.WorkflowActionType.ASSIGNMENT,
                "assign_document_type": statutory_type,
            },
        )

        self._create_workflow(
            name="RentShield: tag breach notices as document type",
            order=8,
            trigger_kwargs={
                "type": WorkflowTrigger.WorkflowTriggerType.DOCUMENT_ADDED,
                "filter_custom_field_query": reason_query(BREACH_REASONS),
            },
            trigger_tags=[rentshield_tag],
            action_kwargs={
                "type": WorkflowAction.WorkflowActionType.ASSIGNMENT,
                "assign_document_type": breach_type,
            },
        )

        self._create_workflow(
            name="RentShield: notify external tool on new notice",
            order=9,
            trigger_kwargs={"type": WorkflowTrigger.WorkflowTriggerType.DOCUMENT_ADDED},
            trigger_tags=[rentshield_tag],
            action_kwargs={"type": WorkflowAction.WorkflowActionType.WEBHOOK},
            webhook_kwargs={
                "url": PLACEHOLDER_WEBHOOK_URL,
                "use_params": True,
                "as_json": True,
                "params": {
                    "event": "notice_created",
                    "title": "{{ title }}",
                    "doc_id": "{{ doc_id }}",
                    "doc_url": "{{ doc_url }}",
                },
                "include_document": False,
            },
            enabled=False,
        )

        analyze_uploaded_url = f"{settings.RENTSHIELD_INTERNAL_URL}/api/documents/notice/analyze-uploaded/"
        ai_review_webhook_kwargs = {
            "url": analyze_uploaded_url,
            "use_params": True,
            "as_json": True,
            "params": {"doc_id": "{{ doc_id }}"},
            "include_document": False,
        }

        self._create_workflow(
            name="RentShield: AI review uploaded contracts (by filename)",
            order=11,
            trigger_kwargs={
                "type": WorkflowTrigger.WorkflowTriggerType.DOCUMENT_ADDED,
                "filter_filename": "*contract*",
            },
            trigger_not_tags=[rentshield_tag],
            action_kwargs={"type": WorkflowAction.WorkflowActionType.WEBHOOK},
            webhook_kwargs=ai_review_webhook_kwargs,
        )

        self._create_workflow(
            name="RentShield: AI review uploaded contracts (by tag)",
            order=12,
            trigger_kwargs={"type": WorkflowTrigger.WorkflowTriggerType.DOCUMENT_ADDED},
            trigger_tags=[tenancy_contract_tag],
            action_kwargs={"type": WorkflowAction.WorkflowActionType.WEBHOOK},
            webhook_kwargs=ai_review_webhook_kwargs,
        )

        self._create_workflow(
            name="RentShield: tag notarization pending review",
            order=14,
            trigger_kwargs={
                "type": WorkflowTrigger.WorkflowTriggerType.DOCUMENT_ADDED,
                "filter_custom_field_query": json.dumps([notarization_field, "exact", True]),
            },
            trigger_tags=[rentshield_tag],
            action_kwargs={"type": WorkflowAction.WorkflowActionType.ASSIGNMENT},
            action_tags=[pending_review_tag],
        )

        notarize_uploaded_url = f"{settings.RENTSHIELD_INTERNAL_URL}/api/documents/notice/notarize-uploaded/"
        self._create_workflow(
            name="RentShield: send confirmed notice to notary",
            order=15,
            trigger_kwargs={
                # DOCUMENT_UPDATED, not DOCUMENT_ADDED: this fires when a
                # Property Owner/Lawyer reviews an already-created,
                # notarization-requested notice and ticks "Details
                # Confirmed" afterward -- not at creation time.
                "type": WorkflowTrigger.WorkflowTriggerType.DOCUMENT_UPDATED,
                "filter_custom_field_query": json.dumps([details_confirmed_field, "exact", True]),
            },
            # Requiring the "Pending Review" tag here (not just the field
            # value) is what stops this from re-firing on every later save
            # of an already-dispatched notice: the first action below
            # removes that tag, so a subsequent save with
            # details_confirmed still True no longer matches this trigger.
            trigger_tags=[pending_review_tag],
            action_kwargs={"type": WorkflowAction.WorkflowActionType.REMOVAL},
            remove_tags=[pending_review_tag],
            extra_actions=[
                {
                    "action_kwargs": {"type": WorkflowAction.WorkflowActionType.ASSIGNMENT},
                    "action_tags": [being_notarized_tag],
                },
                {
                    "action_kwargs": {"type": WorkflowAction.WorkflowActionType.WEBHOOK},
                    "webhook_kwargs": {
                        "url": notarize_uploaded_url,
                        "use_params": True,
                        "as_json": True,
                        "params": {"doc_id": "{{ doc_id }}"},
                        "include_document": False,
                    },
                },
            ],
        )

        self._repair_notarization_pending_queries(
            workflow_names=[
                "RentShield: notarization requested, not dispatched",
                "RentShield: notarization stalled (recurring)",
            ],
            old_query=old_buggy_notarization_pending_query(),
            new_query=notarization_pending_query(),
        )

        self.stdout.write(self.style.SUCCESS("RentShield workflows created/verified."))
        self.stdout.write(
            self.style.WARNING(
                "Before relying on these:\n"
                "  - Email workflows (#1, #2) and webhook workflows (#3, #4, #9) "
                "were created DISABLED, with placeholder recipients/URLs "
                f"({PLACEHOLDER_ALERT_EMAIL!r} / {PLACEHOLDER_WEBHOOK_URL!r}). "
                "Edit them under Manage > Workflows with real values, then enable.\n"
                "  - Email workflows also need PAPERLESS_EMAIL_* configured "
                "(paperless-ngx's own SMTP settings) or nothing will send.\n"
                "  - Workflow email/webhook bodies can only use paperless-ngx's "
                "fixed Jinja placeholders (title, doc_url, doc_id, added, "
                "created, correspondent, document_type, owner_username, "
                "filename) -- custom field values (landlord name, reason, "
                "etc.) are NOT available in those templates. The receiving "
                "webhook endpoint should fetch full details via "
                "GET /api/documents/<doc_id>/ using the id it's given.\n"
                "  - Workflows #11/#12 (AI review on upload) and #15 (send "
                "confirmed notice to notary) call back into this same "
                f"server ({analyze_uploaded_url}, {notarize_uploaded_url}) "
                "-- if this Django process isn't reachable at that address "
                "from its own Celery worker (e.g. in a docker-compose/"
                "production topology), set PAPERLESS_RENTSHIELD_INTERNAL_URL "
                "and re-run this command.\n"
                "  - Workflow #15 only fires on a DOCUMENT_UPDATED save "
                "where the notice still carries the \"Pending Review\" tag "
                "(#14 applies it at creation) -- ticking \"Details "
                "Confirmed\" on a notice that never had notarization "
                "requested does nothing, by design.\n"
                "  - Notarization dispatch itself still needs a real "
                "DocuSeal/OpenSign reachable (see documents/rentshield/"
                "esign/); without one it fails gracefully and tags the "
                "notice \"Notarization Failed\" rather than hanging.",
            ),
        )

    def _repair_notarization_pending_queries(self, *, workflow_names, old_query, new_query):
        """One-time healing for a real bug in an already-shipped query
        (see notarization_pending_query()'s docstring comment above): any
        already-created workflow whose trigger still carries the old,
        never-matches-anything query gets it replaced. Only touches rows
        that exactly match the known-buggy value, so a real edit made
        afterward in the UI is left alone."""
        for name in workflow_names:
            workflow = Workflow.objects.filter(name=name).first()
            if not workflow:
                continue
            for trigger in workflow.triggers.filter(filter_custom_field_query=old_query):
                trigger.filter_custom_field_query = new_query
                trigger.save(update_fields=["filter_custom_field_query"])
                self.stdout.write(
                    self.style.SUCCESS(f"Repaired notarization-pending query on: {name}"),
                )

    def _build_action(
        self,
        *,
        action_kwargs,
        order=0,
        email_kwargs=None,
        webhook_kwargs=None,
        action_tags=None,
        remove_tags=None,
        action_view_groups=None,
        action_change_groups=None,
    ):
        action_kwargs = {**action_kwargs, "order": order}
        if email_kwargs:
            action_kwargs = {**action_kwargs, "email": WorkflowActionEmail.objects.create(**email_kwargs)}
        if webhook_kwargs:
            action_kwargs = {**action_kwargs, "webhook": WorkflowActionWebhook.objects.create(**webhook_kwargs)}

        action = WorkflowAction.objects.create(**action_kwargs)
        if action_tags:
            action.assign_tags.set(action_tags)
        if remove_tags:
            action.remove_tags.set(remove_tags)
        if action_view_groups:
            action.assign_view_groups.set(action_view_groups)
        if action_change_groups:
            action.assign_change_groups.set(action_change_groups)
        return action

    def _create_workflow(
        self,
        *,
        name,
        order,
        trigger_kwargs,
        action_kwargs,
        trigger_tags=None,
        trigger_not_tags=None,
        email_kwargs=None,
        webhook_kwargs=None,
        action_tags=None,
        remove_tags=None,
        action_view_groups=None,
        action_change_groups=None,
        extra_actions=None,
        enabled=True,
    ):
        """A Workflow has exactly one Trigger but can have several
        Actions, run in `order` -- `extra_actions` is a list of the same
        per-action kwargs `_build_action()` takes, for a Workflow that
        needs to do more than one thing (e.g. #15: swap a pair of
        pipeline-stage tags *and* fire a webhook)."""
        if Workflow.objects.filter(name=name).exists():
            self.stdout.write(f"Skipping (already exists): {name}")
            return

        trigger = WorkflowTrigger.objects.create(**trigger_kwargs)
        if trigger_tags:
            trigger.filter_has_tags.set(trigger_tags)
        if trigger_not_tags:
            trigger.filter_has_not_tags.set(trigger_not_tags)

        actions = [
            self._build_action(
                action_kwargs=action_kwargs,
                order=0,
                email_kwargs=email_kwargs,
                webhook_kwargs=webhook_kwargs,
                action_tags=action_tags,
                remove_tags=remove_tags,
                action_view_groups=action_view_groups,
                action_change_groups=action_change_groups,
            ),
        ]
        for i, extra in enumerate(extra_actions or [], start=1):
            actions.append(self._build_action(order=i, **extra))

        workflow = Workflow.objects.create(name=name, order=order, enabled=enabled)
        workflow.triggers.set([trigger])
        workflow.actions.set(actions)

        self.stdout.write(self.style.SUCCESS(f"Created: {name}{'' if enabled else ' (disabled)'}"))
