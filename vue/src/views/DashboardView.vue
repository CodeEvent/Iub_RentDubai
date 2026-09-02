<script setup>
import { computed, onMounted } from 'vue';
import { FilePlus2, FileText, Calendar1, AlertOctagon, Sparkles, ArrowRight } from '@lucide/vue';
import { useNoticeStore } from '../stores/notice.js';

const store = useNoticeStore();
onMounted(() => store.fetchSavedNotices());

const stats = computed(() => {
  const all = store.savedNotices;
  return {
    total: all.length,
    statutory: all.filter((n) => n.noticePeriodDays === 365).length,
    breach: all.filter((n) => n.noticePeriodDays === 30).length,
    premium: all.filter((n) => n.tier === 'premium').length
  };
});
const recent = computed(() => store.savedNotices.slice(0, 5));
</script>

<template>
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
      <p class="text-sm text-slate-500 max-w-2xl">Draft RERA-compliant bilingual tenancy notices in minutes — 12-month statutory eviction notices and 30-day Article 25(1) breach notices, side by side in English and Legal Arabic.</p>
      <router-link to="/notices/new" class="inline-flex items-center gap-2 bg-emerald hover:bg-emerald-600 text-white text-sm font-bold px-5 py-3 rounded-xl transition shrink-0 shadow-lg shadow-emerald/25">
        <FilePlus2 class="w-4 h-4" /> New Notice
      </router-link>
    </div>

    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      <div class="bg-white rounded-2xl border border-slate-200 shadow-premium p-5">
        <div class="w-9 h-9 rounded-lg bg-slate-100 flex items-center justify-center mb-3"><FileText class="w-4 h-4 text-slate-600" /></div>
        <p class="text-2xl font-extrabold text-slate950 tabular-nums">{{ stats.total }}</p>
        <p class="text-xs text-slate-500 mt-0.5">Total Notices</p>
      </div>
      <div class="bg-white rounded-2xl border border-slate-200 shadow-premium p-5">
        <div class="w-9 h-9 rounded-lg bg-emerald-50 flex items-center justify-center mb-3"><Calendar1 class="w-4 h-4 text-emerald-700" /></div>
        <p class="text-2xl font-extrabold text-slate950 tabular-nums">{{ stats.statutory }}</p>
        <p class="text-xs text-slate-500 mt-0.5">12-Month Statutory</p>
      </div>
      <div class="bg-white rounded-2xl border border-slate-200 shadow-premium p-5">
        <div class="w-9 h-9 rounded-lg bg-amber-50 flex items-center justify-center mb-3"><AlertOctagon class="w-4 h-4 text-amber-600" /></div>
        <p class="text-2xl font-extrabold text-slate950 tabular-nums">{{ stats.breach }}</p>
        <p class="text-xs text-slate-500 mt-0.5">30-Day Breach</p>
      </div>
      <div class="bg-white rounded-2xl border border-slate-200 shadow-premium p-5">
        <div class="w-9 h-9 rounded-lg bg-slate-100 flex items-center justify-center mb-3"><Sparkles class="w-4 h-4 text-slate-600" /></div>
        <p class="text-2xl font-extrabold text-slate950 tabular-nums">{{ stats.premium }}</p>
        <p class="text-xs text-slate-500 mt-0.5">Premium AI Tier</p>
      </div>
    </div>

    <div class="bg-white rounded-2xl border border-slate-200 shadow-premium overflow-hidden mb-6">
      <div class="flex items-center justify-between px-5 py-4 border-b border-slate-100">
        <h2 class="text-sm font-bold text-slate-700">Recent Notices</h2>
        <router-link to="/notices" class="text-xs font-semibold text-emerald-700 hover:text-emerald-800 inline-flex items-center gap-1">View all <ArrowRight class="w-3.5 h-3.5" /></router-link>
      </div>
      <div v-if="!recent.length" class="px-5 py-10 text-center text-sm text-slate-400">No notices saved yet — build your first one above.</div>
      <div v-else class="divide-y divide-slate-100">
        <div v-for="n in recent" :key="n.id" class="flex items-center justify-between gap-3 px-5 py-3.5 text-sm">
          <div class="min-w-0">
            <p class="font-semibold text-slate-800 truncate">{{ n.landlordName }} &rarr; {{ n.tenantName }}</p>
            <p class="text-xs text-slate-400">{{ n.reasonLabel }} &middot; {{ n.noticePeriodDays }}-day notice &middot; {{ n.propertyType }} {{ n.unitNo }}</p>
          </div>
          <span class="shrink-0 text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full" :class="n.tier === 'premium' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'">{{ n.tier }}</span>
        </div>
      </div>
    </div>

    <div class="flex gap-3 items-start bg-emerald-50 border border-emerald-100 rounded-xl px-4 py-3.5">
      <p class="text-xs text-emerald-800 leading-relaxed">This platform auto-calculates the mandatory <strong>365-day</strong> (or <strong>30-day</strong> breach) notice period per Article 25 and enforces the statutory eviction and breach grounds recognized by RERA / the Rental Dispute Settlement Centre (RDSC).</p>
    </div>
  </div>
</template>
