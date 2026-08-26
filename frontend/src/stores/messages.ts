import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface StoredMessage {
  message_id: string
  channel: string
  key: string | null
  value_preview: string
  tags: Record<string, string>
  subscriber_count: number
  timestamp: string
}

export const useMessagesStore = defineStore('messages', () => {
  const messages = ref<StoredMessage[]>([])
  const maxMessages = 1000

  // Arrivals are coalesced into one reactive mutation per animation frame.
  // Sampling defaults to "none", so a fast pipeline delivers one WebSocket
  // event per message; touching `messages` on each one would re-render every
  // consumer at the pipeline's rate instead of the display's.
  let pending: StoredMessage[] = []
  let frame: number | null = null

  const messageCount = computed(() => messages.value.length)

  const channels = computed(() => {
    const set = new Set<string>()
    messages.value.forEach(m => set.add(m.channel))
    return Array.from(set).sort()
  })

  function flush() {
    frame = null
    if (pending.length === 0) return

    const batch = pending
    pending = []
    messages.value.push(...batch)

    const excess = messages.value.length - maxMessages
    // splice rather than slice: it keeps the array identity, so consumers
    // holding the reference are not invalidated wholesale on every eviction.
    if (excess > 0) messages.value.splice(0, excess)
  }

  function scheduleFlush() {
    if (frame !== null) return
    frame = typeof requestAnimationFrame === 'function'
      ? requestAnimationFrame(flush)
      : (setTimeout(flush, 16) as unknown as number)
  }

  function addMessage(msg: StoredMessage) {
    if (msg.channel.startsWith('_metrics.')) return
    pending.push(msg)
    // A burst larger than the cap can only end up evicted; drop the excess
    // here rather than pushing it through the reactive array first.
    if (pending.length > maxMessages) pending = pending.slice(-maxMessages)
    scheduleFlush()
  }

  function getByChannel(channel: string): StoredMessage[] {
    return messages.value.filter(m => m.channel === channel)
  }

  function clear() {
    pending = []
    messages.value = []
  }

  return { messages, messageCount, channels, addMessage, getByChannel, clear }
})
