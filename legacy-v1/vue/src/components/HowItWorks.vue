<script setup>
import { ClipboardList, ScanSearch, Stamp, DownloadCloud } from '@lucide/vue';

const steps = [
  {
    icon: ClipboardList,
    title: 'Fill the Guided Wizard',
    body: 'Enter landlord, tenant, and property details, then select your statutory reason — the engine calculates your exact legal notice period automatically.'
  },
  {
    icon: ScanSearch,
    title: 'Add AI Compliance Review (optional)',
    body: "Upload your tenancy contract addendum and let the AI scan it for clauses that conflict with Dubai Law No. (33) of 2008."
  },
  {
    icon: Stamp,
    title: 'Add Notarization Service (optional)',
    body: 'Request routing through a licensed UAE notary before your notice is served.'
  },
  {
    icon: DownloadCloud,
    title: 'Download Your Bilingual Notice',
    body: 'Get your English and Legal Arabic notice instantly — ready to print, notarize, or serve.'
  }
];
</script>

<template>
  <section class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
    <h2 class="text-sm font-bold text-slate-700 uppercase tracking-wide mb-5">How It Works</h2>
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div v-for="(step, i) in steps" :key="step.title" class="bg-white rounded-2xl border border-slate-200 shadow-premium p-5 relative">
        <span class="absolute top-4 right-4 text-[10px] font-bold text-slate-300 tabular-nums">{{ String(i + 1).padStart(2, '0') }}</span>
        <div class="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center mb-4">
          <component :is="step.icon" class="w-5 h-5 text-slate-600" />
        </div>
        <h3 class="text-sm font-bold text-slate-900 mb-1.5 pr-6">{{ step.title }}</h3>
        <p class="text-xs text-slate-500 leading-relaxed">{{ step.body }}</p>
      </div>
    </div>
  </section>
</template>
