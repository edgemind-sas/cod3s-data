import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/topology',
  },
  {
    path: '/topology',
    name: 'Topology',
    component: () => import('@/views/TopologyView.vue'),
    meta: { title: 'Pipeline Topology', icon: 'mdi-graph' },
  },
  {
    path: '/timeline',
    name: 'Timeline',
    component: () => import('@/views/TimelineView.vue'),
    meta: { title: 'Temporal Timeline', icon: 'mdi-timeline' },
  },
  {
    path: '/messages',
    name: 'Messages',
    component: () => import('@/views/MessagesView.vue'),
    meta: { title: 'Message Inspector', icon: 'mdi-email-search-outline' },
  },
  {
    path: '/metrics',
    name: 'Metrics',
    component: () => import('@/views/MetricsView.vue'),
    meta: { title: 'Metrics Dashboard', icon: 'mdi-chart-line' },
  },
  {
    path: '/debug',
    name: 'Debug',
    component: () => import('@/views/DebugView.vue'),
    meta: { title: 'Debug Controls', icon: 'mdi-bug' },
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
