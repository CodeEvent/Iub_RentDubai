import json

from django.conf import settings
from django.contrib.auth.models import Group
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
from documents.rentshield.custom_fields import NEEDS_AI_REVIEW_TAG_NAME
from documents.rentshield.custom_fields import RENTSHIELD_TAG_NAME
from documents.rentshield.custom_fields import TENANCY_CONTRACT_TAG_NAME
from documents.rentshield.custom_fields import key_to_id_map

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
        "Idempotently creates the 10 RentShield paperless-ngx Workflows "
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
            )
            if k not in ids
        ]
        if missing:
            self.stderr.write(
                self.style.ERROR(
                    "Missing RentShield custom fields: "
                    f"{missing}. Run `manage.py migrate` first "
                    "(documents.0026_rentshield_custom_fields creates them).",
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
        # Minimal placeholder -- task 5 (per-role permissions) fleshes this
        # group's actual membership and object-level permissions out.
        lawyer_group, _ = Group.objects.get_or_create(name="Lawyer")

        reason_field = ids["reason"]
        notarization_field = ids["add_notarization"]
        ai_review_field = ids["add_ai_review"]
        esign_status_field = ids["esign_status"]
        notice_date_custom_field = CustomField.objects.get(id=ids["notice_date"])

        def reason_query(keys):
            return json.dumps([reason_field, "in", keys])

        def notarization_pending_query():
            # "esign_status doesn't exist yet OR is blank": the correct op
            # for "this CustomField was never set on this document" is
            # `exists: False`, not `isnull: True` -- `isnull` only matches
            # a CustomFieldInstance row whose value column is SQL NULL,
            # which request_notarization()/_set_custom_field_value() never
            # produces (they only ever write a real string). A doc that
            # never had notarization requested has no esign_status
            # instance row at all, so `isnull` silently matched nothing --
            # confirmed via a real un-notarized demo notice returning 0
            # instead of 1 from this exact query.
            return json.dumps(
                [
                    "AND",
                    [
                        [notarization_field, "exact", True],
                        ["OR", [[esign_status_field, "exists", False], [esign_status_field, "exact", ""]]],
                    ],
                ],
            )

        def old_buggy_notarization_pending_query():
            return json.dumps(
                [
                    "AND",
                    [
                        [notarization_field, "exact", True],
                        ["OR", [[esign_status_field, "isnull", True], [esign_status_field, "exact", ""]]],
                    ],
                ],
            )

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
            name="RentShield: restrict sensitive notices",
            order=10,
            trigger_kwargs={
                "type": WorkflowTrigger.WorkflowTriggerType.DOCUMENT_ADDED,
                "filter_custom_field_query": reason_query(
                    ["personal", "demolition", "renovation"],
                ),
            },
            trigger_tags=[rentshield_tag],
            action_kwargs={"type": WorkflowAction.WorkflowActionType.ASSIGNMENT},
            action_view_groups=[lawyer_group],
            action_change_groups=[lawyer_group],
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
                "  - Workflows #11/#12 (AI review on upload) call back into "
                f"this same server at {analyze_uploaded_url} -- if this "
                "Django process isn't reachable at that address from its own "
                "Celery worker (e.g. in a docker-compose/production "
                "topology), set PAPERLESS_RENTSHIELD_INTERNAL_URL and "
                "re-run this command.",
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
        action_view_groups=None,
        action_change_groups=None,
        enabled=True,
    ):
        if Workflow.objects.filter(name=name).exists():
            self.stdout.write(f"Skipping (already exists): {name}")
            return

        trigger = WorkflowTrigger.objects.create(**trigger_kwargs)
        if trigger_tags:
            trigger.filter_has_tags.set(trigger_tags)
        if trigger_not_tags:
            trigger.filter_has_not_tags.set(trigger_not_tags)

        if email_kwargs:
            action_kwargs = {**action_kwargs, "email": WorkflowActionEmail.objects.create(**email_kwargs)}
        if webhook_kwargs:
            action_kwargs = {**action_kwargs, "webhook": WorkflowActionWebhook.objects.create(**webhook_kwargs)}

        action = WorkflowAction.objects.create(**action_kwargs)
        if action_tags:
            action.assign_tags.set(action_tags)
        if action_view_groups:
            action.assign_view_groups.set(action_view_groups)
        if action_change_groups:
            action.assign_change_groups.set(action_change_groups)

        workflow = Workflow.objects.create(name=name, order=order, enabled=enabled)
        workflow.triggers.set([trigger])
        workflow.actions.set([action])

        self.stdout.write(self.style.SUCCESS(f"Created: {name}{'' if enabled else ' (disabled)'}"))
