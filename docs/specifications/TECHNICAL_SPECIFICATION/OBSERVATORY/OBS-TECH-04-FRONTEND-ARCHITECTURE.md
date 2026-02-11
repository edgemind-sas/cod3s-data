# Observatory Frontend Architecture - Technical Specification

**Document:** OBS-TECH-04-FRONTEND-ARCHITECTURE.md
**Version:** 1.0.0
**Date:** 2026-02-11
**Status:** Draft
**Implements:** [OBS-04](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-04-PIPELINE-TOPOLOGY.md) through [OBS-07](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-07-METRICS-DASHBOARD.md)

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← OBS-TECH-03](OBS-TECH-03-WEBSOCKET-PROTOCOL.md) | [OBS-TECH-00-OVERVIEW](OBS-TECH-00-OVERVIEW.md) | [OBS-TECH-05 →](OBS-TECH-05-COMPONENT-LIBRARY.md) |

---

## Table of Contents

1. [Project Structure](#project-structure)
2. [Vue Router](#vue-router)
3. [Component Hierarchy](#component-hierarchy)
4. [Composables](#composables)
5. [TypeScript Types](#typescript-types)
6. [Build Configuration](#build-configuration)

---

## Project Structure

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── src/
│   ├── main.ts                 # App entry point
│   ├── App.vue                 # Root component
│   ├── router/
│   │   └── index.ts            # Vue Router configuration
│   ├── stores/                 # Pinia stores (see OBS-TECH-06)
│   │   ├── connection.ts       # WebSocket connection state
│   │   ├── topology.ts         # Pipeline topology
│   │   ├── messages.ts         # Message buffer
│   │   ├── metrics.ts          # Metric data points
│   │   └── debug.ts            # Debug state
│   ├── views/                  # Page-level components
│   │   ├── TopologyView.vue    # Pipeline DAG page
│   │   ├── TimelineView.vue    # Temporal timeline page
│   │   ├── MessagesView.vue    # Message list + inspector page
│   │   ├── MetricsView.vue     # Metrics dashboard page
│   │   └── DebugView.vue       # Debug controls + session page
│   ├── components/             # Reusable components (see OBS-TECH-05)
│   │   ├── layout/
│   │   │   ├── AppLayout.vue       # Main layout (sidebar + content)
│   │   │   ├── AppSidebar.vue      # Navigation sidebar
│   │   │   └── InspectorPanel.vue  # Slide-out message inspector
│   │   ├── topology/
│   │   │   ├── PipelineGraph.vue   # @vue-flow DAG
│   │   │   ├── SourceNode.vue      # Custom source node
│   │   │   ├── TransformNode.vue   # Custom transform node
│   │   │   └── DestinationNode.vue # Custom destination node
│   │   ├── timeline/
│   │   │   └── TimelineChart.vue   # Canvas-based timeline
│   │   ├── messages/
│   │   │   ├── MessageList.vue     # Scrollable message list
│   │   │   ├── MessageDetail.vue   # Tabbed detail view
│   │   │   └── MessageDiff.vue     # Side-by-side comparison
│   │   ├── metrics/
│   │   │   ├── MetricCard.vue      # Single metric card
│   │   │   ├── MetricGrid.vue      # Dashboard grid layout
│   │   │   └── GlobalStats.vue     # Top bar stats
│   │   └── debug/
│   │       ├── DebugToolbar.vue    # Floating debug controls
│   │       ├── BreakpointPanel.vue # Breakpoint management
│   │       └── StepHistory.vue     # Step log
│   ├── composables/            # Reusable composition functions
│   │   ├── useWebSocket.ts     # WebSocket connection + reconnect
│   │   ├── useTopology.ts      # Topology data transformations
│   │   ├── useDebug.ts         # Debug command helpers
│   │   ├── useMessages.ts      # Message filtering + search
│   │   └── useMetrics.ts       # Metric data processing
│   ├── services/
│   │   └── websocket.ts        # Low-level WebSocket client
│   └── types/
│       ├── protocol.ts         # WebSocket protocol types
│       ├── topology.ts         # Topology node/edge types
│       ├── messages.ts         # Message types
│       ├── metrics.ts          # Metric types
│       └── debug.ts            # Debug state types
├── public/
│   └── favicon.ico
└── tests/                      # Frontend tests (see OBS-TECH-07)
    ├── unit/
    ├── components/
    └── e2e/
```

---

## Vue Router

### Route Configuration

```typescript
// src/router/index.ts
import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/topology',
  },
  {
    path: '/topology',
    name: 'Topology',
    component: () => import('@/views/TopologyView.vue'),
    meta: { title: 'Pipeline Topology', icon: 'mdi-graph' },
  },
  {
    path: '/timeline',
    name: 'Timeline',
    component: () => import('@/views/TimelineView.vue'),
    meta: { title: 'Temporal Timeline', icon: 'mdi-timeline' },
  },
  {
    path: '/messages',
    name: 'Messages',
    component: () => import('@/views/MessagesView.vue'),
    meta: { title: 'Message Inspector', icon: 'mdi-email-search' },
  },
  {
    path: '/metrics',
    name: 'Metrics',
    component: () => import('@/views/MetricsView.vue'),
    meta: { title: 'Metrics Dashboard', icon: 'mdi-chart-line' },
  },
  {
    path: '/debug',
    name: 'Debug',
    component: () => import('@/views/DebugView.vue'),
    meta: { title: 'Debug Controls', icon: 'mdi-bug' },
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
```

### Navigation

| Route | View | Primary Component | Sidebar Icon |
|-------|------|------------------|-------------|
| `/topology` | TopologyView | PipelineGraph | `mdi-graph` |
| `/timeline` | TimelineView | TimelineChart | `mdi-timeline` |
| `/messages` | MessagesView | MessageList + MessageDetail | `mdi-email-search` |
| `/metrics` | MetricsView | MetricGrid + GlobalStats | `mdi-chart-line` |
| `/debug` | DebugView | DebugToolbar + BreakpointPanel | `mdi-bug` |

---

## Component Hierarchy

```
App.vue
└── AppLayout.vue
    ├── AppSidebar.vue           (navigation + connection status)
    ├── DebugToolbar.vue         (floating, visible when debug active)
    ├── <router-view>            (current page)
    │   ├── TopologyView.vue
    │   │   └── PipelineGraph.vue
    │   ├── TimelineView.vue
    │   │   └── TimelineChart.vue
    │   ├── MessagesView.vue
    │   │   ├── MessageList.vue
    │   │   └── MessageDetail.vue
    │   ├── MetricsView.vue
    │   │   ├── GlobalStats.vue
    │   │   └── MetricGrid.vue
    │   │       └── MetricCard.vue (× N)
    │   └── DebugView.vue
    │       ├── BreakpointPanel.vue
    │       └── StepHistory.vue
    └── InspectorPanel.vue       (slide-out, triggered from any view)
```

### Layout Structure

```
┌──────────────────────────────────────────────────────┐
│  DebugToolbar (floating, top)                        │
├────────┬─────────────────────────────────────────────┤
│        │                                             │
│  Side  │           <router-view>                     │
│  bar   │                                             │
│        │     (TopologyView / TimelineView /           │
│  nav   │      MessagesView / MetricsView /           │
│  +     │      DebugView)                             │
│  status│                                             │
│        │                                             │
│        ├─────────────────────────────────────────────┤
│        │  InspectorPanel (slide-out from right)      │
└────────┴─────────────────────────────────────────────┘
```

---

## Composables

### useWebSocket

```typescript
// src/composables/useWebSocket.ts
import { ref, onMounted, onUnmounted } from 'vue'
import { useConnectionStore } from '@/stores/connection'

export function useWebSocket() {
  const store = useConnectionStore()

  function sendCommand(type: string, payload: object = {}) {
    store.send({
      type,
      id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      payload,
    })
  }

  return {
    connected: store.connected,
    reconnecting: store.reconnecting,
    error: store.error,
    sendCommand,
  }
}
```

### useDebug

```typescript
// src/composables/useDebug.ts
import { useDebugStore } from '@/stores/debug'
import { useWebSocket } from './useWebSocket'

export function useDebug() {
  const store = useDebugStore()
  const { sendCommand } = useWebSocket()

  function pause() {
    sendCommand('debug.pause')
  }

  function resume() {
    sendCommand('debug.resume')
  }

  function step() {
    sendCommand('debug.step', { granularity: store.granularity })
  }

  function setGranularity(granularity: 'message' | 'stage' | 'breakpoint') {
    sendCommand('debug.set_granularity', { granularity })
    store.granularity = granularity
  }

  function toggleSlowMotion(enabled: boolean, delayMs: number = 500) {
    sendCommand('debug.slow_motion', { enabled, delay_ms: delayMs })
  }

  function addBreakpoint(channelPattern: string, condition?: string) {
    sendCommand('debug.add_breakpoint', {
      channel_pattern: channelPattern,
      condition: condition ?? null,
      component_id: null,
    })
  }

  function removeBreakpoint(breakpointId: string) {
    sendCommand('debug.remove_breakpoint', { breakpoint_id: breakpointId })
  }

  return {
    state: store.state,
    granularity: store.granularity,
    breakpoints: store.breakpoints,
    stepCount: store.stepCount,
    pause,
    resume,
    step,
    setGranularity,
    toggleSlowMotion,
    addBreakpoint,
    removeBreakpoint,
  }
}
```

### useTopology

```typescript
// src/composables/useTopology.ts
import { computed } from 'vue'
import { useTopologyStore } from '@/stores/topology'
import type { Node, Edge } from '@vue-flow/core'

export function useTopology() {
  const store = useTopologyStore()

  const flowNodes = computed<Node[]>(() =>
    store.nodes.map((node) => ({
      id: node.id,
      type: node.type,  // 'source', 'transformation', 'destination'
      position: node.position ?? { x: 0, y: 0 },
      data: {
        label: node.label,
        state: node.state,
        metadata: node.metadata,
      },
    }))
  )

  const flowEdges = computed<Edge[]>(() =>
    store.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.channel,
      animated: edge.messageRate > 0,
      data: {
        channel: edge.channel,
        messageRate: edge.messageRate,
      },
    }))
  )

  return { flowNodes, flowEdges }
}
```

---

## TypeScript Types

### Protocol Types

```typescript
// src/types/protocol.ts

/** Standard WebSocket message envelope */
export interface WsMessage {
  type: string
  id: string
  timestamp: string
  payload: Record<string, unknown>
}

/** Server event types */
export type EventType =
  | 'connected'
  | 'topology.update'
  | 'message.published'
  | 'message.detail'
  | 'metric.update'
  | 'component.state'
  | 'debug.paused'
  | 'debug.resumed'
  | 'debug.breakpoint_hit'
  | 'debug.step_completed'
  | 'error.occurred'

/** Client command types */
export type CommandType =
  | 'subscribe'
  | 'debug.pause'
  | 'debug.resume'
  | 'debug.step'
  | 'debug.set_granularity'
  | 'debug.slow_motion'
  | 'debug.add_breakpoint'
  | 'debug.remove_breakpoint'
  | 'channel.history'
  | 'message.inspect'
  | 'channel.watch'
```

### Topology Types

```typescript
// src/types/topology.ts

export interface TopologyNode {
  id: string
  type: 'source' | 'transformation' | 'destination'
  label: string
  state: 'idle' | 'running' | 'paused' | 'error' | 'stopped'
  metadata: Record<string, string>
  position?: { x: number; y: number }
}

export interface TopologyEdge {
  id: string
  source: string
  target: string
  channel: string
  messageRate: number
}
```

### Debug Types

```typescript
// src/types/debug.ts

export type DebugState = 'inactive' | 'running' | 'paused' | 'stepping'
export type Granularity = 'message' | 'stage' | 'breakpoint'

export interface Breakpoint {
  id: string
  channelPattern: string
  condition: string | null
  componentId: string | null
  enabled: boolean
  hitCount: number
}
```

---

## Build Configuration

### Vite Config

```typescript
// vite.config.ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [
    vue(),
    vuetify({ autoImport: true }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
    // Optimize chunk size for embedding
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['vue', 'vue-router', 'pinia', 'vuetify'],
          charts: ['chart.js', 'vue-chartjs'],
          flow: ['@vue-flow/core'],
        },
      },
    },
  },
  server: {
    // Dev proxy to backend
    proxy: {
      '/api': 'http://127.0.0.1:8765',
      '/ws': {
        target: 'ws://127.0.0.1:8765',
        ws: true,
      },
    },
  },
})
```

### Build Output

```bash
# Development
npm run dev     # Vite dev server with HMR + proxy

# Production build
npm run build   # Output to dist/

# Copy to Python package
cp -r dist/* ../cod3s_data/observatory/static/
```

Expected build size: ~300-500 KB gzipped (vendor + app code).

---

## Summary

The frontend architecture is organized around:

1. **5 views** — One per main feature (topology, timeline, messages, metrics, debug)
2. **5 Pinia stores** — Connection, topology, messages, metrics, debug
3. **5 composables** — WebSocket, topology, debug, messages, metrics
4. **Custom components** — PipelineGraph, TimelineChart, MessageDetail, MetricCard, DebugToolbar
5. **TypeScript-first** — All types mirror the WebSocket protocol
6. **Vite build** — Output bundled into Python package as static files

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← OBS-TECH-03](OBS-TECH-03-WEBSOCKET-PROTOCOL.md) | [OBS-TECH-00-OVERVIEW](OBS-TECH-00-OVERVIEW.md) | [OBS-TECH-05 →](OBS-TECH-05-COMPONENT-LIBRARY.md) |
