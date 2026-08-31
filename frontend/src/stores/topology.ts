import { defineStore } from 'pinia'
import { ref, computed, reactive } from 'vue'
import type { TopologyNode, TopologyEdge } from '@/types'

export const useTopologyStore = defineStore('topology', () => {
  const nodes = ref<TopologyNode[]>([])
  const edges = ref<TopologyEdge[]>([])

  const sources = computed(() => nodes.value.filter(n => n.type === 'source'))
  const transformations = computed(() => nodes.value.filter(n => n.type === 'transformation'))
  const destinations = computed(() => nodes.value.filter(n => n.type === 'destination'))

  // --- Channel rate tracking (2-layer: non-reactive counters + reactive rates) ---
  const channelRates = reactive<Record<string, number>>({})
  const _channelCounters: Record<string, { count: number; lastTick: number }> = {}
  const _channelTimers: Record<string, ReturnType<typeof setTimeout>> = {}
  const ACTIVITY_TIMEOUT_MS = 3000
  const RATE_TICK_MS = 500
  const EMA_ALPHA = 0.5
  let _rateInterval: ReturnType<typeof setInterval> | null = null

  function _startTicker() {
    if (_rateInterval) return
    _rateInterval = setInterval(() => {
      const now = Date.now()
      let anyActive = false
      for (const ch of Object.keys(_channelCounters)) {
        const counter = _channelCounters[ch]
        const elapsed = (now - counter.lastTick) / 1000
        if (elapsed <= 0) continue
        const instantRate = counter.count / elapsed
        const prev = channelRates[ch] ?? 0
        channelRates[ch] = EMA_ALPHA * instantRate + (1 - EMA_ALPHA) * prev
        counter.count = 0
        counter.lastTick = now
        if (channelRates[ch] > 0.01) anyActive = true
      }
      if (!anyActive) _stopTicker()
    }, RATE_TICK_MS)
  }

  function _stopTicker() {
    if (_rateInterval) {
      clearInterval(_rateInterval)
      _rateInterval = null
    }
  }

  function _markSingle(ch: string) {
    if (!_channelCounters[ch]) {
      _channelCounters[ch] = { count: 0, lastTick: Date.now() }
    }
    _channelCounters[ch].count++
    _startTicker()

    // Reset inactivity timeout
    if (_channelTimers[ch]) clearTimeout(_channelTimers[ch])
    _channelTimers[ch] = setTimeout(() => {
      channelRates[ch] = 0
      delete _channelCounters[ch]
      delete _channelTimers[ch]
    }, ACTIVITY_TIMEOUT_MS)
  }

  function markChannelActive(channel: string) {
    _markSingle(channel)
    // Also mark parent channels so parent-child edges (UnpackTransform) animate.
    // e.g. "sensors.egm.pressure" → also marks "sensors.egm"
    const parts = channel.split('.')
    for (let i = parts.length - 1; i >= 2; i--) {
      _markSingle(parts.slice(0, i).join('.'))
    }
  }

  function isChannelActive(channel: string): boolean {
    return (channelRates[channel] ?? 0) > 0
  }

  function getChannelRate(channel: string): number {
    return channelRates[channel] ?? 0
  }

  function _cleanupRateTracking() {
    _stopTicker()
    for (const ch of Object.keys(_channelTimers)) {
      clearTimeout(_channelTimers[ch])
      delete _channelTimers[ch]
    }
    for (const ch of Object.keys(_channelCounters)) {
      delete _channelCounters[ch]
    }
    for (const ch of Object.keys(channelRates)) {
      delete channelRates[ch]
    }
  }

  function setTopology(data: { nodes: any[]; edges: any[] }) {
    _cleanupRateTracking()
    nodes.value = data.nodes.map(n => ({
      id: n.component_id,
      type: n.component_type as TopologyNode['type'],
      state: n.state,
      label: n.label || '',
      description: n.description || '',
      channels: n.channels ?? { publishes: [], subscribes: [], parameters: [] },
    }))
    edges.value = data.edges.map(e => ({
      source_id: e.source_id,
      target_id: e.target_id,
      channel: e.channel,
      pattern: e.pattern,
      // Kept: this is what tells a parameter edge from a data one.
      kind: e.kind ?? 'data',
      param: e.param,
    }))
  }

  function updateComponent(data: { component_id: string; component_type: string; new_state: string; label?: string }) {
    const existing = nodes.value.find(n => n.id === data.component_id)
    if (existing) {
      existing.state = data.new_state
      if (data.label !== undefined) {
        existing.label = data.label
      }
    } else {
      nodes.value.push({
        id: data.component_id,
        type: data.component_type as TopologyNode['type'],
        state: data.new_state,
        label: data.label || '',
        description: '',
        channels: { publishes: [], subscribes: [], parameters: [] },
      })
    }
  }

  function updateSubscription(data: { pattern: string; action: string; subscriber_id: string }) {
    if (data.action === 'subscribe') {
      edges.value.push({
        source_id: '',
        target_id: data.subscriber_id,
        channel: '',
        pattern: data.pattern,
        kind: 'data',
      })
    } else if (data.action === 'unsubscribe') {
      edges.value = edges.value.filter(
        e => !(e.pattern === data.pattern && e.target_id === data.subscriber_id)
      )
    }
  }

  return { nodes, edges, sources, transformations, destinations, channelRates, markChannelActive, isChannelActive, getChannelRate, setTopology, updateComponent, updateSubscription }
})
