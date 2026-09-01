<template>
  <div>
    <h1 class="text-h5 mb-4">Temporal Timeline</h1>

    <v-card v-if="messagesStore.messageCount === 0">
      <v-card-text class="text-center text-medium-emphasis">
        <v-icon size="48" class="mb-2">mdi-timeline</v-icon>
        <p>No messages captured yet.</p>
        <p class="text-caption">Messages will appear here as they flow through the pipeline.</p>
      </v-card-text>
    </v-card>

    <template v-else>
      <!-- Toolbar -->
      <div class="d-flex align-center ga-2 mb-4">
        <v-btn-toggle v-model="zoomIndex" mandatory density="compact" variant="outlined">
          <v-btn v-for="z in zoomLevels" :key="z.label" size="small">{{ z.label }}</v-btn>
        </v-btn-toggle>

        <v-spacer />

        <span class="text-caption text-medium-emphasis">
          {{ messagesStore.messageCount }} messages across {{ messagesStore.channels.length }} channels
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

      <!-- Timeline -->
      <v-card style="overflow: visible">
        <div ref="containerEl" class="timeline-container">
          <!-- Lane labels -->
          <div class="timeline-lanes">
            <div class="timeline-axis-label">&nbsp;</div>
            <div
              v-for="ch in messagesStore.channels"
              :key="ch"
              class="timeline-lane-label"
            >
              <v-chip size="small" variant="flat" :color="channelColor(ch)" class="text-truncate" style="max-width: 148px">
                {{ ch }}
              </v-chip>
            </div>
          </div>

          <!-- Horizontally scrollable plot -->
          <div ref="scrollWrap" class="timeline-scroll" @scroll="onScroll">
            <svg
              :width="svgWidth"
              :height="svgHeight"
              class="timeline-svg"
            >
              <!-- Time axis -->
              <g class="timeline-axis">
                <line x1="0" :y1="AXIS_HEIGHT - 1" :x2="svgWidth" :y2="AXIS_HEIGHT - 1" stroke="#666" stroke-width="1" />
                <template v-for="tick in timeTicks" :key="tick.x">
                  <line :x1="tick.x" :y1="AXIS_HEIGHT - 8" :x2="tick.x" :y2="AXIS_HEIGHT" stroke="#666" stroke-width="1" />
                  <text :x="tick.x" :y="AXIS_HEIGHT - 12" text-anchor="middle" fill="#999" font-size="10">
                    {{ tick.label }}
                  </text>
                </template>
              </g>

              <!-- Lane separator lines -->
              <line
                v-for="(_, idx) in messagesStore.channels"
                :key="'lane-' + idx"
                x1="0"
                :y1="AXIS_HEIGHT + (idx + 1) * LANE_HEIGHT"
                :x2="svgWidth"
                :y2="AXIS_HEIGHT + (idx + 1) * LANE_HEIGHT"
                stroke="#333"
                stroke-width="0.5"
                stroke-dasharray="2,4"
              />

              <!-- Message dots -->
              <circle
                v-for="dot in visibleDots"
                :key="dot.messageId"
                :cx="dot.x"
                :cy="dot.y"
                :r="dot.r"
                :fill="dot.color"
                opacity="0.85"
                class="timeline-dot"
                @mouseenter="hoveredDot = dot"
                @mouseleave="hoveredDot = null"
              />
            </svg>
          </div>
        </div>

        <!-- Tooltip -->
        <div
          v-if="hoveredDot"
          class="timeline-tooltip"
          :style="{ left: tooltipLeft + 'px', top: tooltipTop + 'px' }"
        >
          <div class="text-caption font-weight-bold">{{ hoveredDot.msg.channel }}</div>
          <div class="text-caption">Key: {{ hoveredDot.msg.key ?? '-' }}</div>
          <div class="text-caption" v-if="hoveredDot.msg.value_preview">Value: {{ hoveredDot.msg.value_preview }}</div>
          <div class="text-caption" v-if="hoveredTags">Tags: {{ hoveredTags }}</div>
          <div class="text-caption">Subscribers: {{ hoveredDot.msg.subscriber_count }}</div>
          <div class="text-caption text-medium-emphasis">{{ hoveredTime }}</div>
        </div>
      </v-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useMessagesStore, type StoredMessage } from '@/stores/messages'
// The same function and the same palette were declared here as well. They agreed
// by luck; sharing one keeps a channel the same colour in both views for good.
import { channelColor } from '@/utils/channelColors'

const AXIS_HEIGHT = 30
const LANE_HEIGHT = 40
const LANE_LABELS_WIDTH = 160

const messagesStore = useMessagesStore()

const zoomLevels = [
  { label: '30s', windowSec: 30 },
  { label: '60s', windowSec: 60 },
  { label: '5min', windowSec: 300 },
]
const zoomIndex = ref(1)
const autoScroll = ref(true)
const scrollWrap = ref<HTMLElement | null>(null)
const containerEl = ref<HTMLElement | null>(null)
const containerWidth = ref(800)

let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  if (containerEl.value) {
    containerWidth.value = containerEl.value.clientWidth - LANE_LABELS_WIDTH
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        containerWidth.value = entry.contentRect.width - LANE_LABELS_WIDTH
      }
    })
    resizeObserver.observe(containerEl.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
})

interface DotData {
  messageId: string
  x: number
  y: number
  r: number
  color: string
  msg: StoredMessage
}

const hoveredDot = ref<DotData | null>(null)

const hoveredTags = computed(() => hoveredDot.value ? formatTags(hoveredDot.value.msg.tags) : '')
const hoveredTime = computed(() => {
  if (!hoveredDot.value) return ''
  const d = new Date(hoveredDot.value.msg.timestamp)
  return `${d.toLocaleTimeString()}.${String(d.getMilliseconds()).padStart(3, '0')}`
})

const tooltipLeft = computed(() => {
  if (!hoveredDot.value || !scrollWrap.value) return 0
  const xInView = hoveredDot.value.x - scrollLeft.value
  return Math.min(Math.max(xInView + LANE_LABELS_WIDTH + 16, LANE_LABELS_WIDTH), (containerWidth.value + LANE_LABELS_WIDTH) - 200)
})
const TOOLTIP_HEIGHT_ESTIMATE = 110
const tooltipTop = computed(() => {
  if (!hoveredDot.value) return 0
  const dotY = hoveredDot.value.y
  const totalHeight = svgHeight.value
  // If tooltip would overflow below the SVG, show it above the dot
  if (dotY + TOOLTIP_HEIGHT_ESTIMATE > totalHeight) {
    return Math.max(dotY - TOOLTIP_HEIGHT_ESTIMATE, 0)
  }
  return dotY + 16
})

const currentWindow = computed(() => zoomLevels[zoomIndex.value])

const availableWidth = computed(() => Math.max(containerWidth.value, 400))

const pxPerSecond = computed(() => {
  const dur = totalDurationSec.value
  if (dur <= 0) return 12
  const natural = availableWidth.value / dur
  return Math.max(natural, 4)
})

// A dot's x is measured from `start` and scaled by `pxPerSecond`. Both used to
// follow the retained messages, so adding one moved all thousand: the origin
// tracked the oldest message, and the scale tracked the span. Snapping them to a
// ten-second grid — the origin down, the extent up — holds them still between
// jumps, and the DOM then only sees the dots that genuinely came and went.
const GRID_SEC = 10
const GRID_MS = GRID_SEC * 1000

const timeRange = computed(() => {
  const msgs = messagesStore.messages
  if (msgs.length === 0) return { start: 0, end: 0 }
  const first = Date.parse(msgs[0].timestamp) - 2000
  const end = Date.parse(msgs[msgs.length - 1].timestamp) + 2000
  return { start: Math.floor(first / GRID_MS) * GRID_MS, end }
})

const totalDurationSec = computed(() => {
  const { start, end } = timeRange.value
  const span = Math.max((end - start) / 1000, currentWindow.value.windowSec)
  return Math.ceil(span / GRID_SEC) * GRID_SEC
})

const svgWidth = computed(() => Math.max(totalDurationSec.value * pxPerSecond.value, availableWidth.value))
const svgHeight = computed(() => AXIS_HEIGHT + Math.max(messagesStore.channels.length, 1) * LANE_HEIGHT)

const channelIndex = computed(() => {
  const map = new Map<string, number>()
  messagesStore.channels.forEach((ch, i) => map.set(ch, i))
  return map
})

const timeTicks = computed(() => {
  const { start } = timeRange.value
  const dur = totalDurationSec.value
  let interval = 5
  if (dur > 120) interval = 15
  if (dur > 300) interval = 30
  if (dur > 600) interval = 60

  const ticks: { x: number; label: string }[] = []
  for (let s = 0; s <= dur; s += interval) {
    const t = new Date(start + s * 1000)
    ticks.push({
      x: s * pxPerSecond.value,
      label: t.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    })
  }
  return ticks
})

function formatTags(tags: Record<string, string> | undefined): string {
  if (!tags || Object.keys(tags).length === 0) return ''
  return Object.entries(tags).map(([k, v]) => `${k}=${v}`).join(', ')
}

// Geometry only. The strings the tooltip needs are derived from the hovered
// message instead, so a recompute does not format a thousand of them to show one.
// A dot's geometry only depends on the message, the origin, the scale and the
// lane order — and the first three are held still by the grid snapping above.
// Recomputing all of them on every arrival rebuilt hundreds of objects per
// frame to add one; they are kept and reused until something they depend on
// actually moves.
let dotCache = new Map<string, DotData>()
let dotCacheKey = ''

const dots = computed<DotData[]>(() => {
  const { start } = timeRange.value
  const ppSec = pxPerSecond.value
  const lanes = channelIndex.value

  const key = `${start}|${ppSec}|${Array.from(lanes.keys()).join(',')}`
  if (key !== dotCacheKey) {
    dotCache = new Map()
    dotCacheKey = key
  }

  const previous = dotCache
  const current = new Map<string, DotData>()
  const out: DotData[] = []
  for (const msg of messagesStore.messages) {
    let dot = previous.get(msg.message_id)
    if (!dot) {
      const offsetSec = (Date.parse(msg.timestamp) - start) / 1000
      const laneIdx = lanes.get(msg.channel) ?? 0
      dot = {
        messageId: msg.message_id,
        x: offsetSec * ppSec,
        y: AXIS_HEIGHT + laneIdx * LANE_HEIGHT + LANE_HEIGHT / 2,
        r: Math.min(Math.max(msg.subscriber_count * 2 + 4, 4), 14),
        color: channelColor(msg.channel),
        msg,
      }
    }
    current.set(msg.message_id, dot)
    out.push(dot)
  }
  // Rebuilt rather than pruned, so evicted messages cannot linger in the cache.
  dotCache = current
  return out
})

let userScrolled = false
const scrollLeft = ref(0)

function onScroll() {
  if (!scrollWrap.value) return
  const el = scrollWrap.value
  scrollLeft.value = el.scrollLeft
  const atEnd = el.scrollLeft + el.clientWidth >= el.scrollWidth - 20
  if (!atEnd) userScrolled = true
  else userScrolled = false
}

function scrollToEnd() {
  if (scrollWrap.value) {
    scrollWrap.value.scrollLeft = scrollWrap.value.scrollWidth
    scrollLeft.value = scrollWrap.value.scrollLeft
  }
}

// Only the dots the viewport can show are handed to the DOM. The plot is as wide
// as the whole retained history — minutes of it — while the window shows a
// fraction, and every circle costs two event listeners. The margin keeps a
// screenful on each side so panning does not reveal blanks.
const CULL_MARGIN_PX = 400

const visibleDots = computed<DotData[]>(() => {
  const from = scrollLeft.value - CULL_MARGIN_PX
  const to = scrollLeft.value + availableWidth.value + CULL_MARGIN_PX
  return dots.value.filter(dot => dot.x >= from && dot.x <= to)
})

watch(
  () => messagesStore.messageCount,
  () => {
    if (autoScroll.value && !userScrolled) {
      nextTick(scrollToEnd)
    }
  }
)

watch(autoScroll, (v) => {
  if (v) {
    userScrolled = false
    nextTick(scrollToEnd)
  }
})
</script>

<style scoped>
.timeline-container {
  display: flex;
  overflow: hidden;
  width: 100%;
  position: relative;
}

.timeline-lanes {
  flex-shrink: 0;
  width: 160px;
  border-right: 1px solid #444;
  background: rgb(var(--v-theme-surface));
  z-index: 2;
}

.timeline-axis-label {
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid #444;
}

.timeline-lane-label {
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px dashed #333;
  padding: 0 4px;
}

.timeline-scroll {
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
  position: relative;
}

.timeline-svg {
  display: block;
}

.timeline-dot {
  cursor: pointer;
  transition: opacity 0.15s;
}
.timeline-dot:hover {
  opacity: 1 !important;
  filter: brightness(1.3);
}

.timeline-tooltip {
  position: absolute;
  background: rgba(30, 30, 30, 0.95);
  border: 1px solid #555;
  border-radius: 6px;
  padding: 6px 10px;
  pointer-events: none;
  z-index: 10;
  min-width: 160px;
  max-width: 320px;
  word-break: break-word;
}
</style>
