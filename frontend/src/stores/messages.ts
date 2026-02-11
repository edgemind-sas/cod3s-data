import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface StoredMessage {
  channel: string
  key: string | null
  subscriber_count: number
  timestamp: string
}

export const useMessagesStore = defineStore('messages', () => {
  const messages = ref<StoredMessage[]>([])
  const maxMessages = 1000

  const messageCount = computed(() => messages.value.length)

  const channels = computed(() => {
    const set = new Set<string>()
    messages.value.forEach(m => set.add(m.channel))
    return Array.from(set).sort()
  })

  function addMessage(msg: StoredMessage) {
    messages.value.push(msg)
    if (messages.value.length > maxMessages) {
      messages.value = messages.value.slice(-maxMessages)
    }
  }

  function getByChannel(channel: string): StoredMessage[] {
    return messages.value.filter(m => m.channel === channel)
  }

  function clear() {
    messages.value = []
  }

  return { messages, messageCount, channels, addMessage, getByChannel, clear }
})
