<script setup lang="ts">
import Sidebar from './Sidebar.vue'
</script>

<template>
  <div class="app-shell">
    <Sidebar />
    <main class="app-main">
      <slot />
    </main>
  </div>
</template>
