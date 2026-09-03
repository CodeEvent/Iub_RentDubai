from rest_framework import serializers

from rentshield.constants import ALL_REASONS
from rentshield.constants import notice_period_days
from rentshield.models import Notice
from rentshield.notice_builder import build_notice
from rentshield.pricing import calculate_total
from rentshield.services import notice_to_builder_input


class NoticeSerializer(serializers.ModelSerializer):
    reason_label = serializers.SerializerMethodField()
    notice_period_days = serializers.SerializerMethodField()
    total_price_aed = serializers.SerializerMethodField()
    document_id = serializers.IntegerField(source="document.id", read_only=True, allow_null=True)

    class Meta:
        model = Notice
        fields = [
            "id", "landlord_name", "landlord_email", "tenant_name",
            "property_type", "unit_no", "building_name", "plot_number",
            "ejari_number", "notice_date", "reason", "reason_label",
            "notice_period_days", "add_notarization", "add_ai_review",
            "total_price_aed", "consume_task_id", "document_id", "created_at",
        ]
        read_only_fields = ["id", "consume_task_id", "document_id", "created_at"]

    def get_reason_label(self, obj: Notice) -> str:
        reason = ALL_REASONS.get(obj.reason)
        return reason["label"] if reason else obj.reason

    def get_notice_period_days(self, obj: Notice) -> int:
        return notice_period_days(obj.reason)

    def get_total_price_aed(self, obj: Notice) -> int:
        return calculate_total({"notarization": obj.add_notarization, "ai_review": obj.add_ai_review})


class NoticeDetailSerializer(NoticeSerializer):
    document = serializers.SerializerMethodField()

    class Meta(NoticeSerializer.Meta):
        fields = NoticeSerializer.Meta.fields + ["document"]

    def get_document(self, obj: Notice) -> dict:
        return build_notice(notice_to_builder_input(obj))
