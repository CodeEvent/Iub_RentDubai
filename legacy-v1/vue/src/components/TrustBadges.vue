<script setup>
import { Calendar1, Languages, Stamp } from '@lucide/vue';

// Written honestly for what this platform actually does — not copied from
// a human-lawyer service's marketing claims ("100% Legally Compliant",
// "Professional Lawyers"). This is a self-serve generator, not a law firm.
const badges = [
  {
    icon: Calendar1,
    title: 'RERA Statutory Engine',
    body: 'Auto-calculates the correct 365-day or 30-day notice period under Article 25 — never a manual date error.'
  },
  {
    icon: Languages,
    title: 'Bilingual EN / Legal Arabic',
    body: 'Every notice ships formatted side-by-side in English and professional Legal Arabic.'
  },
  {
    icon: Stamp,
    title: 'Notarization Add-on Available',
    body: 'Optional routing through a licensed UAE notary before your notice is served.'
  }
];
</script>

<template>
  <section class="bg-white border-y border-slate-200">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 grid grid-cols-1 sm:grid-cols-3 gap-6">
      <div v-for="badge in badges" :key="badge.title" class="flex items-start gap-3">
        <div class="w-10 h-10 rounded-xl bg-emerald-50 flex items-center justify-center shrink-0">
          <component :is="badge.icon" class="w-5 h-5 text-emerald-700" />
        </div>
        <div>
          <h3 class="text-sm font-bold text-slate-900">{{ badge.title }}</h3>
          <p class="text-xs text-slate-500 mt-0.5 leading-relaxed">{{ badge.body }}</p>
        </div>
      </div>
    </div>
  </section>
</template>
