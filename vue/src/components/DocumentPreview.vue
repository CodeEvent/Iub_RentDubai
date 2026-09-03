<script setup>
import { ref, computed } from 'vue';
import { FileText, DownloadCloud, Save, Loader2, CheckCircle2 } from '@lucide/vue';
import { useNoticeStore } from '../stores/notice.js';

const store = useNoticeStore();
const mobileLang = ref('en');

const doc = computed(() => store.document);

async function handleSave() {
  try {
    await store.saveNotice();
  } catch {
    // store.saveError already holds the message for the template to show
  }
}

function handleDownloadClick() {
  if (!store.isReadyToSave) {
    alert('Please complete Landlord, Tenant, Notice Date and Reason before generating your document.');
    return;
  }
  store.openPaymentModal();
}
</script>

<template>
  <div class="lg:sticky lg:top-24 space-y-4">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <FileText class="w-4 h-4 text-slate-500" />
        <h2 class="text-sm font-bold text-slate-700 uppercase tracking-wide">Live Legal Document Preview</h2>
      </div>
      <span class="lg:hidden inline-flex bg-slate-100 rounded-lg p-1 text-xs font-semibold">
        <button
          class="px-3.5 py-2 rounded-md transition"
          :class="mobileLang === 'en' ? 'bg-white shadow-sm text-slate-900' : 'text-slate-400'"
          @click="mobileLang = 'en'"
        >EN</button>
        <button
          class="px-3.5 py-2 rounded-md transition"
          :class="mobileLang === 'ar' ? 'bg-white shadow-sm text-slate-900' : 'text-slate-400'"
          @click="mobileLang = 'ar'"
        >AR</button>
      </span>
    </div>

    <div class="relative rounded-2xl border border-slate-200 shadow-premium overflow-hidden bg-white">
      <div v-if="!store.paid" class="watermark">
        <span>SAMPLE &middot; UNPAID PREVIEW</span>
      </div>

      <div class="doc-card">
        <!-- English -->
        <div class="p-6 sm:p-8" :class="{ 'hidden lg:block': mobileLang !== 'en' }">
          <div class="text-[13px] leading-relaxed text-slate-800">
            <div class="text-center mb-6">
              <p class="text-[10px] tracking-[0.2em] text-slate-400 font-semibold uppercase mb-1">{{ doc.en.kicker }}</p>
              <h3 class="text-base font-extrabold text-slate950 uppercase tracking-tight">{{ doc.en.title }}</h3>
              <p class="text-[11px] text-slate-500 mt-1">{{ doc.en.subtitle }}</p>
            </div>

            <div class="grid grid-cols-2 gap-3 mb-5 text-[11px]">
              <div class="bg-slate-50 rounded-lg px-3 py-2.5 border border-slate-100">
                <p class="text-slate-400 font-semibold uppercase text-[9px] mb-0.5">{{ doc.en.dateLabel }}</p>
                <p class="font-bold text-slate-900">{{ doc.en.dateValue }}</p>
              </div>
              <div class="bg-slate-50 rounded-lg px-3 py-2.5 border border-slate-100">
                <p class="text-slate-400 font-semibold uppercase text-[9px] mb-0.5">{{ doc.en.deadlineLabel }}</p>
                <p class="font-bold text-emerald-700">{{ doc.en.deadlineValue }}</p>
              </div>
            </div>

            <p class="mb-3"><strong>To:</strong> {{ doc.en.to }}<br>
            <strong>{{ doc.en.ejariLine }}</strong><br>
            {{ doc.en.propertyLine }}</p>
            <p class="mb-3"><strong>From:</strong> {{ doc.en.from }}</p>

            <div v-if="!store.paid" class="flex items-center gap-2 bg-slate950/[.04] border border-dashed border-slate-300 rounded-lg px-3 py-2 mb-4 text-[10.5px] text-slate-500 font-semibold">
              🔒 Full operative legal text &amp; signature blocks unlock after payment.
            </div>
            <div :class="{ 'blur-doc': !store.paid }">
              <p v-for="(para, i) in doc.en.paragraphs" :key="i" class="mb-3 text-justify">{{ para }}</p>
              <p class="mb-1 font-bold">{{ doc.en.reasonLabel }}</p>
              <p class="mb-3 text-justify">{{ doc.en.reasonText }}</p>
              <p class="mb-3 text-justify">{{ doc.en.closing }}</p>
              <div class="mt-8 grid grid-cols-2 gap-6 text-[11px]">
                <div>
                  <p class="text-slate-400 mb-6">Landlord Signature</p>
                  <div class="border-t border-slate-300 pt-1.5">
                    <p class="font-semibold text-slate-800">{{ doc.en.landlordName }}</p>
                    <p class="text-slate-400">{{ doc.en.signDate }}</p>
                  </div>
                </div>
                <div>
                  <p class="text-slate-400 mb-6">Notary Public Attestation</p>
                  <div class="border-t border-slate-300 pt-1.5"><p class="font-semibold text-slate-300">&mdash;</p></div>
                </div>
              </div>
              <p class="text-[10px] text-slate-400 mt-6 italic">{{ doc.en.footer }}</p>
            </div>
          </div>
        </div>

        <!-- Arabic -->
        <div class="p-6 sm:p-8 border-t-2 border-dashed border-slate-200 lg:border-t-0 lg:border-l-2" :class="{ 'hidden lg:block': mobileLang !== 'ar' }">
          <div class="arabic-text text-[13px] leading-loose text-slate-800">
            <div class="text-center mb-6">
              <p class="text-[10px] tracking-widest text-slate-400 font-semibold mb-1">{{ doc.ar.kicker }}</p>
              <h3 class="text-base font-extrabold text-slate950">{{ doc.ar.title }}</h3>
              <p class="text-[11px] text-slate-500 mt-1">{{ doc.ar.subtitle }}</p>
            </div>

            <div class="grid grid-cols-2 gap-3 mb-5 text-[11px]">
              <div class="bg-slate-50 rounded-lg px-3 py-2.5 border border-slate-100">
                <p class="text-slate-400 font-semibold text-[9px] mb-0.5">{{ doc.ar.dateLabel }}</p>
                <p class="font-bold text-slate-900">{{ doc.ar.dateValue }}</p>
              </div>
              <div class="bg-slate-50 rounded-lg px-3 py-2.5 border border-slate-100">
                <p class="text-slate-400 font-semibold text-[9px] mb-0.5">{{ doc.ar.deadlineLabel }}</p>
                <p class="font-bold text-emerald-700">{{ doc.ar.deadlineValue }}</p>
              </div>
            </div>

            <p class="mb-3"><strong>إلى:</strong> {{ doc.ar.to }}<br>
            <strong>{{ doc.ar.ejariLine }}</strong><br>
            {{ doc.ar.propertyLine }}</p>
            <p class="mb-3"><strong>من:</strong> {{ doc.ar.from }}</p>

            <div v-if="!store.paid" class="flex items-center gap-2 bg-slate950/[.04] border border-dashed border-slate-300 rounded-lg px-3 py-2 mb-4 text-[10.5px] text-slate-500 font-semibold">
              🔒 يتم فك قفل النص القانوني الكامل بعد إتمام الدفع.
            </div>
            <div :class="{ 'blur-doc': !store.paid }">
              <p v-for="(para, i) in doc.ar.paragraphs" :key="i" class="mb-3 text-justify">{{ para }}</p>
              <p class="mb-1 font-bold">{{ doc.ar.reasonLabel }}</p>
              <p class="mb-3 text-justify">{{ doc.ar.reasonText }}</p>
              <p class="mb-3 text-justify">{{ doc.ar.closing }}</p>
              <div class="mt-8 grid grid-cols-2 gap-6 text-[11px]">
                <div>
                  <p class="text-slate-400 mb-6">توقيع المؤجر</p>
                  <div class="border-t border-slate-300 pt-1.5">
                    <p class="font-semibold text-slate-800">{{ doc.ar.landlordName }}</p>
                    <p class="text-slate-400">{{ doc.ar.signDate }}</p>
                  </div>
                </div>
                <div>
                  <p class="text-slate-400 mb-6">توثيق الكاتب العدل</p>
                  <div class="border-t border-slate-300 pt-1.5"><p class="font-semibold text-slate-300">&mdash;</p></div>
                </div>
              </div>
              <p class="text-[10px] text-slate-400 mt-6 italic">{{ doc.ar.footer }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Add-on services (base + optional extras, priced individually) -->
    <div class="bg-white rounded-2xl border border-slate-200 shadow-premium overflow-hidden">
      <div class="flex items-center justify-between px-4 py-3 border-b border-slate-100">
        <span class="text-sm font-bold text-slate-800">Bilingual Notice Generator</span>
        <span class="text-sm font-bold text-slate-900 tabular-nums">{{ store.basePrice }} AED</span>
      </div>
      <label
        v-for="(addOn, key) in store.addOnCatalog"
        :key="key"
        class="flex items-start gap-3 px-4 py-3 border-b border-slate-100 last:border-b-0 cursor-pointer hover:bg-slate-50 transition"
      >
        <input v-model="store.addOns[key]" type="checkbox" class="mt-0.5 w-4 h-4 rounded border-slate-300 text-emerald focus:ring-emerald">
        <span class="flex-1 min-w-0">
          <span class="flex items-center justify-between gap-2">
            <span class="text-sm font-semibold text-slate-800">Add {{ addOn.label }}</span>
            <span class="text-xs font-bold text-slate-600 tabular-nums shrink-0">+{{ addOn.priceAed }} AED</span>
          </span>
          <span class="block text-xs text-slate-500 mt-0.5">{{ addOn.description }}</span>
        </span>
      </label>
      <div class="flex items-center justify-between px-4 py-3 bg-slate-50">
        <span class="text-sm font-bold text-slate-900">Grand Total</span>
        <span class="text-lg font-extrabold text-slate950 tabular-nums">{{ store.totalPrice }} AED</span>
      </div>
    </div>

    <!-- Primary paywall CTA (fake Stripe checkout — see PaymentModal.vue) -->
    <button
      class="w-full group relative overflow-hidden bg-emerald hover:bg-emerald-600 text-white font-bold text-sm sm:text-base py-4 rounded-2xl shadow-xl shadow-emerald/25 transition flex items-center justify-center gap-2.5"
      @click="handleDownloadClick"
    >
      <DownloadCloud class="w-5 h-5" />
      <span>Download Notarized-Format PDF</span>
      <span class="bg-white/20 px-2 py-0.5 rounded-md text-xs font-extrabold tracking-wide">{{ store.totalPrice }} AED</span>
    </button>
    <p class="text-center text-[11px] text-slate-400 -mt-1">Secure checkout &middot; Instant PDF &middot; Notary-ready formatting</p>

    <!-- Secondary: persist to the API (the real backend round-trip) -->
    <button
      class="w-full border border-slate-200 hover:bg-slate-50 text-slate-700 font-semibold text-sm py-3 rounded-2xl transition flex items-center justify-center gap-2.5 disabled:opacity-60"
      :disabled="!store.isReadyToSave || store.saving"
      @click="handleSave"
    >
      <Loader2 v-if="store.saving" class="w-4 h-4 animate-spin" />
      <CheckCircle2 v-else-if="store.savedId" class="w-4 h-4 text-emerald-600" />
      <Save v-else class="w-4 h-4" />
      <span>{{ store.saving ? 'Saving…' : store.savedId ? 'Saved — Save Another' : 'Save Notice to Your Account' }}</span>
    </button>
    <p v-if="store.saveError" class="text-center text-[11px] text-red-600">{{ store.saveError }}</p>
  </div>
</template>
