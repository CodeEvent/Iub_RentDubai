<script setup>
import { computed } from 'vue';
import { ArrowLeft, ArrowRight, Check, Users, Building2, CalendarClock, CheckSquare, ShieldCheck, AlertTriangle } from '@lucide/vue';
import { STATUTORY_REASONS, BREACH_REASONS } from '@rentshield/shared';
import { STEPS, useNoticeStore } from '../stores/notice.js';
import StepIndicator from './StepIndicator.vue';

const store = useNoticeStore();

const stepIcons = { users: Users, 'building-2': Building2, 'calendar-clock': CalendarClock, 'check-square': CheckSquare };
const currentIcon = computed(() => stepIcons[STEPS[store.step].icon]);

const expiryPreview = computed(() => {
  if (!store.noticeDate) return null;
  const doc = store.document;
  const en = doc.en;
  return { label: en.deadlineLabel, value: en.deadlineValue };
});

function reviewValue(v) {
  return v && String(v).trim() ? v : null;
}
</script>

<template>
  <div class="bg-white rounded-2xl border border-slate-200 shadow-premium overflow-hidden">
    <div class="px-6 sm:px-8 pt-6">
      <StepIndicator :step="store.step" />
    </div>

    <div class="px-6 sm:px-8 py-6 min-h-[420px]">
      <!-- Step 0: Parties -->
      <div v-if="store.step === 0" class="step-panel space-y-5">
        <div class="flex items-center gap-2 mb-1">
          <div class="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center"><Users class="w-4 h-4 text-slate-600" /></div>
          <h3 class="font-bold text-slate-900">Landlord &amp; Tenant Details</h3>
        </div>
        <div>
          <label class="text-xs font-semibold text-slate-600 mb-1.5 block">Landlord Full Name</label>
          <input v-model="store.landlordName" type="text" placeholder="e.g. Ahmed Khalifa Al Suwaidi" class="field-input w-full border border-slate-300 rounded-xl px-3.5 py-2.5 text-sm">
        </div>
        <div>
          <label class="text-xs font-semibold text-slate-600 mb-1.5 block">
            Landlord Email
            <span class="font-normal text-slate-400">(required only if you add Notarization)</span>
          </label>
          <input v-model="store.landlordEmail" type="email" placeholder="e.g. ahmed@example.com" class="field-input w-full border border-slate-300 rounded-xl px-3.5 py-2.5 text-sm">
        </div>
        <div>
          <label class="text-xs font-semibold text-slate-600 mb-1.5 block">Tenant Full Name</label>
          <input v-model="store.tenantName" type="text" placeholder="e.g. John Michael Smith" class="field-input w-full border border-slate-300 rounded-xl px-3.5 py-2.5 text-sm">
        </div>
      </div>

      <!-- Step 1: Property -->
      <div v-else-if="store.step === 1" class="step-panel space-y-5">
        <div class="flex items-center gap-2 mb-1">
          <div class="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center"><Building2 class="w-4 h-4 text-slate-600" /></div>
          <h3 class="font-bold text-slate-900">Property Details</h3>
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="text-xs font-semibold text-slate-600 mb-1.5 block">Unit Type</label>
            <select v-model="store.propertyType" class="field-input w-full border border-slate-300 rounded-xl px-3.5 py-2.5 text-sm bg-white">
              <option value="Apartment">Apartment</option>
              <option value="Villa">Villa</option>
              <option value="Townhouse">Townhouse</option>
              <option value="Office">Office / Commercial Unit</option>
            </select>
          </div>
          <div>
            <label class="text-xs font-semibold text-slate-600 mb-1.5 block">Unit / Villa No.</label>
            <input v-model="store.unitNo" type="text" placeholder="e.g. 1204" class="field-input w-full border border-slate-300 rounded-xl px-3.5 py-2.5 text-sm">
          </div>
        </div>
        <div>
          <label class="text-xs font-semibold text-slate-600 mb-1.5 block">Building / Community Name</label>
          <input v-model="store.buildingName" type="text" placeholder="e.g. Marina Heights, Dubai Marina" class="field-input w-full border border-slate-300 rounded-xl px-3.5 py-2.5 text-sm">
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="text-xs font-semibold text-slate-600 mb-1.5 block">Plot Number</label>
            <input v-model="store.plotNumber" type="text" placeholder="e.g. 341-2891" class="field-input w-full border border-slate-300 rounded-xl px-3.5 py-2.5 text-sm">
          </div>
          <div>
            <label class="text-xs font-semibold text-slate-600 mb-1.5 block">Ejari Certificate No.</label>
            <input v-model="store.ejariNumber" type="text" placeholder="e.g. 1234567890" class="field-input w-full border border-slate-300 rounded-xl px-3.5 py-2.5 text-sm">
          </div>
        </div>
      </div>

      <!-- Step 2: Notice & Reason -->
      <div v-else-if="store.step === 2" class="step-panel space-y-5">
        <div class="flex items-center gap-2 mb-1">
          <div class="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center"><CalendarClock class="w-4 h-4 text-slate-600" /></div>
          <h3 class="font-bold text-slate-900">Notice Date &amp; Legal Reason</h3>
        </div>
        <div>
          <label class="text-xs font-semibold text-slate-600 mb-1.5 block">Notice Served Date</label>
          <input v-model="store.noticeDate" type="date" class="field-input w-full border border-slate-300 rounded-xl px-3.5 py-2.5 text-sm">
        </div>

        <div v-if="expiryPreview" class="flex items-center gap-2.5 bg-slate-50 border border-slate-200 rounded-xl px-4 py-3">
          <ShieldCheck class="w-4 h-4 text-emerald shrink-0" />
          <p class="text-xs text-slate-600">{{ expiryPreview.label }}: <strong class="text-slate-900">{{ expiryPreview.value }}</strong></p>
        </div>

        <div>
          <label class="text-xs font-semibold text-slate-600 mb-1.5 block">Reason for Eviction</label>
          <select v-model="store.reason" class="field-input w-full border border-slate-300 rounded-xl px-3.5 py-2.5 text-sm bg-white">
            <option value="">Select a statutory reason...</option>
            <optgroup label="12-Month Statutory Notice">
              <option v-for="(r, key) in STATUTORY_REASONS" :key="key" :value="key">{{ r.label }}</option>
            </optgroup>
            <optgroup label="30-Day Breach Notice (Article 25)">
              <option v-for="(r, key) in BREACH_REASONS" :key="key" :value="key">{{ r.label }}</option>
            </optgroup>
          </select>
        </div>

        <div v-if="store.reasonData" class="flex items-center gap-2">
          <span
            class="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full"
            :class="store.isBreachReason ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'"
          >{{ store.isBreachReason ? '30-Day Breach Notice' : '12-Month Statutory Notice' }}</span>
        </div>
        <div
          v-if="store.reasonData"
          class="rounded-xl border px-4 py-3.5 flex gap-3 items-start"
          :class="store.reasonData.tone === 'red' ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200'"
        >
          <AlertTriangle class="w-4 h-4 mt-0.5 shrink-0" :class="store.reasonData.tone === 'red' ? 'text-red-600' : 'text-amber-600'" />
          <p class="text-xs leading-relaxed" :class="store.reasonData.tone === 'red' ? 'text-red-800 font-semibold' : 'text-amber-800'">{{ store.reasonData.warning }}</p>
        </div>
      </div>

      <!-- Step 3: Review -->
      <div v-else class="step-panel space-y-4">
        <div class="flex items-center gap-2 mb-1">
          <div class="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center"><CheckSquare class="w-4 h-4 text-slate-600" /></div>
          <h3 class="font-bold text-slate-900">Review Summary</h3>
        </div>
        <div class="rounded-xl border border-slate-200 divide-y divide-slate-100 overflow-hidden text-sm">
          <div class="flex items-start justify-between gap-3 px-4 py-2.5">
            <span class="text-slate-400 text-xs font-medium shrink-0">Landlord</span>
            <span class="text-slate-800 font-semibold text-right break-words min-w-0" :class="{ 'text-slate-300 italic font-normal': !reviewValue(store.landlordName) }">{{ reviewValue(store.landlordName) || 'Not provided' }}</span>
          </div>
          <div class="flex items-start justify-between gap-3 px-4 py-2.5">
            <span class="text-slate-400 text-xs font-medium shrink-0">Tenant</span>
            <span class="text-slate-800 font-semibold text-right break-words min-w-0" :class="{ 'text-slate-300 italic font-normal': !reviewValue(store.tenantName) }">{{ reviewValue(store.tenantName) || 'Not provided' }}</span>
          </div>
          <div class="flex items-start justify-between gap-3 px-4 py-2.5">
            <span class="text-slate-400 text-xs font-medium shrink-0">Property</span>
            <span class="text-slate-800 font-semibold text-right break-words min-w-0">{{ store.propertyType }} {{ store.unitNo }}, {{ store.buildingName }}</span>
          </div>
          <div class="flex items-start justify-between gap-3 px-4 py-2.5">
            <span class="text-slate-400 text-xs font-medium shrink-0">Plot No.</span>
            <span class="text-slate-800 font-semibold text-right break-words min-w-0" :class="{ 'text-slate-300 italic font-normal': !reviewValue(store.plotNumber) }">{{ reviewValue(store.plotNumber) || 'Not provided' }}</span>
          </div>
          <div class="flex items-start justify-between gap-3 px-4 py-2.5">
            <span class="text-slate-400 text-xs font-medium shrink-0">Ejari No.</span>
            <span class="text-slate-800 font-semibold text-right break-words min-w-0" :class="{ 'text-slate-300 italic font-normal': !reviewValue(store.ejariNumber) }">{{ reviewValue(store.ejariNumber) || 'Not provided' }}</span>
          </div>
          <div class="flex items-start justify-between gap-3 px-4 py-2.5">
            <span class="text-slate-400 text-xs font-medium shrink-0">Notice Date</span>
            <span class="text-slate-800 font-semibold text-right break-words min-w-0">{{ store.document.en.dateValue }}</span>
          </div>
          <div class="flex items-start justify-between gap-3 px-4 py-2.5">
            <span class="text-slate-400 text-xs font-medium shrink-0">{{ store.document.en.deadlineLabel }}</span>
            <span class="text-slate-800 font-semibold text-right break-words min-w-0">{{ store.document.en.deadlineValue }}</span>
          </div>
          <div class="flex items-start justify-between gap-3 px-4 py-2.5">
            <span class="text-slate-400 text-xs font-medium shrink-0">Reason</span>
            <span class="text-slate-800 font-semibold text-right break-words min-w-0" :class="{ 'text-slate-300 italic font-normal': !store.reasonData }">{{ store.reasonData?.label || 'Not provided' }}</span>
          </div>
        </div>
        <div class="flex items-start gap-2.5 bg-emerald-50 border border-emerald-100 rounded-xl px-4 py-3">
          <ShieldCheck class="w-4 h-4 text-emerald-700 mt-0.5 shrink-0" />
          <p class="text-xs text-emerald-800">Your bilingual notice is ready in the live preview panel.</p>
        </div>
      </div>
    </div>

    <div class="px-6 sm:px-8 pb-7 flex items-center justify-between border-t border-slate-100 pt-5">
      <button
        class="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-500 hover:text-slate-800 transition py-2.5 pr-2 -ml-1"
        :class="{ 'opacity-0 pointer-events-none': store.step === 0 }"
        @click="store.goStep(-1)"
      >
        <ArrowLeft class="w-4 h-4" /> Back
      </button>
      <button
        class="inline-flex items-center gap-2 bg-slate950 hover:bg-slate-800 text-white text-sm font-semibold px-5 py-2.5 rounded-xl transition shadow-lg shadow-slate950/10"
        @click="store.goStep(1)"
      >
        <template v-if="store.step === STEPS.length - 1">Done <Check class="w-4 h-4" /></template>
        <template v-else>Continue <ArrowRight class="w-4 h-4" /></template>
      </button>
    </div>
  </div>
</template>
