/* Builds the bilingual (EN/AR) statutory or breach notice as structured
   data — not HTML — so api/ can serialize it and vue/ can render it,
   without the legal wording ever being duplicated or drifting between
   the two. Every string below is ported verbatim from the original
   single-file prototype (legacy/index.html). */

import { ALL_REASONS, STATUTORY_REASONS, BREACH_REASONS, isBreach, noticePeriodDays } from './reasons.js';
import { formatDateEn, formatDateAr, formatExpiryEn, formatExpiryAr, fallback } from './dateRules.js';

function partyBlock(input) {
  return {
    landlord: fallback(input.landlordName, '[Landlord Full Name]'),
    tenant: fallback(input.tenantName, '[Tenant Full Name]'),
    unitNo: fallback(input.unitNo, '[Unit No.]'),
    building: fallback(input.buildingName, '[Building / Community Name]'),
    plot: fallback(input.plotNumber, '[Plot No.]'),
    ejari: fallback(input.ejariNumber, '[Ejari No.]'),
    propertyType: input.propertyType || 'Apartment'
  };
}

function buildStatutoryNotice(input) {
  const p = partyBlock(input);
  const r = STATUTORY_REASONS[input.reason];
  const noticeDateEn = formatDateEn(input.noticeDate);
  const noticeDateAr = formatDateAr(input.noticeDate);
  const expiryEn = formatExpiryEn(input.noticeDate, 365);
  const expiryAr = formatExpiryAr(input.noticeDate, 365);
  const reasonEn = r ? r.label : '[Reason for Eviction]';
  const reasonAr = r ? r.labelAr : '[سبب الإخلاء]';
  const clauseEn = r ? r.clauseEn : 'The Landlord relies on a statutory ground for eviction as recognized under Article 25 of Law No. (33) of 2008.';
  const clauseAr = r ? r.clauseAr : 'يستند المؤجر إلى سبب قانوني موجب للإخلاء وفقاً لأحكام المادة 25 من القانون رقم (33) لسنة 2008.';

  return {
    type: 'statutory',
    days: 365,
    en: {
      kicker: 'Served via Notary Public',
      title: 'Notice of Eviction',
      subtitle: 'Pursuant to Law No. (33) of 2008 Amending Law No. (26) of 2007 Regulating the Relationship Between Landlords and Tenants in the Emirate of Dubai',
      dateLabel: 'Notice Date', dateValue: noticeDateEn,
      deadlineLabel: 'Legal Expiry (365 Days)', deadlineValue: expiryEn,
      to: `${p.tenant} (the "Tenant")`,
      ejariLine: `Ejari No.: ${p.ejari}`,
      propertyLine: `Property: ${p.propertyType} No. ${p.unitNo}, ${p.building}, Plot No. ${p.plot}, Dubai, United Arab Emirates`,
      from: `${p.landlord} (the "Landlord")`,
      paragraphs: [
        'Dear Tenant,',
        `Pursuant to Article 25(2) of Law No. (33) of 2008 Amending Law No. (26) of 2007 Regulating the Relationship Between Landlords and Tenants in the Emirate of Dubai, and in accordance with the requirements of the Real Estate Regulatory Agency (RERA), the Landlord hereby serves this formal Notice of Eviction upon the Tenant occupying the above-referenced Property under Ejari Contract No. ${p.ejari}.`,
        `This Notice is served on ${noticeDateEn} and shall take legal effect after a period of not less than twelve (12) calendar months / three hundred and sixty-five (365) days from the date of service, expiring on ${expiryEn} (the "Expiry Date"), upon which date the Tenant shall vacate and hand over vacant possession of the Property to the Landlord free of occupants and belongings.`
      ],
      reasonLabel: `Reason for Eviction: ${reasonEn}`,
      reasonText: clauseEn,
      closing: "This Notice is issued in accordance with the statutory grounds for eviction recognized under UAE law. The Landlord reserves all rights available at law, including recourse to the Rental Dispute Settlement Centre (RDSC) in the event of the Tenant's non-compliance with this Notice.",
      footer: 'Served via Notary Public / Registered Mail / Court Bailiff in accordance with Article 25(3) of Law No. (33) of 2008.',
      landlordName: p.landlord, signDate: noticeDateEn
    },
    ar: {
      kicker: 'تم التبليغ عن طريق الكاتب العدل',
      title: 'إنذار عدلي بالإخلاء',
      subtitle: 'صادر بموجب القانون رقم (33) لسنة 2008 المعدل للقانون رقم (26) لسنة 2007 بشأن تنظيم العلاقة بين المؤجرين والمستأجرين في إمارة دبي',
      dateLabel: 'تاريخ الإنذار', dateValue: noticeDateAr,
      deadlineLabel: 'تاريخ الانتهاء القانوني (365 يوماً)', deadlineValue: expiryAr,
      to: `المستأجر ${p.tenant} ("المستأجر")`,
      ejariLine: `رقم عقد إيجاري: ${p.ejari}`,
      propertyLine: `العقار: ${p.propertyType} رقم ${p.unitNo}، ${p.building}، رقم القطعة ${p.plot}، دبي، الإمارات العربية المتحدة`,
      from: `المؤجر ${p.landlord} ("المؤجر")`,
      paragraphs: [
        'السيد/السيدة المستأجر المحترم،',
        `عملاً بأحكام المادة 25(2) من القانون رقم (33) لسنة 2008 المعدل للقانون رقم (26) لسنة 2007 بشأن تنظيم العلاقة بين المؤجرين والمستأجرين في إمارة دبي، ووفقاً لمتطلبات مؤسسة التنظيم العقاري (ريرا)، يقوم المؤجر بموجب هذا الإنذار بتوجيه إنذار عدلي رسمي بالإخلاء إلى المستأجر شاغل العقار المشار إليه أعلاه بموجب عقد إيجاري رقم ${p.ejari}.`,
        `صدر هذا الإنذار بتاريخ ${noticeDateAr} ويسري مفعوله القانوني بعد مدة لا تقل عن اثني عشر (12) شهراً ميلادياً / ثلاثمائة وخمسة وستين (365) يوماً من تاريخ تبليغه، وينتهي بتاريخ ${expiryAr} ("تاريخ الانتهاء")، والذي يتوجب على المستأجر بحلوله إخلاء العقار وتسليمه خالياً من الشواغل والمنقولات للمؤجر.`
      ],
      reasonLabel: `سبب الإخلاء: ${reasonAr}`,
      reasonText: clauseAr,
      closing: 'صدر هذا الإنذار وفقاً للأسباب القانونية الموجبة للإخلاء المقررة بموجب قوانين دولة الإمارات العربية المتحدة، ويحتفظ المؤجر بكافة حقوقه المقررة قانوناً، بما في ذلك حق اللجوء إلى مركز فض المنازعات الإيجارية في حال عدم امتثال المستأجر لهذا الإنذار.',
      footer: 'تم التبليغ عن طريق الكاتب العدل / البريد المسجل / محضر المحكمة وفقاً للمادة 25(3) من القانون رقم (33) لسنة 2008.',
      landlordName: p.landlord, signDate: noticeDateAr
    }
  };
}

function buildBreachNotice(input) {
  const p = partyBlock(input);
  const r = BREACH_REASONS[input.reason];
  const noticeDateEn = formatDateEn(input.noticeDate);
  const noticeDateAr = formatDateAr(input.noticeDate);
  const deadlineEn = formatExpiryEn(input.noticeDate, 30);
  const deadlineAr = formatExpiryAr(input.noticeDate, 30);
  const reasonEn = r ? r.label : '[Grounds for Breach]';
  const reasonAr = r ? r.labelAr : '[سبب المخالفة]';
  const clauseEn = r ? r.clauseEn : 'The Tenant has committed a material breach of the tenancy contract recognized under Article 25(1) of Law No. (33) of 2008.';
  const clauseAr = r ? r.clauseAr : 'ارتكب المستأجر مخالفة جوهرية لعقد الإيجار معترف بها بموجب المادة 25(1) من القانون رقم (33) لسنة 2008.';

  return {
    type: 'breach',
    days: 30,
    en: {
      kicker: 'Served via Notary Public',
      title: 'Notice of Lease Breach — 30-Day Statutory Notice',
      subtitle: 'Pursuant to Article 25(1) of Law No. (33) of 2008 Amending Law No. (26) of 2007 Regulating the Relationship Between Landlords and Tenants in the Emirate of Dubai',
      dateLabel: 'Notice Date', dateValue: noticeDateEn,
      deadlineLabel: 'Compliance Deadline (30 Days)', deadlineValue: deadlineEn,
      to: `${p.tenant} (the "Tenant")`,
      ejariLine: `Ejari No.: ${p.ejari}`,
      propertyLine: `Property: ${p.propertyType} No. ${p.unitNo}, ${p.building}, Plot No. ${p.plot}, Dubai, United Arab Emirates`,
      from: `${p.landlord} (the "Landlord")`,
      paragraphs: [
        'Dear Tenant,',
        `This Notice is served upon you pursuant to Article 25(1) of Law No. (33) of 2008 Amending Law No. (26) of 2007 Regulating the Relationship Between Landlords and Tenants in the Emirate of Dubai, which permits the Landlord to seek eviction upon thirty (30) days' written notice where the Tenant has committed a material breach of the tenancy contract registered under Ejari Contract No. ${p.ejari}, without prejudice to the Landlord's right to recover any outstanding amounts or damages.`
      ],
      reasonLabel: `Grounds for Breach: ${reasonEn}`,
      reasonText: clauseEn,
      closing: `You are hereby required to remedy the above breach and/or vacate the Property within thirty (30) days from the date of this Notice, being no later than ${deadlineEn} (the "Compliance Date"). Failure to comply may result in the Landlord initiating proceedings before the Rental Dispute Settlement Centre (RDSC) for termination of the tenancy contract and eviction, together with recovery of all amounts lawfully due.`,
      footer: 'Served via Notary Public / Registered Mail / Court Bailiff in accordance with Article 25(1) of Law No. (33) of 2008.',
      landlordName: p.landlord, signDate: noticeDateEn
    },
    ar: {
      kicker: 'تم التبليغ عن طريق الكاتب العدل',
      title: 'إنذار بمخالفة عقد الإيجار — إنذار قانوني لمدة 30 يوماً',
      subtitle: 'صادر بموجب المادة 25(1) من القانون رقم (33) لسنة 2008 المعدل للقانون رقم (26) لسنة 2007 بشأن تنظيم العلاقة بين المؤجرين والمستأجرين في إمارة دبي',
      dateLabel: 'تاريخ الإنذار', dateValue: noticeDateAr,
      deadlineLabel: 'الموعد النهائي للامتثال (30 يوماً)', deadlineValue: deadlineAr,
      to: `المستأجر ${p.tenant} ("المستأجر")`,
      ejariLine: `رقم عقد إيجاري: ${p.ejari}`,
      propertyLine: `العقار: ${p.propertyType} رقم ${p.unitNo}، ${p.building}، رقم القطعة ${p.plot}، دبي، الإمارات العربية المتحدة`,
      from: `المؤجر ${p.landlord} ("المؤجر")`,
      paragraphs: [
        'السيد/السيدة المستأجر المحترم،',
        `يوجه هذا الإنذار إليكم عملاً بأحكام المادة 25(1) من القانون رقم (33) لسنة 2008 المعدل للقانون رقم (26) لسنة 2007 بشأن تنظيم العلاقة بين المؤجرين والمستأجرين في إمارة دبي، والتي تجيز للمؤجر طلب الإخلاء بموجب إنذار كتابي مدته ثلاثون (30) يوماً في حال ارتكاب المستأجر مخالفة جوهرية لعقد الإيجار المسجل بموجب عقد إيجاري رقم ${p.ejari}، وذلك دون الإخلال بحق المؤجر في المطالبة بأي مبالغ مستحقة أو تعويضات.`
      ],
      reasonLabel: `سبب المخالفة: ${reasonAr}`,
      reasonText: clauseAr,
      closing: `يتوجب عليكم تدارك المخالفة المذكورة أعلاه و/أو إخلاء العقار خلال ثلاثين (30) يوماً من تاريخ هذا الإنذار، وذلك في موعد أقصاه ${deadlineAr} ("تاريخ الامتثال"). وفي حال عدم الامتثال، يجوز للمؤجر اللجوء إلى مركز فض المنازعات الإيجارية لطلب فسخ عقد الإيجار والإخلاء، إضافة إلى استرداد جميع المبالغ المستحقة قانوناً.`,
      footer: 'تم التبليغ عن طريق الكاتب العدل / البريد المسجل / محضر المحكمة وفقاً للمادة 25(1) من القانون رقم (33) لسنة 2008.',
      landlordName: p.landlord, signDate: noticeDateAr
    }
  };
}

export function buildNotice(input) {
  return isBreach(input.reason) ? buildBreachNotice(input) : buildStatutoryNotice(input);
}

export { ALL_REASONS, isBreach, noticePeriodDays };
