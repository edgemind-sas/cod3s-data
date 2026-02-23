<template>
  <BaseEdge
    :id="id"
    :path="path"
    :label="label"
    :label-x="labelX"
    :label-y="labelY"
    :label-style="labelStyle"
    :label-show-bg="labelShowBg"
    :label-bg-style="labelBgStyle"
    :label-bg-padding="labelBgPadding"
    :label-bg-border-radius="labelBgBorderRadius"
    :marker-start="markerStart"
    :marker-end="markerEnd"
    :interaction-width="interactionWidth"
    :style="style"
  />
  <g :key="tier" :class="['edge-particles', { 'edge-particles--active': tier !== 'idle' }]" :opacity="groupOpacity">
    <circle
      v-for="p in particles"
      :key="p.id"
      :r="p.radius"
      :fill="color"
      :opacity="p.opacity"
    >
      <animateMotion :dur="p.duration" repeatCount="indefinite" :begin="p.delay" :path="path" />
    </circle>
  </g>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { BaseEdge, getSmoothStepPath } from '@vue-flow/core'
import type { EdgeProps } from '@vue-flow/core'
import { channelColor } from '@/utils/channelColors'
import { useTopologyStore } from '@/stores/topology'

const props = defineProps<EdgeProps>()
const topologyStore = useTopologyStore()

const pathParams = computed(() => getSmoothStepPath({
  sourceX: props.sourceX,
  sourceY: props.sourceY,
  sourcePosition: props.sourcePosition,
  targetX: props.targetX,
  targetY: props.targetY,
  targetPosition: props.targetPosition,
}))

const path = computed(() => pathParams.value[0])
const labelX = computed(() => pathParams.value[1])
const labelY = computed(() => pathParams.value[2])

const channel = computed(() => (props.data as any)?.channel ?? '')
const pattern = computed(() => (props.data as any)?.pattern ?? '')

// Read rate directly from the reactive store so animations update in real-time.
// For parent-child edges (UnpackTransform), the publisher's channel (e.g. "sensors.egm")
// has no direct traffic; the actual messages flow on the pattern channel
// (e.g. "sensors.egm.pressure"), so we check both.
const rate = computed(() =>
  topologyStore.getChannelRate(channel.value) || topologyStore.getChannelRate(pattern.value)
)
const color = computed(() => channelColor(channel.value))

type Tier = 'idle' | 'low' | 'medium' | 'high'

const tier = computed<Tier>(() => {
  const r = rate.value
  if (r <= 0) return 'idle'
  if (r < 5) return 'low'
  if (r <= 30) return 'medium'
  return 'high'
})

const TIER_CONFIG = {
  idle:   { count: 0, duration: 0,   radius: 0,   groupOpacity: 0 },
  low:    { count: 2, duration: 2.5, radius: 3,   groupOpacity: 0.7 },
  medium: { count: 3, duration: 1.5, radius: 3.5, groupOpacity: 0.85 },
  high:   { count: 5, duration: 0.8, radius: 4,   groupOpacity: 1.0 },
} as const

const groupOpacity = computed(() => TIER_CONFIG[tier.value].groupOpacity)

const particles = computed(() => {
  const cfg = TIER_CONFIG[tier.value]
  if (cfg.count === 0) return []
  const dur = cfg.duration
  const arr = []
  for (let i = 0; i < cfg.count; i++) {
    const delay = (dur / cfg.count) * i
    const opacityFactor = 1 - (i / cfg.count) * 0.6
    arr.push({
      id: `p${i}`,
      delay: `${delay}s`,
      duration: `${dur}s`,
      opacity: opacityFactor,
      radius: cfg.radius,
    })
  }
  return arr
})
</script>

<style scoped>
.edge-particles {
  opacity: 0;
  transition: opacity 0.5s ease-in;
  pointer-events: none;
}
.edge-particles--active {
  opacity: 1;
  transition: opacity 0.3s ease-out;
}
</style>
