from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DocumentsConfig(AppConfig):
    name = "documents"

    verbose_name = _("Documents")

    def ready(self) -> None:
        from documents.signals import document_consumption_finished
        from documents.signals import document_updated
        from documents.signals.handlers import add_inbox_tags
        from documents.signals.handlers import add_or_update_document_in_llm_index
        from documents.signals.handlers import add_to_index
        from documents.signals.handlers import run_workflows_added
        from documents.signals.handlers import run_workflows_updated
        from documents.signals.handlers import send_websocket_document_updated
        from documents.signals.handlers import set_correspondent
        from documents.signals.handlers import set_document_type
        from documents.signals.handlers import set_storage_path
        from documents.signals.handlers import set_tags
        from documents.rentshield.signals import capture_old_notary_status
        from documents.rentshield.signals import grant_organization_access
        from documents.rentshield.signals import notify_on_notary_status_change
        from documents.rentshield.login_audit import record_login

        document_consumption_finished.connect(add_inbox_tags)
        document_consumption_finished.connect(set_correspondent)
        document_consumption_finished.connect(set_document_type)
        document_consumption_finished.connect(set_tags)
        document_consumption_finished.connect(set_storage_path)
        document_consumption_finished.connect(add_to_index)
        document_consumption_finished.connect(run_workflows_added)
        document_consumption_finished.connect(add_or_update_document_in_llm_index)
        document_consumption_finished.connect(grant_organization_access)
        document_updated.connect(run_workflows_updated)
        document_updated.connect(send_websocket_document_updated)
        document_updated.connect(add_or_update_document_in_llm_index)

        from django.db.models.signals import post_save
        from django.db.models.signals import pre_save
        from documents.models import CustomFieldInstance

        pre_save.connect(capture_old_notary_status, sender=CustomFieldInstance)
        post_save.connect(notify_on_notary_status_change, sender=CustomFieldInstance)

        from django.contrib.auth.signals import user_logged_in

        user_logged_in.connect(record_login)

        import documents.schema  # noqa: F401

        AppConfig.ready(self)
