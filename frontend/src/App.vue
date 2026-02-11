<template>
  <v-app>
    <AppLayout>
      <router-view />
    </AppLayout>
  </v-app>
</template>

<script setup lang="ts">
import AppLayout from '@/components/layout/AppLayout.vue'
import { useConnectionStore } from '@/stores/connection'
import { onMounted, onUnmounted } from 'vue'

const connectionStore = useConnectionStore()

onMounted(() => {
  connectionStore.connect()
})

onUnmounted(() => {
  connectionStore.disconnect()
})
</script>
