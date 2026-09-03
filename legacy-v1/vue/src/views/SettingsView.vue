<script setup>
import { ref, onMounted } from 'vue';
import { CheckCircle2, XCircle, Loader2 } from '@lucide/vue';
import { useNoticeStore } from '../stores/notice.js';

const store = useNoticeStore();
const apiStatus = ref('checking'); // 'checking' | 'ok' | 'down'

async function checkApi() {
  apiStatus.value = 'checking';
  try {
    const res = await fetch('/api/health');
    apiStatus.value = res.ok ? 'ok' : 'down';
  } catch {
    apiStatus.value = 'down';
  }
}
onMounted(checkApi);
</script>

<template>
  <div class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
    <div class="bg-white rounded-2xl border border-slate-200 shadow-premium p-5">
      <h2 class="text-sm font-bold text-slate-800 mb-1">API Connection</h2>
      <p class="text-xs text-slate-500 mb-4">The Express + SQLite backend this app saves notices to (@rentshield/api).</p>
      <div class="flex items-center gap-2.5 bg-slate-50 border border-slate-200 rounded-xl px-4 py-3">
        <Loader2 v-if="apiStatus === 'checking'" class="w-4 h-4 text-slate-400 animate-spin" />
        <CheckCircle2 v-else-if="apiStatus === 'ok'" class="w-4 h-4 text-emerald-600" />
        <XCircle v-else class="w-4 h-4 text-red-500" />
        <p class="text-xs text-slate-600">
          <span v-if="apiStatus === 'checking'">Checking /api/health&hellip;</span>
          <span v-else-if="apiStatus === 'ok'" class="text-emerald-700 font-semibold">Connected</span>
          <span v-else class="text-red-600 font-semibold">Unreachable — is `npm run dev:api` running?</span>
        </p>
        <button class="ml-auto text-[11px] font-semibold text-slate-500 hover:text-slate-800" @click="checkApi">Recheck</button>
      </div>
    </div>

    <div class="bg-white rounded-2xl border border-slate-200 shadow-premium p-5">
      <h2 class="text-sm font-bold text-slate-800 mb-1">Service Charges</h2>
      <p class="text-xs text-slate-500 mb-4">Base generator fee plus optional add-on services, priced individually — not a flat law-firm package.</p>
      <div class="rounded-xl border border-slate-200 divide-y divide-slate-100 overflow-hidden text-sm">
        <div class="flex items-center justify-between px-4 py-2.5">
          <span class="text-slate-600">Bilingual Notice Generator</span>
          <span class="font-semibold text-slate-800 tabular-nums">{{ store.basePrice }} AED</span>
        </div>
        <div v-for="(addOn, key) in store.addOnCatalog" :key="key" class="flex items-center justify-between px-4 py-2.5">
          <span class="text-slate-600">+ {{ addOn.label }}</span>
          <span class="font-semibold text-slate-800 tabular-nums">{{ addOn.priceAed }} AED</span>
        </div>
      </div>
    </div>

    <div class="bg-white rounded-2xl border border-slate-200 shadow-premium p-5">
      <h2 class="text-sm font-bold text-slate-800 mb-1">Default Add-ons</h2>
      <p class="text-xs text-slate-500 mb-4">Which add-ons new notices start with before you adjust them in the builder.</p>
      <label v-for="(addOn, key) in store.addOnCatalog" :key="key" class="flex items-center justify-between gap-3 py-2 cursor-pointer">
        <span class="text-sm text-slate-700">{{ addOn.label }}</span>
        <input v-model="store.addOns[key]" type="checkbox" class="w-4 h-4 rounded border-slate-300 text-emerald focus:ring-emerald">
      </label>
    </div>

    <div class="bg-white rounded-2xl border border-slate-200 shadow-premium p-5 text-xs text-slate-500 leading-relaxed">
      <h2 class="text-sm font-bold text-slate-800 mb-1">About</h2>
      <p>Dubai Rent Shield is a document drafting aid and does not constitute legal advice. Always verify service requirements with a licensed UAE legal counsel or Notary Public.</p>
      <p class="mt-2">Repo layout follows <a href="https://github.com/minthcm/minthcm" target="_blank" rel="noopener" class="text-emerald-700 font-semibold hover:underline">minthcm</a>'s module conventions as an architectural reference — no minthcm code or its AGPL-3.0 license is part of this project.</p>
    </div>
  </div>
</template>
