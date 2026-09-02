<script setup>
import { onMounted } from 'vue';
import { FilePlus2, Inbox } from '@lucide/vue';
import { useNoticeStore } from '../stores/notice.js';

const store = useNoticeStore();
onMounted(() => store.fetchSavedNotices());
</script>

<template>
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <div class="flex items-center justify-between mb-6">
      <p class="text-sm text-slate-500">Every notice saved to the RentShield API, newest first.</p>
      <router-link to="/notices/new" class="inline-flex items-center gap-2 bg-emerald hover:bg-emerald-600 text-white text-xs font-bold px-4 py-2.5 rounded-xl transition">
        <FilePlus2 class="w-4 h-4" /> New Notice
      </router-link>
    </div>

    <div v-if="!store.savedNotices.length" class="bg-white rounded-2xl border border-slate-200 shadow-premium p-12 flex flex-col items-center text-center gap-3">
      <div class="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center">
        <Inbox class="w-6 h-6 text-slate-400" />
      </div>
      <p class="font-bold text-slate-800">No notices saved yet</p>
      <p class="text-sm text-slate-500 max-w-sm">Once you save a notice from the builder, it'll show up here with its statutory reason, notice period, and tier.</p>
      <router-link to="/notices/new" class="mt-1 inline-flex items-center gap-2 bg-slate950 hover:bg-slate-800 text-white text-xs font-bold px-4 py-2.5 rounded-xl transition">
        <FilePlus2 class="w-4 h-4" /> Build your first notice
      </router-link>
    </div>

    <div v-else class="bg-white rounded-2xl border border-slate-200 shadow-premium overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-slate-100 text-left text-[10px] font-bold uppercase tracking-wide text-slate-400">
              <th class="px-5 py-3">Landlord &rarr; Tenant</th>
              <th class="px-5 py-3">Property</th>
              <th class="px-5 py-3">Reason</th>
              <th class="px-5 py-3">Period</th>
              <th class="px-5 py-3">Notice Date</th>
              <th class="px-5 py-3">Tier</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="n in store.savedNotices" :key="n.id" class="hover:bg-slate-50 transition">
              <td class="px-5 py-3.5 font-semibold text-slate-800 whitespace-nowrap">{{ n.landlordName }} &rarr; {{ n.tenantName }}</td>
              <td class="px-5 py-3.5 text-slate-600">{{ n.propertyType }} {{ n.unitNo }}</td>
              <td class="px-5 py-3.5 text-slate-600">{{ n.reasonLabel }}</td>
              <td class="px-5 py-3.5 text-slate-600 whitespace-nowrap">{{ n.noticePeriodDays }} days</td>
              <td class="px-5 py-3.5 text-slate-600 whitespace-nowrap">{{ n.noticeDate }}</td>
              <td class="px-5 py-3.5">
                <span class="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full" :class="n.tier === 'premium' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'">{{ n.tier }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
