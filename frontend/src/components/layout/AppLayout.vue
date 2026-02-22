<template>
  <v-layout>
    <v-app-bar density="compact" flat>
      <v-app-bar-title class="text-body-1">
        COD3S Observatory
      </v-app-bar-title>
      <template #append>
        <v-chip
          :color="stateColor"
          size="small"
          variant="elevated"
          class="mr-3"
        >
          {{ pipelineStore.state }}
        </v-chip>
        <v-btn
          v-if="pipeline.canStart"
          color="green"
          variant="tonal"
          size="small"
          class="mr-1"
          @click="pipeline.start"
        >
          <v-icon start>mdi-play</v-icon>
          Start
        </v-btn>
        <v-btn
          v-if="pipeline.canStop"
          color="orange"
          variant="tonal"
          size="small"
          class="mr-1"
          @click="pipeline.stop"
        >
          <v-icon start>mdi-stop</v-icon>
          Stop
        </v-btn>
        <v-btn
          v-if="pipeline.isRunning"
          color="blue"
          variant="tonal"
          size="small"
          @click="pipeline.restart"
        >
          <v-icon start>mdi-restart</v-icon>
          Restart
        </v-btn>
      </template>
    </v-app-bar>
    <AppSidebar />
    <v-main :style="{ paddingBottom: inspectorStore.isOpen ? inspectorStore.panelHeight + 'px' : '40px' }">
      <v-container fluid class="pa-4">
        <slot />
      </v-container>
    </v-main>
    <MessageInspector />
  </v-layout>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppSidebar from './AppSidebar.vue'
import MessageInspector from '@/components/inspector/MessageInspector.vue'
import { usePipeline } from '@/composables/usePipeline'
import { usePipelineStore } from '@/stores/pipeline'
import { useInspectorStore } from '@/stores/inspector'

const pipeline = usePipeline()
const pipelineStore = usePipelineStore()
const inspectorStore = useInspectorStore()

const stateColor = computed(() => {
  switch (pipelineStore.state) {
    case 'running': return 'green'
    case 'stopping': return 'orange'
    case 'stopped': return 'orange'
    case 'error': return 'red'
    default: return 'grey'
  }
})
</script>
