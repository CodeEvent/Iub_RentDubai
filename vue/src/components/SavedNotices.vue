<script setup>
import { onMounted } from 'vue';
import { ListChecks } from '@lucide/vue';
import { useNoticeStore } from '../stores/notice.js';

const store = useNoticeStore();
onMounted(() => store.fetchSavedNotices());
</script>

<template>
  <section v-if="store.savedNotices.length" class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-12">
    <div class="flex items-center gap-2 mb-3">
      <ListChecks class="w-4 h-4 text-slate-500" />
      <h2 class="text-sm font-bold text-slate-700 uppercase tracking-wide">Saved Notices</h2>
    </div>
    <div class="bg-white rounded-2xl border border-slate-200 shadow-premium divide-y divide-slate-100 overflow-hidden">
      <div v-for="n in store.savedNotices" :key="n.id" class="flex items-center justify-between gap-3 px-5 py-3.5 text-sm">
        <div class="min-w-0">
          <p class="font-semibold text-slate-800 truncate">{{ n.landlordName }} &rarr; {{ n.tenantName }}</p>
          <p class="text-xs text-slate-400">{{ n.reasonLabel }} &middot; {{ n.noticePeriodDays }}-day notice &middot; {{ n.propertyType }} {{ n.unitNo }}</p>
        </div>
        <span class="shrink-0 text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full" :class="n.tier === 'premium' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'">{{ n.tier }}</span>
      </div>
    </div>
  </section>
</template>
