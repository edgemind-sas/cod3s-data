import { useParametersStore } from '@/stores/parameters'
import { useWebSocket } from './useWebSocket'

export function useParameters() {
  const store = useParametersStore()
  const { sendCommand } = useWebSocket()

  async function refresh() {
    await store.fetchAll()
  }

  function update(channel: string, value: unknown, key?: string | null) {
    sendCommand('param.update', {
      channel,
      value,
      ...(key ? { key } : {}),
    })
  }

  return {
    params: store.params,
    loading: store.loading,
    error: store.error,
    refresh,
    update,
  }
}
