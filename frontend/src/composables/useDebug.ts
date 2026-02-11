import { useDebugStore } from '@/stores/debug'
import { useWebSocket } from './useWebSocket'

export function useDebug() {
  const store = useDebugStore()
  const { sendCommand } = useWebSocket()

  function pause() {
    sendCommand('debug.pause')
  }

  function resume() {
    sendCommand('debug.resume')
  }

  function step(granularity?: string) {
    sendCommand('debug.step', { granularity: granularity ?? store.granularity })
  }

  function setGranularity(granularity: 'message' | 'stage' | 'breakpoint') {
    sendCommand('debug.set_granularity', { granularity })
  }

  function setSlowMotion(enabled: boolean, delayMs: number = 500) {
    sendCommand('debug.set_slow_motion', { enabled, delay_ms: delayMs })
  }

  return {
    state: store.state,
    granularity: store.granularity,
    breakpoints: store.breakpoints,
    stepCount: store.stepCount,
    pause,
    resume,
    step,
    setGranularity,
    setSlowMotion,
  }
}
