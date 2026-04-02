import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { PipelineState } from '@/types'

export const usePipelineStore = defineStore('pipeline', () => {
  const state = ref<PipelineState>('idle')
  const displayName = ref('COD3S Observatory')
  const subtitle = ref('')

  const isRunning = computed(() => state.value === 'running')
  const canStart = computed(() => state.value === 'idle' || state.value === 'stopped')
  const canStop = computed(() => state.value === 'running')

  function updateFromServer(data: { state?: PipelineState }) {
    if (data.state !== undefined) state.value = data.state
  }

  function updateInfoFromServer(data: { display_name?: string; subtitle?: string }) {
    if (data.display_name) displayName.value = data.display_name
    if (data.subtitle !== undefined) subtitle.value = data.subtitle
  }

  return {
    state,
    displayName,
    subtitle,
    isRunning,
    canStart,
    canStop,
    updateFromServer,
    updateInfoFromServer,
  }
})
