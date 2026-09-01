<template>
  <div>
    <h1 class="text-h5 mb-4">Message Inspector</h1>

    <v-card v-if="messagesStore.messageCount === 0">
      <v-card-text class="text-center text-medium-emphasis">
        <v-icon size="48" class="mb-2">mdi-email-search-outline</v-icon>
        <p>No messages captured yet.</p>
        <p class="text-caption">Messages will appear here as they flow through the pipeline.</p>
      </v-card-text>
    </v-card>

    <template v-else>
      <!-- Filter bar -->
      <div class="d-flex align-center flex-wrap ga-2 mb-4">
        <v-text-field
          v-model="keyFilter"
          density="compact"
          variant="outlined"
          placeholder="Filter by key..."
          prepend-inner-icon="mdi-magnify"
          hide-details
          clearable
          style="max-width: 260px"
        />

        <v-chip
          v-for="ch in messagesStore.channels"
          :key="ch"
          size="small"
          :color="selectedChannel === ch ? channelColor(ch) : undefined"
          :variant="selectedChannel === ch ? 'flat' : 'outlined'"
          @click="toggleChannel(ch)"
        >
          {{ ch }}
        </v-chip>

        <v-spacer />

        <span class="text-caption text-medium-emphasis">
          {{ filtered.total }} / {{ messagesStore.messageCount }} messages
          <span v-if="filtered.total > filteredMessages.length">
            (showing the {{ filteredMessages.length }} most recent)
          </span>
        </span>

        <v-btn
          :icon="autoScroll ? 'mdi-pause' : 'mdi-play'"
          size="small"
          variant="text"
          :color="autoScroll ? 'primary' : undefined"
          @click="autoScroll = !autoScroll"
          :title="autoScroll ? 'Pause auto-scroll' : 'Resume auto-scroll'"
        />
      </div>

      <!-- Messages table -->
      <v-card>
        <div ref="tableContainer" class="messages-table-wrap" @scroll="onScroll">
          <v-table density="compact" hover>
            <thead>
              <tr>
                <th style="width: 140px">Time</th>
                <th style="width: 120px">Channel</th>
                <th style="width: 120px">Key</th>
                <th>Value</th>
                <th>Tags</th>
                <th style="width: 90px" class="text-right">Subscribers</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="msg in filteredMessages"
                :key="msg.uid"
                :class="{ 'inspector-selected': msg.message_id === inspector.selectedMessageId }"
                class="message-row"
                @click="inspectMessage(msg.message_id)"
              >
                <td class="text-caption text-medium-emphasis" style="font-family: monospace">
                  {{ formatTime(msg.timestamp) }}
                </td>
                <td>
                  <v-chip
                    size="x-small"
                    variant="flat"
                    :color="channelColor(msg.channel)"
                  >
                    {{ msg.channel }}
                  </v-chip>
                </td>
                <td class="text-body-2">{{ msg.key ?? '-' }}</td>
                <td class="text-body-2 text-truncate" style="max-width: 200px" :title="msg.value_preview">
                  {{ msg.value_preview || '-' }}
                </td>
                <td>
                  <v-chip
                    v-for="(v, k) in msg.tags"
                    :key="String(k)"
                    size="x-small"
                    variant="outlined"
                    class="mr-1"
                  >
                    {{ k }}={{ v }}
                  </v-chip>
                  <span v-if="!msg.tags || Object.keys(msg.tags).length === 0" class="text-medium-emphasis">-</span>
                </td>
                <td class="text-right">{{ msg.subscriber_count }}</td>
              </tr>
            </tbody>
          </v-table>
        </div>
      </v-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { useMessagesStore, type StoredMessage } from '@/stores/messages'
import { useInspector } from '@/composables/useInspector'
import { channelColor } from '@/utils/channelColors'

const messagesStore = useMessagesStore()
const inspector = useInspector()

function inspectMessage(messageId: string) {
  if (messageId) {
    inspector.inspect(messageId)
  }
}

const selectedChannel = ref<string | null>(null)
const keyFilter = ref('')
const autoScroll = ref(true)
const tableContainer = ref<HTMLElement | null>(null)

function toggleChannel(ch: string) {
  selectedChannel.value = selectedChannel.value === ch ? null : ch
}

const MAX_ROWS = 200

/**
 * The newest MAX_ROWS messages the filters keep, plus how many they keep in all.
 *
 * One backward pass over the store: newest first without copying and reversing
 * a thousand entries every frame, and the filters see the whole store rather
 * than its last 200 rows — filtering after truncating meant a low-rate channel
 * such as `params.consignes` showed nothing while the store held its messages.
 * Rows stop accumulating at the cap; the count keeps going, so "x / y" is true.
 */
const filtered = computed(() => {
  const channel = selectedChannel.value
  const kf = keyFilter.value ? keyFilter.value.toLowerCase() : ''
  const all = messagesStore.messages
  const rows: StoredMessage[] = []
  let total = 0
  for (let i = all.length - 1; i >= 0; i--) {
    const m = all[i]
    if (channel && m.channel !== channel) continue
    if (kf && !m.key?.toLowerCase().includes(kf)) continue
    total++
    if (rows.length < MAX_ROWS) rows.push(m)
  }
  return { rows, total }
})

const filteredMessages = computed(() => filtered.value.rows)

function formatTime(ts: string): string {
  try {
    const d = new Date(ts)
    const time = d.toLocaleTimeString()
    const ms = String(d.getMilliseconds()).padStart(3, '0')
    return `${time}.${ms}`
  } catch {
    return ts
  }
}

// Newest first, so following the flow means staying at the TOP. Scrolling to
// the bottom sent the view to the oldest row on every arrival — away from what
// had just come in.
function scrollToNewest() {
  if (tableContainer.value) {
    tableContainer.value.scrollTop = 0
  }
}

// Scrolling down means the user is reading older rows; auto-scroll steps aside
// until they come back to the top, as the Timeline already does.
let userScrolled = false

function onScroll() {
  if (!tableContainer.value) return
  userScrolled = tableContainer.value.scrollTop > 8
}

watch(
  () => messagesStore.messageCount,
  () => {
    if (autoScroll.value && !userScrolled) {
      nextTick(scrollToNewest)
    }
  }
)

watch(autoScroll, (on) => {
  if (on) {
    userScrolled = false
    nextTick(scrollToNewest)
  }
})
</script>

<style scoped>
.messages-table-wrap {
  max-height: 70vh;
  overflow-y: auto;
}
.message-row {
  cursor: pointer;
}
.inspector-selected {
  background: rgba(var(--v-theme-primary), 0.08) !important;
}
</style>
