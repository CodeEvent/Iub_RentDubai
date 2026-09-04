import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from documents.models import SavedView
from documents.models import SavedViewFilterRule
from documents.models import Tag
from documents.models import UiSettings
from documents.rentshield.custom_fields import AI_REVIEWED_TAG_NAME
from documents.rentshield.custom_fields import NEEDS_AI_REVIEW_TAG_NAME
from documents.rentshield.custom_fields import RENTSHIELD_TAG_NAME
from documents.rentshield.custom_fields import TENANCY_CONTRACT_TAG_NAME
from documents.rentshield.custom_fields import key_to_id_map

User = get_user_model()

STATUTORY_REASONS = ["sale", "personal", "demolition", "renovation"]
BREACH_REASONS = ["nonpayment", "sublease"]

# SavedViewFilterRule.rule_type values (documents/models.py SavedViewFilterRule.RULE_TYPES)
RULE_HAS_TAG = 6
RULE_DOES_NOT_HAVE_TAG = 17
RULE_CUSTOM_FIELDS_QUERY = 42


class Command(BaseCommand):
    help = (
        "Idempotently creates 8 RentShield paperless-ngx Saved Views "
        "(see README.md 'Dashboards' section) and pins them to show on "
        "the Dashboard/sidebar for every existing superuser -- "
        "paperless-ngx's own dashboard-widget mechanism, no custom "
        "dashboard UI. Safe to re-run; skips views already created by "
        "name, and only ADDS visibility for superusers who don't already "
        "have that view's id in their dashboard/sidebar list (so manually "
        "hiding a view again afterward sticks)."
    )

    def handle(self, *args, **options):
        ids = key_to_id_map()
        missing = [k for k in ("reason", "add_notarization", "esign_status", "ai_review_findings_count") if k not in ids]
        if missing:
            self.stderr.write(
                self.style.ERROR(
                    f"Missing RentShield custom fields: {missing}. Run `manage.py migrate` first.",
                ),
            )
            return

        reason_field = ids["reason"]
        notarization_field = ids["add_notarization"]
        esign_status_field = ids["esign_status"]
        findings_count_field = ids["ai_review_findings_count"]

        rentshield_tag = Tag.objects.filter(name=RENTSHIELD_TAG_NAME).first()
        needs_ai_review_tag = Tag.objects.filter(name=NEEDS_AI_REVIEW_TAG_NAME).first()
        ai_reviewed_tag = Tag.objects.filter(name=AI_REVIEWED_TAG_NAME).first()
        tenancy_contract_tag = Tag.objects.filter(name=TENANCY_CONTRACT_TAG_NAME).first()
        if not rentshield_tag:
            self.stderr.write(
                self.style.ERROR(
                    "RentShield Notice tag doesn't exist yet -- run "
                    "`manage.py create_rentshield_workflows` first (it "
                    "bootstraps the tags this command's views filter on).",
                ),
            )
            return

        def reason_query(keys):
            return json.dumps([reason_field, "in", keys])

        def notarization_pending_query():
            return json.dumps(
                [
                    "AND",
                    [
                        [notarization_field, "exact", True],
                        ["OR", [[esign_status_field, "isnull", True], [esign_status_field, "exact", ""]]],
                    ],
                ],
            )

        view_ids = []

        view_ids.append(
            self._create_view(
                name="RentShield: All Notices",
                icon=SavedView.Icon.JOURNALS,
                rules=[(RULE_HAS_TAG, rentshield_tag.id)],
                sort_field="added",
                sort_reverse=True,
            ),
        )
        view_ids.append(
            self._create_view(
                name="RentShield: Statutory Notices (365-day)",
                icon=SavedView.Icon.CALENDAR,
                rules=[(RULE_CUSTOM_FIELDS_QUERY, reason_query(STATUTORY_REASONS))],
                sort_field="added",
                sort_reverse=True,
            ),
        )
        view_ids.append(
            self._create_view(
                name="RentShield: Breach Notices (30-day)",
                icon=SavedView.Icon.EXCLAMATION_TRIANGLE,
                rules=[(RULE_CUSTOM_FIELDS_QUERY, reason_query(BREACH_REASONS))],
                sort_field="added",
                sort_reverse=True,
            ),
        )
        view_ids.append(
            self._create_view(
                name="RentShield: Notarization Pending",
                icon=SavedView.Icon.FILE_EARMARK_LOCK,
                rules=[(RULE_CUSTOM_FIELDS_QUERY, notarization_pending_query())],
                sort_field="added",
                sort_reverse=True,
            ),
        )
        view_ids.append(
            self._create_view(
                name="RentShield: Sensitive Notices (Legal Review)",
                icon=SavedView.Icon.SAFE,
                rules=[
                    (RULE_CUSTOM_FIELDS_QUERY, reason_query(["personal", "demolition", "renovation"])),
                ],
                sort_field="added",
                sort_reverse=True,
            ),
        )
        if needs_ai_review_tag:
            view_ids.append(
                self._create_view(
                    name="RentShield: Needs AI Review",
                    icon=SavedView.Icon.STARS,
                    rules=[(RULE_HAS_TAG, needs_ai_review_tag.id)],
                    sort_field="added",
                    sort_reverse=True,
                ),
            )
        if tenancy_contract_tag and ai_reviewed_tag:
            view_ids.append(
                self._create_view(
                    name="RentShield: Contracts Under Review",
                    icon=SavedView.Icon.CLOCK_HISTORY,
                    rules=[
                        (RULE_HAS_TAG, tenancy_contract_tag.id),
                        (RULE_DOES_NOT_HAVE_TAG, ai_reviewed_tag.id),
                    ],
                    sort_field="added",
                    sort_reverse=True,
                ),
            )
        view_ids.append(
            self._create_view(
                name="RentShield: Non-Compliant Contracts",
                icon=SavedView.Icon.EXCLAMATION_TRIANGLE,
                rules=[(RULE_CUSTOM_FIELDS_QUERY, json.dumps([findings_count_field, "gte", 1]))],
                sort_field="added",
                sort_reverse=True,
            ),
        )

        view_ids = [v for v in view_ids if v is not None]
        added_for = []
        for user in User.objects.filter(is_superuser=True):
            if self._pin_to_dashboard(user, view_ids):
                added_for.append(user.username)

        self.stdout.write(self.style.SUCCESS("RentShield dashboard views created/verified."))
        if added_for:
            self.stdout.write(f"Pinned to dashboard + sidebar for: {', '.join(added_for)}")
        self.stdout.write(
            self.style.WARNING(
                "Dashboard/sidebar visibility is per-user (paperless-ngx's own "
                "UiSettings, not a SavedView field) -- only existing superusers "
                "got these pinned automatically. Any other account (once "
                "task 5's tenant/notary/lawyer/owner roles exist) needs its "
                "own visibility set the same way, or a user can star/unstar "
                "any view themselves from Saved Views in the sidebar.",
            ),
        )

    def _create_view(self, *, name, icon, rules, sort_field, sort_reverse):
        view, created = SavedView.objects.get_or_create(
            name=name,
            defaults={
                "icon": icon,
                "sort_field": sort_field,
                "sort_reverse": sort_reverse,
            },
        )
        if not created:
            self.stdout.write(f"Skipping (already exists): {name}")
            return view.id

        for rule_type, value in rules:
            SavedViewFilterRule.objects.create(saved_view=view, rule_type=rule_type, value=str(value))

        self.stdout.write(self.style.SUCCESS(f"Created: {name}"))
        return view.id

    def _pin_to_dashboard(self, user, view_ids) -> bool:
        ui_settings, _ = UiSettings.objects.get_or_create(user=user, defaults={"settings": {}})
        current = ui_settings.settings if isinstance(ui_settings.settings, dict) else {}
        current = dict(current)
        saved_views_settings = dict(current.get("saved_views") or {})

        dashboard_ids = {int(v) for v in saved_views_settings.get("dashboard_views_visible_ids", []) if str(v).isdigit()}
        sidebar_ids = {int(v) for v in saved_views_settings.get("sidebar_views_visible_ids", []) if str(v).isdigit()}

        before = (frozenset(dashboard_ids), frozenset(sidebar_ids))
        dashboard_ids.update(view_ids)
        sidebar_ids.update(view_ids)
        after = (frozenset(dashboard_ids), frozenset(sidebar_ids))

        if before == after:
            return False

        saved_views_settings["dashboard_views_visible_ids"] = sorted(dashboard_ids)
        saved_views_settings["sidebar_views_visible_ids"] = sorted(sidebar_ids)
        current["saved_views"] = saved_views_settings
        ui_settings.settings = current
        ui_settings.save(update_fields=["settings"])
        return True
