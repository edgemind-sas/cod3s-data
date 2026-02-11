<template>
  <div>
    <h1 class="text-h5 mb-4">Metrics Dashboard</h1>

    <!-- Global stats bar -->
    <v-row class="mb-4" dense>
      <v-col cols="6" md="3">
        <v-card variant="tonal" color="blue">
          <v-card-text class="text-center pa-3">
            <div class="text-h5">{{ messagesStore.messageCount }}</div>
            <div class="text-caption">Total Messages</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="6" md="3">
        <v-card variant="tonal" color="green">
          <v-card-text class="text-center pa-3">
            <div class="text-h5">{{ messagesStore.channels.length }}</div>
            <div class="text-caption">Active Channels</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="6" md="3">
        <v-card variant="tonal" color="orange">
          <v-card-text class="text-center pa-3">
            <div class="text-h5">{{ metricNames.length }}</div>
            <div class="text-caption">Metrics Tracked</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="6" md="3">
        <v-card variant="tonal" :color="pipelineColor">
          <v-card-text class="text-center pa-3">
            <div class="text-h5 text-capitalize">{{ pipelineStore.state }}</div>
            <div class="text-caption">Pipeline State</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-card v-if="metricNames.length === 0">
      <v-card-text class="text-center text-medium-emphasis">
        <v-icon size="48" class="mb-2">mdi-chart-line</v-icon>
        <p>No metrics received yet.</p>
        <p class="text-caption">Metrics will appear here once the pipeline is running.</p>
      </v-card-text>
    </v-card>

    <v-row v-else>
      <v-col
        v-for="name in metricNames"
        :key="name"
        cols="12"
        md="6"
        lg="4"
      >
        <v-card class="metric-card">
          <v-card-text class="pa-4">
            <!-- Header: name + trend -->
            <div class="d-flex align-center mb-1">
              <span class="text-body-2 font-weight-medium text-truncate" :title="name">
                {{ formatMetricName(name) }}
              </span>
              <v-spacer />
              <v-chip
                v-if="trend(name) !== 0"
                size="x-small"
                :color="trend(name) > 0 ? 'success' : 'error'"
                variant="tonal"
              >
                <v-icon size="12" start>{{ trend(name) > 0 ? 'mdi-trending-up' : 'mdi-trending-down' }}</v-icon>
                {{ trendPercent(name) }}
              </v-chip>
              <v-chip v-else size="x-small" variant="tonal" color="grey">
                <v-icon size="12" start>mdi-trending-neutral</v-icon>
                stable
              </v-chip>
            </div>

            <!-- Current value -->
            <div class="text-h4 mb-2">
              {{ formatValue(metricsStore.latestByName[name]) }}
            </div>

            <!-- Sparkline -->
            <div class="sparkline-container">
              <svg
                v-if="sparklinePoints(name).length > 1"
                width="100%"
                height="60"
                :viewBox="`0 0 ${sparklineViewWidth(name)} 60`"
                preserveAspectRatio="none"
                class="sparkline-svg"
              >
                <defs>
                  <linearGradient :id="'grad-' + sanitizeId(name)" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" :stop-color="metricColor(name)" stop-opacity="0.25" />
                    <stop offset="100%" :stop-color="metricColor(name)" stop-opacity="0.02" />
                  </linearGradient>
                </defs>
                <polygon
                  :points="sparklineArea(name)"
                  :fill="`url(#grad-${sanitizeId(name)})`"
                />
                <polyline
                  :points="sparklineLine(name)"
                  fill="none"
                  :stroke="metricColor(name)"
                  stroke-width="2"
                  stroke-linejoin="round"
                  stroke-linecap="round"
                />
              </svg>
              <div v-else class="sparkline-placeholder text-caption text-medium-emphasis">
                Waiting for data points...
              </div>
            </div>

            <!-- Footer: tags + point count -->
            <div class="d-flex align-center mt-2 flex-wrap ga-1">
              <v-chip
                v-for="(v, k) in metricsStore.latestByName[name]?.tags"
                :key="String(k)"
                size="x-small"
                variant="outlined"
              >
                {{ k }}={{ v }}
              </v-chip>
              <v-spacer />
              <span class="text-caption text-medium-emphasis">
                {{ sparklinePoints(name).length }} pts
              </span>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useMessagesStore } from '@/stores/messages'
import { useMetricsStore, type MetricPoint } from '@/stores/metrics'
import { usePipelineStore } from '@/stores/pipeline'

const PALETTE = ['#42A5F5', '#66BB6A', '#FFA726', '#AB47BC', '#26C6DA', '#EC407A', '#8D6E63', '#EF5350']

const messagesStore = useMessagesStore()
const metricsStore = useMetricsStore()
const pipelineStore = usePipelineStore()

const metricNames = computed(() => Object.keys(metricsStore.latestByName).sort())

const pipelineColor = computed(() => {
  const map: Record<string, string> = { running: 'green', idle: 'grey', stopped: 'red', stopping: 'orange', error: 'red' }
  return map[pipelineStore.state] ?? 'grey'
})

function metricColor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) | 0
  return PALETTE[Math.abs(hash) % PALETTE.length]
}

function sanitizeId(name: string): string {
  return name.replace(/[^a-zA-Z0-9]/g, '-')
}

function formatMetricName(name: string): string {
  // "broker.messages_published" -> "Broker / Messages Published"
  return name
    .split('.')
    .map(part => part.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()))
    .join(' / ')
}

function formatValue(metric: MetricPoint | undefined): string {
  if (!metric) return '-'
  if (typeof metric.value === 'number') {
    if (Number.isInteger(metric.value)) return metric.value.toLocaleString()
    return metric.value.toFixed(2)
  }
  return JSON.stringify(metric.value)
}

function trend(name: string): number {
  const history = metricsStore.getHistory(name, 5)
  if (history.length < 2) return 0
  const prev = history[history.length - 2].value
  const curr = history[history.length - 1].value
  if (typeof prev !== 'number' || typeof curr !== 'number') return 0
  if (curr > prev) return 1
  if (curr < prev) return -1
  return 0
}

function trendPercent(name: string): string {
  const history = metricsStore.getHistory(name, 5)
  if (history.length < 2) return ''
  const prev = history[history.length - 2].value
  const curr = history[history.length - 1].value
  if (typeof prev !== 'number' || typeof curr !== 'number' || prev === 0) return ''
  const pct = ((curr - prev) / Math.abs(prev)) * 100
  return `${pct > 0 ? '+' : ''}${pct.toFixed(1)}%`
}

function sparklinePoints(name: string): number[] {
  const history = metricsStore.getHistory(name, 50)
  return history
    .map(p => (typeof p.value === 'number' ? p.value : null))
    .filter((v): v is number => v !== null)
}

function sparklineViewWidth(name: string): number {
  return Math.max(sparklinePoints(name).length - 1, 1) * 6
}

function sparklineLine(name: string): string {
  const pts = sparklinePoints(name)
  if (pts.length < 2) return ''
  const min = Math.min(...pts)
  const max = Math.max(...pts)
  const range = max - min || 1
  const w = sparklineViewWidth(name)
  const step = w / (pts.length - 1)
  return pts.map((v, i) => `${i * step},${56 - ((v - min) / range) * 52}`).join(' ')
}

function sparklineArea(name: string): string {
  const pts = sparklinePoints(name)
  if (pts.length < 2) return ''
  const min = Math.min(...pts)
  const max = Math.max(...pts)
  const range = max - min || 1
  const w = sparklineViewWidth(name)
  const step = w / (pts.length - 1)
  const line = pts.map((v, i) => `${i * step},${56 - ((v - min) / range) * 52}`).join(' ')
  return `0,60 ${line} ${w},60`
}
</script>

<style scoped>
.metric-card {
  transition: box-shadow 0.2s;
}
.metric-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3) !important;
}

.sparkline-container {
  height: 60px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.03);
}

.sparkline-svg {
  display: block;
}

.sparkline-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}
</style>
