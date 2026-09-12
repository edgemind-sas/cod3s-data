import { defineStore } from 'pinia'
import { ref, computed, triggerRef } from 'vue'

export interface StoredMessage {
  /**
   * Identifies this publication, where `message_id` does not.
   *
   * A message_id is not unique across the stream: a pass-through transform —
   * `throttle`, `filter` — forwards the very object it received, so the same id
   * is published again on the next channel. Keying a `v-for` on message_id
   * therefore produced duplicate keys, and Vue then stopped removing evicted
   * rows: the timeline reached 28 000 `<circle>` nodes for a 500-message store.
   */
  uid: number
  message_id: string
  channel: string
  key: string | null
  value_preview: string
  tags: Record<string, string>
  subscriber_count: number
  timestamp: string
}

/** Incoming payloads carry everything but the uid, which the store assigns. */
export type IncomingMessage = Omit<StoredMessage, 'uid'>

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
  let nextUid = 1

  const messageCount = computed(() => messages.value.length)

  // Counted per channel, and maintained as messages arrive and are evicted.
  // Deriving the list by walking every retained message meant a full pass on
  // each flush — for a set that changes perhaps a dozen times in a run. The
  // counts are what make eviction cheap: a channel leaves the list only once
  // its last message is gone.
  const channelCounts = ref(new Map<string, number>())

  const channels = computed(() => Array.from(channelCounts.value.keys()).sort())

  function retain(channel: string) {
    const counts = channelCounts.value
    counts.set(channel, (counts.get(channel) ?? 0) + 1)
  }

  function release(channel: string) {
    const counts = channelCounts.value
    const left = (counts.get(channel) ?? 0) - 1
    if (left > 0) counts.set(channel, left)
    else counts.delete(channel)
  }

  function flush() {
    frame = null
    if (pending.length === 0) return

    const batch = pending
    pending = []
    messages.value.push(...batch)
    for (const msg of batch) retain(msg.channel)

    const excess = messages.value.length - maxMessages.value
    // splice rather than slice: it keeps the array identity, so consumers
    // holding the reference are not invalidated wholesale on every eviction.
    if (excess > 0) {
      for (let i = 0; i < excess; i++) release(messages.value[i].channel)
      messages.value.splice(0, excess)
    }
    // The Map is mutated in place, so the computed needs telling.
    triggerRef(channelCounts)
  }

  function scheduleFlush() {
    if (frame !== null) return
    frame = typeof requestAnimationFrame === 'function'
      ? requestAnimationFrame(flush)
      : (setTimeout(flush, 16) as unknown as number)
  }

  function addMessage(msg: IncomingMessage) {
    if (msg.channel.startsWith('_metrics.')) return
    pending.push({ ...msg, uid: nextUid++ })
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
    channelCounts.value.clear()
    triggerRef(channelCounts)
  }

  /** Align the client's retention with what the server can still describe. */
  function setMaxMessages(limit: number) {
    if (!Number.isFinite(limit) || limit < 1) return
    maxMessages.value = Math.floor(limit)
    const excess = messages.value.length - maxMessages.value
    if (excess > 0) {
      for (let i = 0; i < excess; i++) release(messages.value[i].channel)
      messages.value.splice(0, excess)
      triggerRef(channelCounts)
    }
  }

  /** How much wall-clock time the retained messages cover, in seconds. */
  const historySeconds = computed(() => {
    const all = messages.value
    if (all.length < 2) return 0
    const span = Date.parse(all[all.length - 1].timestamp) - Date.parse(all[0].timestamp)
    return Number.isFinite(span) ? Math.max(span, 0) / 1000 : 0
  })

  return {
    messages,
    messageCount,
    channels,
    channelCounts,
    historySeconds,
    maxMessages,
    addMessage,
    setMaxMessages,
    getByChannel,
    clear,
  }
})
