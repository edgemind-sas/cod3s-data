import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { TopologyNode, TopologyEdge } from '@/types'

export const useTopologyStore = defineStore('topology', () => {
  const nodes = ref<TopologyNode[]>([])
  const edges = ref<TopologyEdge[]>([])

  const sources = computed(() => nodes.value.filter(n => n.type === 'source'))
  const transformations = computed(() => nodes.value.filter(n => n.type === 'transformation'))
  const destinations = computed(() => nodes.value.filter(n => n.type === 'destination'))

  function setTopology(data: { nodes: any[]; edges: any[] }) {
    nodes.value = data.nodes.map(n => ({
      id: n.component_id,
      type: n.component_type as TopologyNode['type'],
      state: n.state,
      channels: n.channels ?? { publishes: [], subscribes: [] },
    }))
    edges.value = data.edges.map(e => ({
      source_id: e.source_id,
      target_id: e.target_id,
      channel: e.channel,
      pattern: e.pattern,
    }))
  }

  function updateComponent(data: { component_id: string; component_type: string; new_state: string }) {
    const existing = nodes.value.find(n => n.id === data.component_id)
    if (existing) {
      existing.state = data.new_state
    } else {
      nodes.value.push({
        id: data.component_id,
        type: data.component_type as TopologyNode['type'],
        state: data.new_state,
        channels: { publishes: [], subscribes: [] },
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
      })
    } else if (data.action === 'unsubscribe') {
      edges.value = edges.value.filter(
        e => !(e.pattern === data.pattern && e.target_id === data.subscriber_id)
      )
    }
  }

  return { nodes, edges, sources, transformations, destinations, setTopology, updateComponent, updateSubscription }
})
