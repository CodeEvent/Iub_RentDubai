<script setup>
import { ref } from 'vue';
import Sidebar from './components/shell/Sidebar.vue';
import TopBar from './components/shell/TopBar.vue';
import ChatDrawer from './components/ChatDrawer.vue';
import PaymentModal from './components/PaymentModal.vue';

const sidebarOpen = ref(false);
const chatDrawerRef = ref(null);
</script>

<template>
  <div class="lg:flex min-h-screen bg-slate-50">
    <Sidebar :open="sidebarOpen" @close="sidebarOpen = false" @open-chat="chatDrawerRef?.openDrawer()" />

    <div class="flex-1 min-w-0">
      <TopBar @open-sidebar="sidebarOpen = true" />
      <router-view />
    </div>
  </div>

  <ChatDrawer ref="chatDrawerRef" />
  <PaymentModal />
</template>
