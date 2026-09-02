<script setup>
import { LayoutDashboard, FilePlus2, ListChecks, Settings, ShieldCheck, Bot, X } from '@lucide/vue';
import { router } from '../../router.js';

defineProps({ open: { type: Boolean, default: false } });
const emit = defineEmits(['close', 'open-chat']);

const icons = { 'layout-dashboard': LayoutDashboard, 'file-plus-2': FilePlus2, 'list-checks': ListChecks, settings: Settings };
const navItems = router.options.routes.filter((r) => r.meta?.title);
</script>

<template>
  <div v-if="open" class="fixed inset-0 bg-slate950/40 z-30 lg:hidden" @click="emit('close')"></div>

  <aside
    class="fixed inset-y-0 left-0 z-40 w-64 bg-slate950 text-slate-300 flex flex-col shrink-0 transition-transform duration-300 lg:translate-x-0 lg:static lg:z-0"
    :class="open ? 'translate-x-0' : '-translate-x-full'"
    style="padding-top: env(safe-area-inset-top); padding-bottom: env(safe-area-inset-bottom);"
  >
    <div class="h-16 px-5 flex items-center justify-between border-b border-white/10 shrink-0">
      <div class="flex items-center gap-2.5">
        <div class="w-9 h-9 rounded-lg bg-emerald flex items-center justify-center shadow-lg shadow-emerald/30 shrink-0">
          <ShieldCheck class="w-5 h-5 text-white" />
        </div>
        <div class="leading-tight">
          <p class="font-bold text-[15px] text-white tracking-tight">Rent Shield</p>
          <p class="text-[10px] text-slate-500 tracking-wide uppercase">RERA &middot; DLD Compliant</p>
        </div>
      </div>
      <button aria-label="Close menu" class="lg:hidden text-slate-400 hover:text-white p-2 -m-2" @click="emit('close')">
        <X class="w-5 h-5" />
      </button>
    </div>

    <nav class="flex-1 overflow-y-auto px-3 py-4 space-y-1">
      <p class="px-3 mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-600">Notices</p>
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold transition"
        :class="$route.path === item.path ? 'bg-white/10 text-white' : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'"
        @click="emit('close')"
      >
        <component :is="icons[item.meta.icon]" class="w-4 h-4 shrink-0" />
        {{ item.meta.title }}
      </router-link>

      <p class="px-3 mt-5 mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-600">Tools</p>
      <button
        class="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold text-slate-400 hover:bg-white/5 hover:text-slate-200 transition"
        @click="emit('open-chat')"
      >
        <Bot class="w-4 h-4 shrink-0 text-emerald" />
        AI Assistant
      </button>
    </nav>

    <div class="px-4 py-4 border-t border-white/10 text-[10.5px] text-slate-500 leading-relaxed shrink-0">
      Document drafting aid — not legal advice. Verify with a licensed UAE legal counsel or Notary Public.
    </div>
  </aside>
</template>
