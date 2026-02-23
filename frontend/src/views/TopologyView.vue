<template>
  <div>
    <div class="d-flex align-center mb-4">
      <h1 class="text-h5">Pipeline Topology</h1>
      <v-spacer />
      <v-btn v-if="topologyStore.nodes.length > 0" size="small" variant="outlined" prepend-icon="mdi-auto-fix" @click="resetLayout">
        Reset layout
      </v-btn>
    </div>

    <v-card v-if="topologyStore.nodes.length === 0">
      <v-card-text class="text-center text-medium-emphasis">
        <v-icon size="48" class="mb-2">mdi-graph</v-icon>
        <p>Waiting for pipeline components...</p>
        <p class="text-caption">Components will appear here once the pipeline starts.</p>
      </v-card-text>
    </v-card>

    <div v-else class="topology-flow-container">
      <VueFlow
        :nodes="layoutedNodes"
        :edges="styledEdges"
        :nodes-draggable="true"
        :nodes-connectable="false"
        :pan-on-drag="true"
        :zoom-on-scroll="true"
        fit-view-on-init
        @node-click="onNodeClick"
        @pane-click="onPaneClick"
        @nodes-change="onNodesChange"
      >
        <!-- Source node -->
        <template #node-source="{ data }">
          <div
            class="pipeline-node pipeline-node--source"
            :class="{ 'pipeline-node--selected': selectedNodeId === data.nodeId }"
          >
            <div class="pipeline-node__header">
              <v-icon size="16" class="mr-1" color="blue">mdi-database-arrow-right</v-icon>
              <span class="pipeline-node__label">{{ data.label || data.nodeId }}</span>
            </div>
            <div v-if="data.label" class="pipeline-node__id">{{ data.nodeId }}</div>
            <v-chip :color="stateColor(data.state)" size="x-small" class="mt-1">
              {{ data.state }}
            </v-chip>
            <div v-for="ch in data.channels.publishes" :key="ch" class="pipeline-node__channel">
              &rarr; {{ ch }}
            </div>
            <Handle type="source" :position="Position.Right" />
          </div>
        </template>

        <!-- Transformation node -->
        <template #node-transformation="{ data }">
          <div
            class="pipeline-node pipeline-node--transformation"
            :class="{ 'pipeline-node--selected': selectedNodeId === data.nodeId }"
          >
            <Handle type="target" :position="Position.Left" />
            <div class="pipeline-node__header">
              <v-icon size="16" class="mr-1" color="orange">mdi-cog</v-icon>
              <span class="pipeline-node__label">{{ data.label || data.nodeId }}</span>
            </div>
            <div v-if="data.label" class="pipeline-node__id">{{ data.nodeId }}</div>
            <v-chip :color="stateColor(data.state)" size="x-small" class="mt-1">
              {{ data.state }}
            </v-chip>
            <div v-for="ch in data.channels.subscribes" :key="'in-'+ch" class="pipeline-node__channel">
              &larr; {{ ch }}
            </div>
            <div v-for="ch in data.channels.publishes" :key="'out-'+ch" class="pipeline-node__channel">
              &rarr; {{ ch }}
            </div>
            <Handle type="source" :position="Position.Right" />
          </div>
        </template>

        <!-- Destination node -->
        <template #node-destination="{ data }">
          <div
            class="pipeline-node pipeline-node--destination"
            :class="{ 'pipeline-node--selected': selectedNodeId === data.nodeId }"
          >
            <Handle type="target" :position="Position.Left" />
            <div class="pipeline-node__header">
              <v-icon size="16" class="mr-1" color="green">mdi-database-arrow-left</v-icon>
              <span class="pipeline-node__label">{{ data.label || data.nodeId }}</span>
            </div>
            <div v-if="data.label" class="pipeline-node__id">{{ data.nodeId }}</div>
            <v-chip :color="stateColor(data.state)" size="x-small" class="mt-1">
              {{ data.state }}
            </v-chip>
            <div v-for="ch in data.channels.subscribes" :key="ch" class="pipeline-node__channel">
              &larr; {{ ch }}
            </div>
          </div>
        </template>
        <template #edge-animated="edgeProps">
          <AnimatedEdge v-bind="edgeProps" />
        </template>
      </VueFlow>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { VueFlow, Position, Handle, MarkerType } from '@vue-flow/core'
import type { Node as FlowNode, Edge as FlowEdge, NodeMouseEvent, NodeChange } from '@vue-flow/core'
import { applyNodeChanges } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import dagre from '@dagrejs/dagre'
import { useTopologyStore } from '@/stores/topology'
import AnimatedEdge from '@/components/edges/AnimatedEdge.vue'

const NODE_WIDTH = 220
const NODE_HEIGHT = 100

const topologyStore = useTopologyStore()
const selectedNodeId = ref<string | null>(null)

// --- Convert store nodes to Vue Flow nodes ---
const flowNodes = computed<FlowNode[]>(() =>
  topologyStore.nodes.map(node => ({
    id: node.id,
    type: node.type,
    position: { x: 0, y: 0 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: {
      nodeId: node.id,
      label: node.label,
      state: node.state,
      channels: node.channels,
    },
  }))
)

// --- Convert store edges to Vue Flow edges (filter incomplete) ---
const flowEdges = computed<FlowEdge[]>(() =>
  topologyStore.edges
    .filter(e => e.source_id && e.target_id)
    .map((e, i) => ({
      id: `e-${e.source_id}-${e.target_id}-${i}`,
      source: e.source_id,
      target: e.target_id,
      type: 'animated',
      label: e.pattern,
      markerEnd: { type: MarkerType.ArrowClosed },
      data: {
        channel: e.channel,
        pattern: e.pattern,
      },
    }))
)

// --- Dagre layout ---
function applyDagreLayout(nodes: FlowNode[], edges: FlowEdge[]): FlowNode[] {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 50, ranksep: 120 })

  for (const node of nodes) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target)
  }

  dagre.layout(g)

  return nodes.map(node => {
    const pos = g.node(node.id)
    return {
      ...node,
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
    }
  })
}

// --- Layouted nodes (recomputed when topology structure changes) ---
const layoutedNodes = ref<FlowNode[]>([])

// Structural key: only changes when node IDs or edge connections change
const topologyKey = computed(() => {
  const nodeIds = topologyStore.nodes.map(n => n.id).sort().join(',')
  const edgeIds = topologyStore.edges.map(e => `${e.source_id}-${e.target_id}`).sort().join(',')
  return `${nodeIds}|${edgeIds}`
})

// Re-layout only on structural changes (new/removed nodes or edges)
watch(topologyKey, () => {
  if (flowNodes.value.length > 0) {
    layoutedNodes.value = applyDagreLayout(flowNodes.value, flowEdges.value)
  } else {
    layoutedNodes.value = []
  }
}, { immediate: true })

// Update node data (state, label) without touching positions
watch(flowNodes, (newNodes) => {
  for (const newNode of newNodes) {
    const existing = layoutedNodes.value.find(n => n.id === newNode.id)
    if (existing) {
      existing.data = newNode.data
    }
  }
}, { deep: true })

function onNodesChange(changes: NodeChange[]) {
  layoutedNodes.value = applyNodeChanges(changes, layoutedNodes.value as any)
}

function resetLayout() {
  if (flowNodes.value.length > 0) {
    layoutedNodes.value = applyDagreLayout(flowNodes.value, flowEdges.value)
  }
}

// --- Click-to-highlight ---
const styledEdges = computed<FlowEdge[]>(() => {
  const sel = selectedNodeId.value
  return flowEdges.value.map(edge => {
    if (!sel) {
      return {
        ...edge,
        style: { stroke: 'rgba(255,255,255,0.25)', strokeWidth: 2 },
        labelStyle: { fill: 'rgba(255,255,255,0.5)', fontSize: '10px' },
      }
    }
    if (edge.target === sel) {
      // Incoming edge → blue
      return {
        ...edge,
        style: { stroke: '#42A5F5', strokeWidth: 3 },
        labelStyle: { fill: '#42A5F5', fontSize: '10px', fontWeight: 'bold' },
      }
    }
    if (edge.source === sel) {
      // Outgoing edge → orange
      return {
        ...edge,
        style: { stroke: '#FFA726', strokeWidth: 3 },
        labelStyle: { fill: '#FFA726', fontSize: '10px', fontWeight: 'bold' },
      }
    }
    // Dimmed
    return {
      ...edge,
      style: { stroke: 'rgba(255,255,255,0.08)', strokeWidth: 1 },
      labelStyle: { fill: 'rgba(255,255,255,0.15)', fontSize: '10px' },
    }
  })
})

function onNodeClick({ node }: NodeMouseEvent) {
  selectedNodeId.value = selectedNodeId.value === node.id ? null : node.id
}

function onPaneClick() {
  selectedNodeId.value = null
}

function stateColor(state: string): string {
  switch (state) {
    case 'running': return 'green'
    case 'created': return 'blue-grey'
    case 'paused': return 'orange'
    case 'stopped': return 'red'
    case 'error': return 'red'
    default: return 'grey'
  }
}
</script>

<style scoped>
.topology-flow-container {
  height: calc(100vh - 160px);
  min-height: 400px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  overflow: hidden;
}

/* Dark theme overrides for Vue Flow */
:deep(.vue-flow) {
  background: #121212;
}

:deep(.vue-flow__background) {
  display: none;
}

:deep(.vue-flow__edge-text) {
  font-size: 10px;
}

:deep(.vue-flow__edge-textbg) {
  fill: #1e1e1e;
}

:deep(.vue-flow__handle) {
  width: 8px;
  height: 8px;
  background: rgba(255, 255, 255, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.5);
}

/* Pipeline node styles */
.pipeline-node {
  padding: 8px 12px;
  min-width: 180px;
  max-width: 220px;
  background: #1e1e1e;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-left: 3px solid;
  color: rgba(255, 255, 255, 0.87);
  font-size: 12px;
  cursor: pointer;
  transition: box-shadow 0.2s, border-color 0.2s;
}

.pipeline-node--source {
  border-left-color: #42A5F5;
}

.pipeline-node--transformation {
  border-left-color: #FFA726;
}

.pipeline-node--destination {
  border-left-color: #66BB6A;
}

.pipeline-node--selected {
  border-color: #90CAF9;
  box-shadow: 0 0 12px rgba(66, 165, 245, 0.4);
}

.pipeline-node__header {
  display: flex;
  align-items: center;
  font-weight: 500;
}

.pipeline-node__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pipeline-node__id {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.4);
  margin-top: 1px;
}

.pipeline-node__channel {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.5);
  margin-top: 2px;
}

/* Force dark theme on Vuetify chips inside Vue Flow nodes */
:deep(.pipeline-node .v-chip) {
  background: rgba(255, 255, 255, 0.08) !important;
  color: rgba(255, 255, 255, 0.87) !important;
}
</style>
