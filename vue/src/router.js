import { createRouter, createWebHistory } from 'vue-router';
import DashboardView from './views/DashboardView.vue';
import NoticeBuilderView from './views/NoticeBuilderView.vue';
import NoticesListView from './views/NoticesListView.vue';
import SettingsView from './views/SettingsView.vue';

const routes = [
  { path: '/', name: 'dashboard', component: DashboardView, meta: { title: 'Dashboard', icon: 'layout-dashboard' } },
  { path: '/notices/new', name: 'notice-new', component: NoticeBuilderView, meta: { title: 'New Notice', icon: 'file-plus-2' } },
  { path: '/notices', name: 'notices', component: NoticesListView, meta: { title: 'Saved Notices', icon: 'list-checks' } },
  { path: '/settings', name: 'settings', component: SettingsView, meta: { title: 'Settings', icon: 'settings' } }
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 };
  }
});

router.afterEach((to) => {
  document.title = to.meta?.title ? `${to.meta.title} · Dubai Rent Shield` : 'Dubai Rent Shield';
});
