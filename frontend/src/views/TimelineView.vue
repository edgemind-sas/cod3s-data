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
          :title="autoScroll ? 'Freeze the window' : 'Follow the newest messages'"
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
              <v-chip
                size="small"
                variant="flat"
                :color="channelColor(ch)"
                :title="ch"
                class="lane-chip"
              >
                <!-- Truncated from the LEFT: six channels share the prefix
                     `sensors.egm.temperature_`, so cutting the tail left five
                     lanes labelled identically. The end is what tells them
                     apart; the full name is in the tooltip. -->
                <bdi>{{ ch }}</bdi>
              </v-chip>
            </div>
          </div>

          <!-- Plot: exactly as wide as the window it shows -->
          <div class="timeline-scroll">
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

              <!-- Everything before the oldest retained message. Retention is
                   counted in messages, not in seconds, so a fast pipeline fills
                   the window only partly and the left of the plot is empty —
                   which reads as a broken layout rather than as "nothing is
                   kept from back then". Naming it costs one rectangle. -->
              <g v-if="retentionEdgeX > 24">
                <rect
                  x="0"
                  :y="AXIS_HEIGHT"
                  :width="retentionEdgeX"
                  :height="svgHeight - AXIS_HEIGHT"
                  fill="rgba(255,255,255,0.025)"
                />
                <line
                  :x1="retentionEdgeX"
                  :y1="AXIS_HEIGHT"
                  :x2="retentionEdgeX"
                  :y2="svgHeight"
                  stroke="#666"
                  stroke-width="1"
                  stroke-dasharray="3,3"
                />
                <text
                  :x="retentionEdgeX - 8"
                  :y="AXIS_HEIGHT + 14"
                  text-anchor="end"
                  fill="#777"
                  font-size="10"
                >
                  beyond retention
                </text>
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
                :key="dot.uid"
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
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { useMessagesStore, type StoredMessage } from '@/stores/messages'
// The same function and the same palette were declared here as well. They agreed
// by luck; sharing one keeps a channel the same colour in both views for good.
import { channelColor } from '@/utils/channelColors'

const AXIS_HEIGHT = 30
const LANE_HEIGHT = 40
const LANE_LABELS_WIDTH = 200
// Smallest dot diameter: below this spacing, circles overlap outright.
const DOT_MERGE_PX = 8

const messagesStore = useMessagesStore()

const zoomLevels = [
  { label: '30s', windowSec: 30 },
  { label: '60s', windowSec: 60 },
  { label: '5min', windowSec: 300 },
]
const zoomIndex = ref(1)
const autoScroll = ref(true)
const containerEl = ref<HTMLElement | null>(null)
const containerWidth = ref(800)

let resizeObserver: ResizeObserver | null = null

// The plot lives behind `v-else`, so on a cold page — no messages yet — there
// is no element to measure at mount: the observer was never attached and the
// width stayed at its 800px placeholder for the rest of the session, whatever
// the window size. Watching the ref attaches it the moment the element appears.
watch(containerEl, (el) => {
  resizeObserver?.disconnect()
  resizeObserver = null
  if (!el) return
  containerWidth.value = el.clientWidth - LANE_LABELS_WIDTH
  resizeObserver = new ResizeObserver((entries) => {
    for (const entry of entries) {
      containerWidth.value = entry.contentRect.width - LANE_LABELS_WIDTH
    }
  })
  resizeObserver.observe(el)
}, { immediate: true, flush: 'post' })

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
})

interface DotData {
  uid: number
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

const TOOLTIP_WIDTH_ESTIMATE = 200
const tooltipLeft = computed(() => {
  if (!hoveredDot.value) return 0
  const x = hoveredDot.value.x + LANE_LABELS_WIDTH + 16
  const rightEdge = containerWidth.value + LANE_LABELS_WIDTH - TOOLTIP_WIDTH_ESTIMATE
  return Math.min(Math.max(x, LANE_LABELS_WIDTH), rightEdge)
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

/**
 * A window of fixed width, anchored on the newest message.
 *
 * The origin used to follow the *oldest* retained message, snapped to a ten
 * second grid. Once the store is full and evicting, that origin advances one
 * grid step at a time — and every dot on the plot jumps a tenth of the window
 * to the left at once. That is the timeline "going back to zero".
 *
 * Anchoring on the newest message instead makes the window slide: a dot enters
 * at the right edge and drifts left as time passes, at the same speed as time.
 * Nothing jumps, because nothing depends on which message happens to be oldest.
 *
 * The horizontal scroll is gone with it, and loses nothing: `pxPerSecond` was
 * `availableWidth / duration`, so the plot was always exactly as wide as its
 * viewport and there was never anything to scroll to. The zoom buttons now
 * choose the window outright, which is what they looked like they did.
 */
const windowSec = computed(() => currentWindow.value.windowSec)

const pxPerSecond = computed(() => availableWidth.value / windowSec.value)

// Freezing the window is what the pause button now does: the view stops
// following the flow so a dot can be read, while messages keep arriving.
const frozenEnd = ref<number | null>(null)

const timeRange = computed(() => {
  const msgs = messagesStore.messages
  if (msgs.length === 0) return { start: 0, end: 0 }
  const latest = Date.parse(msgs[msgs.length - 1].timestamp)
  const end = frozenEnd.value ?? latest
  return { start: end - windowSec.value * 1000, end }
})

const svgWidth = computed(() => availableWidth.value)
const svgHeight = computed(() => AXIS_HEIGHT + Math.max(messagesStore.channels.length, 1) * LANE_HEIGHT)

const channelIndex = computed(() => {
  const map = new Map<string, number>()
  messagesStore.channels.forEach((ch, i) => map.set(ch, i))
  return map
})

const timeTicks = computed(() => {
  const { start } = timeRange.value
  if (!start) return []
  const dur = windowSec.value
  const interval = dur > 300 ? 60 : dur > 120 ? 30 : dur > 60 ? 15 : 5

  // Ticks land on round seconds rather than on the window's edge, so the labels
  // stay put while the window slides underneath them.
  const ticks: { x: number; label: string }[] = []
  const firstTick = Math.ceil(start / (interval * 1000)) * interval * 1000
  for (let t = firstTick; t <= start + dur * 1000; t += interval * 1000) {
    ticks.push({
      x: ((t - start) / 1000) * pxPerSecond.value,
      label: new Date(t).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }),
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
// Straightforward, and cheap enough: the store is capped, so this is a few
// hundred objects per frame. An earlier version memoised them by message_id —
// which is not unique, so two publications of the same message shared one dot
// and the second was drawn in the first one's lane, in the first one's colour.
const dots = computed<DotData[]>(() => {
  const { start } = timeRange.value
  const ppSec = pxPerSecond.value
  const lanes = channelIndex.value
  return messagesStore.messages.map((msg) => {
    const offsetSec = (Date.parse(msg.timestamp) - start) / 1000
    const laneIdx = lanes.get(msg.channel) ?? 0
    return {
      uid: msg.uid,
      x: offsetSec * ppSec,
      y: AXIS_HEIGHT + laneIdx * LANE_HEIGHT + LANE_HEIGHT / 2,
      r: Math.min(Math.max(msg.subscriber_count * 2 + 4, 4), 14),
      color: channelColor(msg.channel),
      msg,
    }
  })
})

// Where the retained history begins. Left of it the store simply holds
// nothing, however far back the window reaches.
const retentionEdgeX = computed(() => {
  const all = dots.value
  if (!all.length) return 0
  return Math.max(0, Math.min(all[0].x, svgWidth.value))
})

// Only what falls inside the window reaches the DOM. The store holds more than
// the window shows — everything older has slid off the left edge — and every
// circle costs two event listeners.
const visibleDots = computed<DotData[]>(() => {
  const width = svgWidth.value
  // Dots wider than the gap between them hide each other: at a few hundred
  // messages per lane across a thousand pixels the lane is a solid bar, drawn
  // with one circle and two listeners per message. Only the widest of each
  // cluster is kept — the picture is the same, the DOM is a fraction of it.
  const kept = new Map<string, DotData>()
  const out: DotData[] = []
  for (const dot of dots.value) {
    if (dot.x < -8 || dot.x > width + 8) continue
    const bin = `${dot.y}|${Math.round(dot.x / DOT_MERGE_PX)}`
    const seen = kept.get(bin)
    if (!seen) {
      kept.set(bin, dot)
      out.push(dot)
    } else if (dot.r > seen.r) {
      // Keep the bigger one in place, so a busy point still reads as busy.
      out[out.indexOf(seen)] = dot
      kept.set(bin, dot)
    }
  }
  return out
})

// The pause button freezes the window instead of stopping a scroll: there is
// no scroll any more, the window simply stops following the newest message.
watch(autoScroll, (following) => {
  const msgs = messagesStore.messages
  frozenEnd.value = following || !msgs.length
    ? null
    : Date.parse(msgs[msgs.length - 1].timestamp)
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
  width: 200px;
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
  overflow: hidden;
  position: relative;
}

.timeline-svg {
  display: block;
}

.lane-chip {
  max-width: 188px;
  direction: rtl;
  overflow: hidden;
}
.lane-chip :deep(.v-chip__content) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
