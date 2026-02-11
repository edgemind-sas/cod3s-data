import { usePipelineStore } from '@/stores/pipeline'
import { useWebSocket } from './useWebSocket'

export function usePipeline() {
  const store = usePipelineStore()
  const { sendCommand } = useWebSocket()

  function start() {
    sendCommand('pipeline.start')
  }

  function stop() {
    sendCommand('pipeline.stop')
  }

  function restart() {
    sendCommand('pipeline.restart')
  }

  return {
    state: store.state,
    isRunning: store.isRunning,
    canStart: store.canStart,
    canStop: store.canStop,
    start,
    stop,
    restart,
  }
}
