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
  // Set from the server's `connected` payload. Keeping more rows than the
  // server can describe made half the table clickable and dead: the details and
  // the journey of an older message were long evicted. The default matches the
  // server's own so the window before the handshake behaves the same.
  const maxMessages = ref(500)

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

    const excess = messages.value.length - maxMessages.value
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
    if (pending.length > maxMessages.value) pending = pending.slice(-maxMessages.value)
    scheduleFlush()
  }

  function getByChannel(channel: string): StoredMessage[] {
    return messages.value.filter(m => m.channel === channel)
  }

  function clear() {
    pending = []
    messages.value = []
  }

  /** Align the client's retention with what the server can still describe. */
  function setMaxMessages(limit: number) {
    if (!Number.isFinite(limit) || limit < 1) return
    maxMessages.value = Math.floor(limit)
    const excess = messages.value.length - maxMessages.value
    if (excess > 0) messages.value.splice(0, excess)
  }

  return { messages, messageCount, channels, maxMessages, addMessage, setMaxMessages, getByChannel, clear }
})
