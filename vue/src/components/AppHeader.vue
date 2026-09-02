<script setup>
import { ShieldCheck, Lock } from '@lucide/vue';
</script>

<template>
  <header class="sticky top-0 z-30 bg-slate950 text-white border-b border-slate-800" style="padding-top: env(safe-area-inset-top);">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
      <div class="flex items-center gap-2.5">
        <div class="w-9 h-9 rounded-lg bg-emerald flex items-center justify-center shadow-lg shadow-emerald/30">
          <ShieldCheck class="w-5 h-5 text-white" />
        </div>
        <div class="leading-tight">
          <p class="font-bold text-[15px] tracking-tight">Dubai Rent Shield</p>
          <p class="text-[10px] text-slate-400 tracking-wide uppercase">RERA &middot; DLD Compliant</p>
        </div>
      </div>
      <div class="hidden sm:flex items-center gap-2 text-xs text-slate-300">
        <Lock class="w-3.5 h-3.5 text-emerald" />
        <span>Law No. (33) of 2008 &mdash; Article 25</span>
      </div>
    </div>
  </header>
</template>
