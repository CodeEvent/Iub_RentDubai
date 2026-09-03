# Builds the bilingual (EN/AR) statutory or breach notice as a plain
# dict — not HTML — mirroring legacy-v1/shared/noticeTemplate.js's
# structured-data approach so consumers (the DRF serializer, pdf.py)
# render their own presentation instead of parsing markup. Every string
# below is ported 1:1 from that file.
from __future__ import annotations

from rentshield.constants import BREACH_REASONS
from rentshield.constants import STATUTORY_REASONS
from rentshield.constants import is_breach
from rentshield.dates import fallback
from rentshield.dates import format_date_ar
from rentshield.dates import format_date_en
from rentshield.dates import format_expiry_ar
from rentshield.dates import format_expiry_en


def _party_block(input_data: dict) -> dict:
    return {
        "landlord": fallback(input_data.get("landlord_name"), "[Landlord Full Name]"),
        "tenant": fallback(input_data.get("tenant_name"), "[Tenant Full Name]"),
        "unit_no": fallback(input_data.get("unit_no"), "[Unit No.]"),
        "building": fallback(input_data.get("building_name"), "[Building / Community Name]"),
        "plot": fallback(input_data.get("plot_number"), "[Plot No.]"),
        "ejari": fallback(input_data.get("ejari_number"), "[Ejari No.]"),
        "property_type": input_data.get("property_type") or "Apartment",
    }


def _build_statutory_notice(input_data: dict) -> dict:
    p = _party_block(input_data)
    r = STATUTORY_REASONS.get(input_data.get("reason"))
    notice_date_en = format_date_en(input_data.get("notice_date"))
    notice_date_ar = format_date_ar(input_data.get("notice_date"))
    expiry_en = format_expiry_en(input_data.get("notice_date"), 365)
    expiry_ar = format_expiry_ar(input_data.get("notice_date"), 365)
    reason_en = r["label"] if r else "[Reason for Eviction]"
    reason_ar = r["label_ar"] if r else "[سبب الإخلاء]"
    clause_en = r["clause_en"] if r else (
        "The Landlord relies on a statutory ground for eviction as recognized under "
        "Article 25 of Law No. (33) of 2008."
    )
    clause_ar = r["clause_ar"] if r else (
        "يستند المؤجر إلى سبب قانوني موجب للإخلاء وفقاً لأحكام المادة 25 من القانون رقم "
        "(33) لسنة 2008."
    )

    return {
        "type": "statutory",
        "days": 365,
        "en": {
            "kicker": "Served via Notary Public",
            "title": "Notice of Eviction",
            "subtitle": (
                "Pursuant to Law No. (33) of 2008 Amending Law No. (26) of 2007 Regulating "
                "the Relationship Between Landlords and Tenants in the Emirate of Dubai"
            ),
            "date_label": "Notice Date", "date_value": notice_date_en,
            "deadline_label": "Legal Expiry (365 Days)", "deadline_value": expiry_en,
            "to": f'{p["tenant"]} (the "Tenant")',
            "ejari_line": f'Ejari No.: {p["ejari"]}',
            "property_line": (
                f'Property: {p["property_type"]} No. {p["unit_no"]}, {p["building"]}, '
                f'Plot No. {p["plot"]}, Dubai, United Arab Emirates'
            ),
            "from": f'{p["landlord"]} (the "Landlord")',
            "paragraphs": [
                "Dear Tenant,",
                (
                    f'Pursuant to Article 25(2) of Law No. (33) of 2008 Amending Law No. (26) of '
                    f'2007 Regulating the Relationship Between Landlords and Tenants in the Emirate '
                    f'of Dubai, and in accordance with the requirements of the Real Estate Regulatory '
                    f'Agency (RERA), the Landlord hereby serves this formal Notice of Eviction upon '
                    f'the Tenant occupying the above-referenced Property under Ejari Contract No. '
                    f'{p["ejari"]}.'
                ),
                (
                    f'This Notice is served on {notice_date_en} and shall take legal effect after a '
                    f'period of not less than twelve (12) calendar months / three hundred and '
                    f'sixty-five (365) days from the date of service, expiring on {expiry_en} (the '
                    f'"Expiry Date"), upon which date the Tenant shall vacate and hand over vacant '
                    f'possession of the Property to the Landlord free of occupants and belongings.'
                ),
            ],
            "reason_label": f"Reason for Eviction: {reason_en}",
            "reason_text": clause_en,
            "closing": (
                "This Notice is issued in accordance with the statutory grounds for eviction "
                "recognized under UAE law. The Landlord reserves all rights available at law, "
                "including recourse to the Rental Dispute Settlement Centre (RDSC) in the event of "
                "the Tenant's non-compliance with this Notice."
            ),
            "footer": (
                "Served via Notary Public / Registered Mail / Court Bailiff in accordance with "
                "Article 25(3) of Law No. (33) of 2008."
            ),
            "landlord_name": p["landlord"], "sign_date": notice_date_en,
        },
        "ar": {
            "kicker": "تم التبليغ عن طريق الكاتب العدل",
            "title": "إنذار عدلي بالإخلاء",
            "subtitle": (
                "صادر بموجب القانون رقم (33) لسنة 2008 المعدل للقانون رقم (26) لسنة 2007 بشأن تنظيم "
                "العلاقة بين المؤجرين والمستأجرين في إمارة دبي"
            ),
            "date_label": "تاريخ الإنذار", "date_value": notice_date_ar,
            "deadline_label": "تاريخ الانتهاء القانوني (365 يوماً)", "deadline_value": expiry_ar,
            "to": f'المستأجر {p["tenant"]} ("المستأجر")',
            "ejari_line": f'رقم عقد إيجاري: {p["ejari"]}',
            "property_line": (
                f'العقار: {p["property_type"]} رقم {p["unit_no"]}، {p["building"]}، رقم القطعة '
                f'{p["plot"]}، دبي، الإمارات العربية المتحدة'
            ),
            "from": f'المؤجر {p["landlord"]} ("المؤجر")',
            "paragraphs": [
                "السيد/السيدة المستأجر المحترم،",
                (
                    f'عملاً بأحكام المادة 25(2) من القانون رقم (33) لسنة 2008 المعدل للقانون رقم (26) '
                    f'لسنة 2007 بشأن تنظيم العلاقة بين المؤجرين والمستأجرين في إمارة دبي، ووفقاً '
                    f'لمتطلبات مؤسسة التنظيم العقاري (ريرا)، يقوم المؤجر بموجب هذا الإنذار بتوجيه '
                    f'إنذار عدلي رسمي بالإخلاء إلى المستأجر شاغل العقار المشار إليه أعلاه بموجب عقد '
                    f'إيجاري رقم {p["ejari"]}.'
                ),
                (
                    f'صدر هذا الإنذار بتاريخ {notice_date_ar} ويسري مفعوله القانوني بعد مدة لا تقل عن '
                    f'اثني عشر (12) شهراً ميلادياً / ثلاثمائة وخمسة وستين (365) يوماً من تاريخ تبليغه، '
                    f'وينتهي بتاريخ {expiry_ar} ("تاريخ الانتهاء")، والذي يتوجب على المستأجر بحلوله '
                    f'إخلاء العقار وتسليمه خالياً من الشواغل والمنقولات للمؤجر.'
                ),
            ],
            "reason_label": f"سبب الإخلاء: {reason_ar}",
            "reason_text": clause_ar,
            "closing": (
                "صدر هذا الإنذار وفقاً للأسباب القانونية الموجبة للإخلاء المقررة بموجب قوانين دولة "
                "الإمارات العربية المتحدة، ويحتفظ المؤجر بكافة حقوقه المقررة قانوناً، بما في ذلك حق "
                "اللجوء إلى مركز فض المنازعات الإيجارية في حال عدم امتثال المستأجر لهذا الإنذار."
            ),
            "footer": (
                "تم التبليغ عن طريق الكاتب العدل / البريد المسجل / محضر المحكمة وفقاً للمادة 25(3) من "
                "القانون رقم (33) لسنة 2008."
            ),
            "landlord_name": p["landlord"], "sign_date": notice_date_ar,
        },
    }


def _build_breach_notice(input_data: dict) -> dict:
    p = _party_block(input_data)
    r = BREACH_REASONS.get(input_data.get("reason"))
    notice_date_en = format_date_en(input_data.get("notice_date"))
    notice_date_ar = format_date_ar(input_data.get("notice_date"))
    deadline_en = format_expiry_en(input_data.get("notice_date"), 30)
    deadline_ar = format_expiry_ar(input_data.get("notice_date"), 30)
    reason_en = r["label"] if r else "[Grounds for Breach]"
    reason_ar = r["label_ar"] if r else "[سبب المخالفة]"
    clause_en = r["clause_en"] if r else (
        "The Tenant has committed a material breach of the tenancy contract recognized under "
        "Article 25(1) of Law No. (33) of 2008."
    )
    clause_ar = r["clause_ar"] if r else (
        "ارتكب المستأجر مخالفة جوهرية لعقد الإيجار معترف بها بموجب المادة 25(1) من القانون رقم "
        "(33) لسنة 2008."
    )

    return {
        "type": "breach",
        "days": 30,
        "en": {
            "kicker": "Served via Notary Public",
            "title": "Notice of Lease Breach — 30-Day Statutory Notice",
            "subtitle": (
                "Pursuant to Article 25(1) of Law No. (33) of 2008 Amending Law No. (26) of 2007 "
                "Regulating the Relationship Between Landlords and Tenants in the Emirate of Dubai"
            ),
            "date_label": "Notice Date", "date_value": notice_date_en,
            "deadline_label": "Compliance Deadline (30 Days)", "deadline_value": deadline_en,
            "to": f'{p["tenant"]} (the "Tenant")',
            "ejari_line": f'Ejari No.: {p["ejari"]}',
            "property_line": (
                f'Property: {p["property_type"]} No. {p["unit_no"]}, {p["building"]}, '
                f'Plot No. {p["plot"]}, Dubai, United Arab Emirates'
            ),
            "from": f'{p["landlord"]} (the "Landlord")',
            "paragraphs": [
                "Dear Tenant,",
                (
                    f'This Notice is served upon you pursuant to Article 25(1) of Law No. (33) of '
                    f'2008 Amending Law No. (26) of 2007 Regulating the Relationship Between Landlords '
                    f'and Tenants in the Emirate of Dubai, which permits the Landlord to seek eviction '
                    f'upon thirty (30) days\' written notice where the Tenant has committed a material '
                    f'breach of the tenancy contract registered under Ejari Contract No. {p["ejari"]}, '
                    f'without prejudice to the Landlord\'s right to recover any outstanding amounts or '
                    f'damages.'
                ),
            ],
            "reason_label": f"Grounds for Breach: {reason_en}",
            "reason_text": clause_en,
            "closing": (
                f'You are hereby required to remedy the above breach and/or vacate the Property '
                f'within thirty (30) days from the date of this Notice, being no later than '
                f'{deadline_en} (the "Compliance Date"). Failure to comply may result in the Landlord '
                f'initiating proceedings before the Rental Dispute Settlement Centre (RDSC) for '
                f'termination of the tenancy contract and eviction, together with recovery of all '
                f'amounts lawfully due.'
            ),
            "footer": (
                "Served via Notary Public / Registered Mail / Court Bailiff in accordance with "
                "Article 25(1) of Law No. (33) of 2008."
            ),
            "landlord_name": p["landlord"], "sign_date": notice_date_en,
        },
        "ar": {
            "kicker": "تم التبليغ عن طريق الكاتب العدل",
            "title": "إنذار بمخالفة عقد الإيجار — إنذار قانوني لمدة 30 يوماً",
            "subtitle": (
                "صادر بموجب المادة 25(1) من القانون رقم (33) لسنة 2008 المعدل للقانون رقم (26) لسنة "
                "2007 بشأن تنظيم العلاقة بين المؤجرين والمستأجرين في إمارة دبي"
            ),
            "date_label": "تاريخ الإنذار", "date_value": notice_date_ar,
            "deadline_label": "الموعد النهائي للامتثال (30 يوماً)", "deadline_value": deadline_ar,
            "to": f'المستأجر {p["tenant"]} ("المستأجر")',
            "ejari_line": f'رقم عقد إيجاري: {p["ejari"]}',
            "property_line": (
                f'العقار: {p["property_type"]} رقم {p["unit_no"]}، {p["building"]}، رقم القطعة '
                f'{p["plot"]}، دبي، الإمارات العربية المتحدة'
            ),
            "from": f'المؤجر {p["landlord"]} ("المؤجر")',
            "paragraphs": [
                "السيد/السيدة المستأجر المحترم،",
                (
                    f'يوجه هذا الإنذار إليكم عملاً بأحكام المادة 25(1) من القانون رقم (33) لسنة 2008 '
                    f'المعدل للقانون رقم (26) لسنة 2007 بشأن تنظيم العلاقة بين المؤجرين والمستأجرين في '
                    f'إمارة دبي، والتي تجيز للمؤجر طلب الإخلاء بموجب إنذار كتابي مدته ثلاثون (30) يوماً '
                    f'في حال ارتكاب المستأجر مخالفة جوهرية لعقد الإيجار المسجل بموجب عقد إيجاري رقم '
                    f'{p["ejari"]}، وذلك دون الإخلال بحق المؤجر في المطالبة بأي مبالغ مستحقة أو تعويضات.'
                ),
            ],
            "reason_label": f"سبب المخالفة: {reason_ar}",
            "reason_text": clause_ar,
            "closing": (
                f'يتوجب عليكم تدارك المخالفة المذكورة أعلاه و/أو إخلاء العقار خلال ثلاثين (30) يوماً '
                f'من تاريخ هذا الإنذار، وذلك في موعد أقصاه {deadline_ar} ("تاريخ الامتثال"). وفي حال '
                f'عدم الامتثال، يجوز للمؤجر اللجوء إلى مركز فض المنازعات الإيجارية لطلب فسخ عقد الإيجار '
                f'والإخلاء، إضافة إلى استرداد جميع المبالغ المستحقة قانوناً.'
            ),
            "footer": (
                "تم التبليغ عن طريق الكاتب العدل / البريد المسجل / محضر المحكمة وفقاً للمادة 25(1) من "
                "القانون رقم (33) لسنة 2008."
            ),
            "landlord_name": p["landlord"], "sign_date": notice_date_ar,
        },
    }


def build_notice(input_data: dict) -> dict:
    return _build_breach_notice(input_data) if is_breach(input_data.get("reason")) else _build_statutory_notice(input_data)
