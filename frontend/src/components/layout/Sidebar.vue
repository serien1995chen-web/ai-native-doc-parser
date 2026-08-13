<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()

const navItems = [
  {
    label: '新解析',
    to: '/',
    isActive: () => route.path === '/',
  },
  {
    label: '任务管理',
    to: '/tasks',
    isActive: () => route.path === '/tasks',
  },
  {
    label: '我的收藏',
    to: '/collections/default',
    isActive: () => route.path.startsWith('/collections'),
  },
]
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-brand">AI Native Doc Parser</div>
    <nav class="sidebar-nav">
      <RouterLink
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        class="nav-link"
        :class="{ 'is-active': item.isActive() }"
      >
        {{ item.label }}
      </RouterLink>
    </nav>
  </aside>
</template>
