import { useInspectorStore } from '@/stores/inspector'
import { useWebSocket } from './useWebSocket'

export function useInspector() {
  const store = useInspectorStore()
  const { sendCommand } = useWebSocket()

  function inspect(messageId: string) {
    store.selectMessage(messageId)
    sendCommand('message.inspect', { message_id: messageId })
  }

  function close() {
    store.close()
  }

  function toggle() {
    store.toggle()
  }

  return {
    isOpen: store.isOpen,
    panelHeight: store.panelHeight,
    activeTab: store.activeTab,
    selectedMessageId: store.selectedMessageId,
    messageDetail: store.messageDetail,
    loading: store.loading,
    error: store.error,
    hasDetail: store.hasDetail,
    inspect,
    close,
    toggle,
  }
}
