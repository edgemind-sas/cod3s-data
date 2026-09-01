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
      <!-- Pipeline time first: the Observatory watches the architecture, not the
           process. The source's own timestamp is what Grafana and InfluxDB index
           on, and it is kept right below because a gap between the two is itself
           worth seeing — a replayed session puts months between them. -->
      <tr>
        <td class="text-medium-emphasis font-weight-medium">Published</td>
        <td>
          {{ formatTimestamp(observedAt) }}
          <span class="text-caption text-medium-emphasis ml-2">{{ timeAgo(observedAt) }}</span>
        </td>
      </tr>
      <tr>
        <td class="text-medium-emphasis font-weight-medium">Source timestamp</td>
        <td>
          {{ formatTimestamp(detail.timestamp) }}
          <span v-if="clockGap" class="text-caption text-warning ml-2">{{ clockGap }}</span>
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

/** Falls back to the source's timestamp for a detail stored before this field. */
const observedAt = computed(() => props.detail.observed_at || props.detail.timestamp)

/** Shown only when the two clocks disagree by more than a rounding error. */
const clockGap = computed(() => {
  const observed = new Date(observedAt.value).getTime()
  const source = new Date(props.detail.timestamp).getTime()
  if (!Number.isFinite(observed) || !Number.isFinite(source)) return ''
  const ms = observed - source
  if (Math.abs(ms) < 1000) return ''
  const behind = ms > 0
  const secs = Math.abs(ms) / 1000
  const amount =
    secs < 60
      ? `${secs.toFixed(1)}s`
      : secs < 3600
        ? `${Math.round(secs / 60)}m`
        : secs < 86400
          ? `${Math.round(secs / 3600)}h`
          : `${Math.round(secs / 86400)}d`
  return behind ? `${amount} older than publication` : `${amount} ahead of publication`
})

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
