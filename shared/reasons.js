/* Statutory grounds recognized under Dubai Law No. (33) of 2008.
   Ported verbatim from the original single-file prototype (legacy/index.html)
   so the legal text served by the API and shown in the Vue app are always
   the exact same wording. */

export const STATUTORY_REASONS = {
  sale: {
    label: 'Sale of Property',
    labelAr: 'بيع العقار',
    warning: 'Note: The landlord must prove intent to sell. If sold, the notice remains valid for the new owner.',
    icon: 'tag',
    tone: 'amber',
    clauseEn: 'The Landlord intends to sell the Property. Should the Property be sold prior to the Expiry Date, this Notice shall remain valid, binding, and fully enforceable in favor of any new owner or successor-in-title of the Property.',
    clauseAr: 'يعتزم المؤجر بيع العقار. وفي حال بيع العقار قبل تاريخ الانتهاء، يظل هذا الإنذار سارياً ونافذاً وملزماً لصالح أي مالك جديد أو خلف قانوني للعقار.'
  },
  personal: {
    label: 'Personal Use / Recovery',
    labelAr: 'الاستخدام الشخصي / الاسترداد',
    warning: '⚠️ CRITICAL: Under Dubai law, if you evict for personal use, you cannot rent this property to another tenant for 2 consecutive years from the eviction date.',
    icon: 'alert-triangle',
    tone: 'red',
    clauseEn: 'The Landlord requires vacant possession of the Property for personal use and occupation by the Landlord or a first-degree relative. Pursuant to Article 25(4) of Law No. (33) of 2008, the Landlord shall not lease the Property to any new tenant for a period of two (2) consecutive years from the date of eviction, save as otherwise permitted by law.',
    clauseAr: 'يحتاج المؤجر إلى استلام العقار خالياً لغرض الاستخدام الشخصي وسكن المؤجر أو أحد أقاربه من الدرجة الأولى. وعملاً بأحكام المادة 25(4) من القانون رقم (33) لسنة 2008، يتعهد المؤجر بعدم تأجير العقار لمستأجر جديد لمدة سنتين (2) متتاليتين من تاريخ الإخلاء، إلا فيما يسمح به القانون.'
  },
  demolition: {
    label: 'Demolition',
    labelAr: 'الهدم',
    warning: 'Note: Requires technical reports or government approvals to be presented at the Rental Dispute Settlement Centre (RDSC).',
    icon: 'hammer',
    tone: 'amber',
    clauseEn: 'The Property is required to be vacated for the purpose of demolition, subject to the necessary permits and approvals obtained from the competent government authorities, which shall be presented, if required, before the Rental Dispute Settlement Centre (RDSC).',
    clauseAr: 'يستلزم إخلاء العقار لغرض هدمه، وذلك رهناً بالحصول على التصاريح والموافقات اللازمة من الجهات الحكومية المختصة، والتي سيتم تقديمها، عند الطلب، أمام مركز فض المنازعات الإيجارية.'
  },
  renovation: {
    label: 'Extensive Renovation',
    labelAr: 'التجديدات الشاملة',
    warning: 'Note: Requires technical reports or government approvals to be presented at the Rental Dispute Settlement Centre (RDSC).',
    icon: 'wrench',
    tone: 'amber',
    clauseEn: 'The Property requires extensive renovation or modification works that cannot reasonably be carried out while occupied, necessitating the Tenant\'s vacancy. This is supported by a technical report issued by a certified engineering consultant/authority, which shall be presented, if required, before the Rental Dispute Settlement Centre (RDSC).',
    clauseAr: 'يستلزم العقار أعمال ترميم أو تعديل شاملة يتعذر تنفيذها بشكل معقول أثناء إشغاله، مما يستوجب إخلاء المستأجر له. ويستند ذلك إلى تقرير فني صادر عن استشاري هندسي/جهة معتمدة، وسيتم تقديمه، عند الطلب، أمام مركز فض المنازعات الإيجارية.'
  }
};

/* 30-day lease-breach grounds under Article 25(1) — a distinct, shorter-form notice */
export const BREACH_REASONS = {
  nonpayment: {
    label: 'Non-payment of Rent',
    labelAr: 'عدم سداد الأجرة',
    warning: 'Note: This generates a 30-day breach notice under Article 25(1), not the 12-month statutory notice. Be ready to evidence the unpaid installment(s) and your prior demand for payment.',
    icon: 'banknote',
    tone: 'amber',
    clauseEn: 'The Tenant has failed to pay the agreed rental installment(s) due under the tenancy contract despite the Landlord\'s demand for payment, constituting non-payment of rent under Article 25(1)(a) of Law No. (33) of 2008.',
    clauseAr: 'تخلف المستأجر عن سداد قسط/أقساط الأجرة المتفق عليها بموجب عقد الإيجار رغم مطالبة المؤجر بالسداد، الأمر الذي يشكل عدم سداد للأجرة وفقاً للمادة 25(1)(أ) من القانون رقم (33) لسنة 2008.'
  },
  sublease: {
    label: 'Unauthorized Subleasing',
    labelAr: 'التأجير من الباطن غير المصرح به',
    warning: 'Note: This generates a 30-day breach notice under Article 25(1), not the 12-month statutory notice. Document evidence of the unauthorized sublease or short-term listing is recommended.',
    icon: 'ban',
    tone: 'amber',
    clauseEn: 'The Tenant has sublet the Property, in whole or in part — including via short-term or holiday-home rental platforms — without obtaining the Landlord\'s prior written consent, constituting unauthorized subleasing under Article 25(1)(b) of Law No. (33) of 2008.',
    clauseAr: 'قام المستأجر بتأجير العقار من الباطن، كلياً أو جزئياً، بما في ذلك عبر منصات التأجير قصيرة الأجل أو بيوت العطلات، دون الحصول على موافقة خطية مسبقة من المؤجر، الأمر الذي يشكل تأجيراً من الباطن غير مصرح به وفقاً للمادة 25(1)(ب) من القانون رقم (33) لسنة 2008.'
  }
};

export const ALL_REASONS = { ...STATUTORY_REASONS, ...BREACH_REASONS };
export const BREACH_KEYS = ['nonpayment', 'sublease'];

export function isBreach(reasonKey) {
  return BREACH_KEYS.includes(reasonKey);
}

export function noticePeriodDays(reasonKey) {
  return isBreach(reasonKey) ? 30 : 365;
}
