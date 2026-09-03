<script setup>
import { useRoute } from 'vue-router';
import { Menu, FilePlus2, UserCircle } from '@lucide/vue';

defineEmits(['open-sidebar']);
const route = useRoute();
</script>

<template>
  <header class="sticky top-0 z-20 bg-white border-b border-slate-200" style="padding-top: env(safe-area-inset-top);">
    <div class="h-16 px-4 sm:px-6 flex items-center justify-between gap-3">
      <div class="flex items-center gap-3 min-w-0">
        <button aria-label="Open menu" class="lg:hidden text-slate-500 hover:text-slate-900 p-2 -m-2 shrink-0" @click="$emit('open-sidebar')">
          <Menu class="w-5 h-5" />
        </button>
        <h1 class="text-base sm:text-lg font-extrabold text-slate950 tracking-tight truncate">{{ route.meta.title }}</h1>
      </div>

      <router-link
        to="/notices/new"
        class="hidden sm:inline-flex items-center gap-2 bg-slate950 hover:bg-slate-800 text-white text-xs font-bold px-4 py-2.5 rounded-xl transition shrink-0"
      >
        <FilePlus2 class="w-4 h-4" /> New Notice
      </router-link>
      <router-link to="/notices/new" aria-label="New Notice" class="sm:hidden text-slate-500 hover:text-slate-900 p-2 -m-2 shrink-0">
        <FilePlus2 class="w-5 h-5" />
      </router-link>

      <button aria-label="Account" class="hidden sm:flex text-slate-400 hover:text-slate-700 shrink-0">
        <UserCircle class="w-7 h-7" />
      </button>
    </div>
  </header>
</template>
