import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/runs' },
  { path: '/runs', name: 'runs', component: () => import('./views/RunsView.vue') },
  { path: '/new', name: 'new', component: () => import('./views/NewRunView.vue') },
  { path: '/runs/:runId', redirect: (to) => ({ name: 'report', params: to.params }) },
  { path: '/runs/:runId/review', name: 'review', component: () => import('./views/ReviewView.vue') },
  { path: '/runs/:runId/report', name: 'report', component: () => import('./views/ReportView.vue'), meta: { runBar: true } },
  { path: '/runs/:runId/live', name: 'live', component: () => import('./views/LiveView.vue'), meta: { runBar: true, timeLinked: true } },
  { path: '/runs/:runId/personas', name: 'personas', component: () => import('./views/PersonasView.vue'), meta: { runBar: true, timeLinked: true } },
  { path: '/runs/:runId/community', name: 'community', component: () => import('./views/CommunityView.vue'), meta: { runBar: true, timeLinked: true } },
  { path: '/runs/:runId/interview', name: 'interview', component: () => import('./views/InterviewView.vue') },
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior: (to, from, saved) => saved || (to.name !== from.name ? { top: 0 } : undefined),
})
