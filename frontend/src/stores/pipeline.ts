import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { PipelineState } from '@/types'

export const usePipelineStore = defineStore('pipeline', () => {
  const state = ref<PipelineState>('idle')

  const isRunning = computed(() => state.value === 'running')
  const canStart = computed(() => state.value === 'idle' || state.value === 'stopped')
  const canStop = computed(() => state.value === 'running')

  function updateFromServer(data: { state?: PipelineState }) {
    if (data.state !== undefined) state.value = data.state
  }

  return {
    state,
    isRunning,
    canStart,
    canStop,
    updateFromServer,
  }
})
