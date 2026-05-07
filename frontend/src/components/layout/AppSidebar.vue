<template>
  <v-navigation-drawer permanent rail expand-on-hover>
    <v-list-item
      prepend-icon="mdi-telescope"
      :title="pipelineStore.displayName"
      :subtitle="pipelineStore.subtitle || 'v1.0.0'"
      class="sidebar-header"
    />

    <v-divider />

    <v-list density="compact" nav>
      <v-list-item
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        :prepend-icon="item.icon"
        :title="item.title"
        :active="$route.path === item.path"
      />
    </v-list>

    <template #append>
      <v-divider />
      <v-list-item
        :prepend-icon="connectionIcon"
        :title="connectionLabel"
        :class="connectionClass"
      />
    </template>
  </v-navigation-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useConnectionStore } from '@/stores/connection'
import { usePipelineStore } from '@/stores/pipeline'

const connectionStore = useConnectionStore()
const pipelineStore = usePipelineStore()

const navItems = [
  { path: '/topology', title: 'Topology', icon: 'mdi-graph' },
  { path: '/timeline', title: 'Timeline', icon: 'mdi-timeline' },
  { path: '/messages', title: 'Messages', icon: 'mdi-email-search-outline' },
  { path: '/parameters', title: 'Parameters', icon: 'mdi-tune' },
  // { path: '/metrics', title: 'Metrics', icon: 'mdi-chart-line' },
  // { path: '/debug', title: 'Debug', icon: 'mdi-bug' },
]

const connectionIcon = computed(() => {
  if (connectionStore.connected) return 'mdi-circle'
  if (connectionStore.reconnecting) return 'mdi-loading mdi-spin'
  return 'mdi-circle-outline'
})

const connectionLabel = computed(() => {
  if (connectionStore.connected) return 'Connected'
  if (connectionStore.reconnecting) return 'Reconnecting...'
  return 'Disconnected'
})

const connectionClass = computed(() => ({
  'text-green': connectionStore.connected,
  'text-orange': connectionStore.reconnecting,
  'text-red': !connectionStore.connected && !connectionStore.reconnecting,
}))
</script>

<style scoped>
.sidebar-header :deep(.v-list-item-title),
.sidebar-header :deep(.v-list-item-subtitle) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
