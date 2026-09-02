<script setup>
import { Check } from '@lucide/vue';
import { STEPS } from '../stores/notice.js';

defineProps({ step: { type: Number, required: true } });
</script>

<template>
  <div class="flex items-center justify-between">
    <template v-for="(s, i) in STEPS" :key="s.title">
      <div class="flex items-center" :class="i < STEPS.length - 1 ? 'flex-1' : ''">
        <div class="flex flex-col items-center gap-1.5 shrink-0">
          <div
            class="w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold transition-all"
            :class="i < step ? 'bg-emerald text-white' : i === step ? 'bg-slate950 text-white ring-4 ring-slate950/10' : 'bg-slate-100 text-slate-400'"
          >
            <Check v-if="i < step" class="w-4 h-4" />
            <span v-else>{{ i + 1 }}</span>
          </div>
          <span
            class="text-[10px] font-semibold uppercase tracking-wide hidden sm:block"
            :class="i === step ? 'text-slate-800' : 'text-slate-400'"
          >{{ s.title }}</span>
        </div>
        <div v-if="i < STEPS.length - 1" class="flex-1 h-0.5 mx-2 rounded" :class="i < step ? 'bg-emerald' : 'bg-slate-100'"></div>
      </div>
    </template>
  </div>
</template>
