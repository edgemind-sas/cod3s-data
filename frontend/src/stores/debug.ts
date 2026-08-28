import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { DebugState, Granularity, Breakpoint, DebugInfo } from '@/types'

export const useDebugStore = defineStore('debug', () => {
  const state = ref<DebugState>('inactive')
  const granularity = ref<Granularity>('message')
  const breakpoints = ref<Breakpoint[]>([])
  const slowMotion = ref(false)
  const slowMotionDelayMs = ref(500)
  const stepCount = ref(0)
  // A step waits for a message to flow; with a quiet pipeline that wait is
  // unbounded, so the client is told the command was accepted and shows it as
  // pending until the step actually happens.
  const stepPending = ref(false)

  function setStepPending(pending: boolean) {
    stepPending.value = pending
  }

  function updateFromServer(data: Partial<DebugInfo>) {
    if (data.state !== undefined) state.value = data.state
    if (data.granularity !== undefined) granularity.value = data.granularity
    if (data.breakpoints !== undefined) breakpoints.value = data.breakpoints
    if (data.slow_motion !== undefined) slowMotion.value = data.slow_motion
    if (data.slow_motion_delay_ms !== undefined) slowMotionDelayMs.value = data.slow_motion_delay_ms
    if (data.step_count !== undefined) stepCount.value = data.step_count
  }

  return {
    state,
    granularity,
    breakpoints,
    slowMotion,
    slowMotionDelayMs,
    stepCount,
    stepPending,
    setStepPending,
    updateFromServer,
  }
})
