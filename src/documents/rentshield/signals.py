# Reacts to the Real Notary Public human fulfiller's manual edit of
# "RentShield: Notary Public Status" through paperless-ngx's own generic
# document editor -- there is no bespoke completion endpoint for her to
# call instead (see custom_fields.py's comment above
# AWAITING_NOTARY_PUBLIC_TAG_NAME), so a plain Django signal on
# CustomFieldInstance is the only hook available for noticing that
# transition. A native paperless-ngx Workflow can't do this instead:
# WorkflowActionEmail's recipient is a fixed string set at workflow-
# config time, and its Jinja2 template only exposes a fixed allowlist of
# Document attributes (documents/templating/workflows.py) -- neither can
# reach a per-document CustomField value like landlord_email, which
# differs on every notice.
from __future__ import annotations

from django.db import transaction

from documents.models import CustomFieldInstance

_TERMINAL_STATUSES = {"completed", "rejected"}


def grant_organization_access(sender, document, **kwargs) -> None:
    """document_consumption_finished (2026-09-22, cross-tenant isolation
    -- see /home/giova/.claude/plans/synchronous-finding-storm.md) --
    reuses documents/permissions.py's own set_permissions_for_object,
    the same guardian-backed mechanism paperless-ngx's own document-
    sharing UI already uses, instead of inventing a second one. This
    file's own header comment on why the old Lawyer role's object-
    permission-grant machinery was "this project's single biggest
    source of real bugs" is exactly why this stays this small: ONE
    grant, to ONE stable group (the owner's Organization.group, if
    any), no per-user computation, no removal/undo logic, called
    exactly once per document at the same point add_inbox_tags/
    set_correspondent/etc. already run. A document whose owner has no
    Organization (every individual self-serve account) hits the early
    return and nothing changes for them -- confirmed this is the
    overwhelmingly common case, not the exception.

    2026-09-22: also writes one RentShieldPermissionAuditLog row per
    grant, in the same transaction, for compliance review -- same
    "queryable DB rows, not log-pipeline lines" precedent as
    RentShieldLoginLog."""
    from documents.rentshield.roles import get_user_organization

    if document.owner_id is None:
        return
    organization = get_user_organization(document.owner)
    if organization is None:
        return

    from documents.models import RentShieldPermissionAuditLog
    from documents.permissions import set_permissions_for_object

    with transaction.atomic():
        set_permissions_for_object(
            {
                "view": {"groups": [organization.group_id]},
                "change": {"groups": [organization.group_id]},
            },
            document,
            merge=True,
        )
        RentShieldPermissionAuditLog.objects.create(
            action=RentShieldPermissionAuditLog.ACTION_ORGANIZATION_GRANT,
            document=document,
            organization=organization,
            details=(
                f"Automatically granted view/change on document {document.pk} "
                f"to organization {organization.name!r}'s group "
                f"(document_consumption_finished, post-consume sync)."
            ),
        )


def capture_old_notary_status(sender, instance, **kwargs) -> None:
    """pre_save: stashes the value this row had before this save (None
    for a brand-new row) -- post_save below compares against it so the
    notification only fires on the transition INTO a terminal status,
    not on every resave once a notice is already completed/rejected."""
    if instance.pk is None:
        instance._rentshield_old_value = None
        return
    previous = CustomFieldInstance.objects.filter(pk=instance.pk).first()
    instance._rentshield_old_value = previous.value if previous else None


def notify_on_notary_status_change(sender, instance, created, **kwargs) -> None:
    from documents.rentshield.custom_fields import key_to_id_map

    notary_status_field_id = key_to_id_map().get("notary_status")
    if notary_status_field_id is None or instance.field_id != notary_status_field_id:
        return

    new_value = instance.value
    old_value = getattr(instance, "_rentshield_old_value", None)
    if new_value not in _TERMINAL_STATUSES or new_value == old_value:
        return

    # Dispatched as a Celery task via documents.tasks.notify_notice_served_task,
    # not run inline here -- verified for real that writing a second
    # CustomFieldInstance (served_date) from within this signal, even
    # deferred to transaction.on_commit(), does not reliably persist
    # through the real DRF PATCH request path the notary officer's
    # browser uses (visible to its own connection right after the write,
    # silently gone moments later -- some ambient transaction state from
    # the enclosing request appears to roll it back, though nothing
    # raises). A Celery task gets a fresh connection/transaction with
    # nothing ambient to interact with, sidestepping that entirely --
    # same reasoning documents/tasks.py's run_ai_review_task/
    # run_notarization_task already give for keeping this class of work
    # off the request's own transaction.
    document_id = instance.document_id

    def _dispatch() -> None:
        from documents.tasks import notify_notice_served_task

        notify_notice_served_task.delay(document_id, new_value)

    transaction.on_commit(_dispatch)
