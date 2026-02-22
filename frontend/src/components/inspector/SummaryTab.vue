<template>
  <v-table density="compact" class="summary-table">
    <tbody>
      <tr>
        <td class="text-medium-emphasis font-weight-medium">Key</td>
        <td>{{ detail.key ?? '-' }}</td>
      </tr>
      <tr>
        <td class="text-medium-emphasis font-weight-medium">Channel</td>
        <td>
          <v-chip size="x-small" variant="flat" :color="channelColor(detail.channel)">
            {{ detail.channel }}
          </v-chip>
        </td>
      </tr>
      <tr>
        <td class="text-medium-emphasis font-weight-medium">Timestamp</td>
        <td>
          {{ formatTimestamp(detail.timestamp) }}
          <span class="text-caption text-medium-emphasis ml-2">{{ timeAgo(detail.timestamp) }}</span>
        </td>
      </tr>
      <tr>
        <td class="text-medium-emphasis font-weight-medium">Value Type</td>
        <td>{{ valueType }}</td>
      </tr>
      <tr>
        <td class="text-medium-emphasis font-weight-medium">Tags Count</td>
        <td>{{ Object.keys(detail.tags || {}).length }}</td>
      </tr>
      <tr>
        <td class="text-medium-emphasis font-weight-medium">Subscriber Count</td>
        <td>{{ detail.subscriber_count }}</td>
      </tr>
      <tr>
        <td class="text-medium-emphasis font-weight-medium">Message ID</td>
        <td class="d-flex align-center">
          <code class="text-caption">{{ detail.message_id }}</code>
          <v-btn icon size="x-small" variant="text" @click="copy(detail.message_id)" class="ml-1">
            <v-icon size="14">mdi-content-copy</v-icon>
          </v-btn>
        </td>
      </tr>
      <tr>
        <td class="text-medium-emphasis font-weight-medium">Trace ID</td>
        <td class="d-flex align-center">
          <code class="text-caption">{{ detail.trace_id }}</code>
          <v-btn icon size="x-small" variant="text" @click="copy(detail.trace_id)" class="ml-1">
            <v-icon size="14">mdi-content-copy</v-icon>
          </v-btn>
        </td>
      </tr>
    </tbody>
  </v-table>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { MessageDetail } from '@/types'
import { channelColor } from '@/utils/channelColors'

const props = defineProps<{ detail: MessageDetail }>()

const valueType = computed(() => {
  const v = props.detail.value
  if (v === null || v === undefined) return 'null'
  if (Array.isArray(v)) return `array(${v.length})`
  return typeof v
})

function formatTimestamp(ts: string): string {
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return ts
  }
}

function timeAgo(ts: string): string {
  try {
    const diff = Date.now() - new Date(ts).getTime()
    const secs = Math.floor(diff / 1000)
    if (secs < 60) return `${secs}s ago`
    const mins = Math.floor(secs / 60)
    if (mins < 60) return `${mins}m ago`
    const hrs = Math.floor(mins / 60)
    return `${hrs}h ago`
  } catch {
    return ''
  }
}

function copy(text: string) {
  navigator.clipboard.writeText(text)
}
</script>

<style scoped>
.summary-table td:first-child {
  width: 160px;
  white-space: nowrap;
}
</style>
