import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('../views/NewParse.vue'),
    },
    {
      path: '/tasks',
      name: 'tasks',
      component: () => import('../views/TaskManagement.vue'),
    },
    {
      path: '/collections/:id',
      name: 'collections',
      component: () => import('../views/Collections.vue'),
    },
    {
      path: '/results/:task_id',
      name: 'results',
      component: () => import('../views/ParseResult.vue'),
    },
  ],
})

export default router
