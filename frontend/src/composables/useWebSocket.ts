import { useConnectionStore } from '@/stores/connection'

export function useWebSocket() {
  const store = useConnectionStore()

  function sendCommand(type: string, payload: Record<string, unknown> = {}) {
    store.send({
      type,
      id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      payload,
    })
  }

  return {
    connected: store.connected,
    reconnecting: store.reconnecting,
    error: store.error,
    sendCommand,
  }
}
