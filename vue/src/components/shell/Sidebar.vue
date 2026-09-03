<script setup>
import { ref, watch } from 'vue';
import { LayoutDashboard, FilePlus2, ListChecks, Settings, ShieldCheck, Bot, X, PanelLeftClose, PanelLeftOpen } from '@lucide/vue';
import { router } from '../../router.js';

defineProps({ open: { type: Boolean, default: false } });
const emit = defineEmits(['close', 'open-chat']);

const icons = { 'layout-dashboard': LayoutDashboard, 'file-plus-2': FilePlus2, 'list-checks': ListChecks, settings: Settings };
const navItems = router.options.routes.filter((r) => r.meta?.title);

// Desktop icon-rail collapse — remembered per browser via localStorage.
// Only reachable through the toggle button, which is hidden below the lg
// breakpoint, so the mobile slide-out drawer always shows full labels.
const collapsed = ref(false);
try {
  collapsed.value = localStorage.getItem('rentshield.sidebarCollapsed') === '1';
} catch {
  // Private browsing / storage blocked — default to expanded.
}
watch(collapsed, (v) => {
  try {
    localStorage.setItem('rentshield.sidebarCollapsed', v ? '1' : '0');
  } catch {
    // Non-fatal — collapse preference just won't persist this session.
  }
});
</script>

<template>
  <div v-if="open" class="fixed inset-0 bg-slate950/40 z-30 lg:hidden" @click="emit('close')"></div>

  <aside
    class="fixed inset-y-0 left-0 z-40 w-64 bg-slate950 text-slate-300 flex flex-col shrink-0 transition-[transform,width] duration-300 lg:translate-x-0 lg:static lg:z-0"
    :class="[open ? 'translate-x-0' : '-translate-x-full', collapsed ? 'lg:w-20' : 'lg:w-64']"
    style="padding-top: env(safe-area-inset-top); padding-bottom: env(safe-area-inset-bottom);"
  >
    <div class="h-16 px-5 flex items-center justify-between border-b border-white/10 shrink-0" :class="{ 'lg:px-0 lg:justify-center': collapsed }">
      <div class="flex items-center gap-2.5 min-w-0">
        <div class="w-9 h-9 rounded-lg bg-emerald flex items-center justify-center shadow-lg shadow-emerald/30 shrink-0">
          <ShieldCheck class="w-5 h-5 text-white" />
        </div>
        <div class="leading-tight min-w-0" :class="{ 'lg:hidden': collapsed }">
          <p class="font-bold text-[15px] text-white tracking-tight truncate">Rent Shield</p>
          <p class="text-[10px] text-slate-500 tracking-wide uppercase truncate">RERA &middot; DLD Compliant</p>
        </div>
      </div>
      <button aria-label="Close menu" class="lg:hidden text-slate-400 hover:text-white p-2 -m-2" @click="emit('close')">
        <X class="w-5 h-5" />
      </button>
    </div>

    <nav class="flex-1 overflow-y-auto px-3 py-4 space-y-1">
      <p class="px-3 mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-600" :class="{ 'lg:hidden': collapsed }">Notices</p>
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        :title="collapsed ? item.meta.title : null"
        class="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold transition"
        :class="[$route.path === item.path ? 'bg-white/10 text-white' : 'text-slate-400 hover:bg-white/5 hover:text-slate-200', { 'lg:justify-center lg:px-0': collapsed }]"
        @click="emit('close')"
      >
        <component :is="icons[item.meta.icon]" class="w-4 h-4 shrink-0" />
        <span :class="{ 'lg:hidden': collapsed }">{{ item.meta.title }}</span>
      </router-link>

      <p class="px-3 mt-5 mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-600" :class="{ 'lg:hidden': collapsed }">Tools</p>
      <button
        :title="collapsed ? 'AI Assistant' : null"
        class="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold text-slate-400 hover:bg-white/5 hover:text-slate-200 transition"
        :class="{ 'lg:justify-center lg:px-0': collapsed }"
        @click="emit('open-chat')"
      >
        <Bot class="w-4 h-4 shrink-0 text-emerald" />
        <span :class="{ 'lg:hidden': collapsed }">AI Assistant</span>
      </button>
    </nav>

    <button
      class="hidden lg:flex items-center gap-2 mx-3 mb-2 px-3 py-2 rounded-lg text-slate-500 hover:bg-white/5 hover:text-slate-300 transition text-xs font-semibold"
      :class="{ 'justify-center px-0': collapsed }"
      @click="collapsed = !collapsed"
    >
      <PanelLeftOpen v-if="collapsed" class="w-4 h-4 shrink-0" />
      <PanelLeftClose v-else class="w-4 h-4 shrink-0" />
      <span v-if="!collapsed">Collapse</span>
    </button>

    <div class="px-4 py-4 border-t border-white/10 text-[10.5px] text-slate-500 leading-relaxed shrink-0" :class="{ 'lg:hidden': collapsed }">
      Document drafting aid — not legal advice. Verify with a licensed UAE legal counsel or Notary Public.
    </div>
  </aside>
</template>
