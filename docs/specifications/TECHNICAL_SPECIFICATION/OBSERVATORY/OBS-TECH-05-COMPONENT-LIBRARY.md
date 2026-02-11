# Observatory Component Library - Technical Specification

**Document:** OBS-TECH-05-COMPONENT-LIBRARY.md
**Version:** 1.0.0
**Date:** 2026-02-11
**Status:** Draft
**Implements:** [OBS-04](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-04-PIPELINE-TOPOLOGY.md) through [OBS-07](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-07-METRICS-DASHBOARD.md)

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← OBS-TECH-04](OBS-TECH-04-FRONTEND-ARCHITECTURE.md) | [OBS-TECH-00-OVERVIEW](OBS-TECH-00-OVERVIEW.md) | [OBS-TECH-06 →](OBS-TECH-06-STATE-MANAGEMENT.md) |

---

## Table of Contents

1. [PipelineGraph](#pipelinegraph)
2. [TimelineChart](#timelinechart)
3. [MessageDetail](#messagedetail)
4. [MetricCard](#metriccard)
5. [DebugControls](#debugcontrols)

---

## PipelineGraph

**Implements:** [OBS-04-PIPELINE-TOPOLOGY](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-04-PIPELINE-TOPOLOGY.md)

**Library:** `@vue-flow/core` with dagre layout

### Component API

```vue
<template>
  <VueFlow
    :nodes="flowNodes"
    :edges="flowEdges"
    :default-viewport="{ zoom: 1 }"
    fit-view-on-init
    @node-click="onNodeClick"
    @edge-click="onEdgeClick"
  >
    <template #node-source="props">
      <SourceNode v-bind="props" />
    </template>
    <template #node-transformation="props">
      <TransformNode v-bind="props" />
    </template>
    <template #node-destination="props">
      <DestinationNode v-bind="props" />
    </template>

    <Background />
    <MiniMap />
    <Controls />
  </VueFlow>
</template>
```

### Custom Node Components

**SourceNode** — Rounded rectangle, icon for source type

```vue
<!-- components/topology/SourceNode.vue -->
<template>
  <div class="source-node" :class="stateClass">
    <v-icon>mdi-database-import</v-icon>
    <span class="node-label">{{ data.label }}</span>
    <span class="node-state">{{ data.state }}</span>
    <div v-if="hasBreakpoint" class="breakpoint-indicator" />
  </div>
</template>
```

**TransformNode** — Hexagonal shape

```vue
<!-- components/topology/TransformNode.vue -->
<template>
  <div class="transform-node" :class="stateClass">
    <v-icon>mdi-cog</v-icon>
    <span class="node-label">{{ data.label }}</span>
    <span class="node-state">{{ data.state }}</span>
  </div>
</template>
```

**DestinationNode** — Double-bordered rectangle

```vue
<!-- components/topology/DestinationNode.vue -->
<template>
  <div class="destination-node" :class="stateClass">
    <v-icon>mdi-database-export</v-icon>
    <span class="node-label">{{ data.label }}</span>
    <span class="node-state">{{ data.state }}</span>
  </div>
</template>
```

### State-Based Styling

```css
.source-node, .transform-node, .destination-node {
  /* Base styles */
  padding: 12px 16px;
  border: 2px solid #ccc;
  border-radius: 8px;
  background: white;
  min-width: 120px;
  text-align: center;
}

/* State colors */
.state-running  { border-color: #4CAF50; background: #E8F5E9; }
.state-paused   { border-color: #FF9800; background: #FFF3E0; }
.state-error    { border-color: #F44336; background: #FFEBEE; }
.state-stopped  { border-color: #9E9E9E; background: #F5F5F5; }
.state-idle     { border-color: #2196F3; background: #E3F2FD; }

/* Node type shapes */
.transform-node { clip-path: polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%); }
.destination-node { border-style: double; border-width: 4px; }

/* Breakpoint indicator */
.breakpoint-indicator {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #F44336;
}
```

### Edge Animation

Edges animate when messages flow:

```typescript
const flowEdges = computed<Edge[]>(() =>
  store.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: `${edge.channel} (${edge.messageRate}/s)`,
    animated: edge.messageRate > 0,
    style: {
      strokeWidth: Math.min(4, 1 + Math.log10(edge.messageRate + 1)),
    },
  }))
)
```

### Layout

Automatic layout using dagre:

```typescript
import dagre from 'dagre'

function layoutGraph(nodes: TopologyNode[], edges: TopologyEdge[]) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 80, ranksep: 120 })

  nodes.forEach((n) => g.setNode(n.id, { width: 150, height: 60 }))
  edges.forEach((e) => g.setEdge(e.source, e.target))

  dagre.layout(g)

  return nodes.map((n) => ({
    ...n,
    position: { x: g.node(n.id).x, y: g.node(n.id).y },
  }))
}
```

---

## TimelineChart

**Implements:** [OBS-05-TEMPORAL-TIMELINE](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-05-TEMPORAL-TIMELINE.md)

**Rendering:** HTML5 Canvas (virtualized for performance)

### Component API

```vue
<!-- components/timeline/TimelineChart.vue -->
<template>
  <div class="timeline-container" ref="container">
    <canvas ref="canvas" @click="onClick" @wheel="onWheel" />
    <div class="timeline-controls">
      <v-btn-toggle v-model="zoomLevel">
        <v-btn value="1s">1s</v-btn>
        <v-btn value="10s">10s</v-btn>
        <v-btn value="1m">1m</v-btn>
        <v-btn value="5m">5m</v-btn>
      </v-btn-toggle>
      <v-btn :color="liveTail ? 'primary' : ''" @click="toggleLiveTail">
        <v-icon>mdi-play</v-icon> Live
      </v-btn>
    </div>
  </div>
</template>
```

### Canvas Rendering Architecture

```typescript
// Render pipeline
class TimelineRenderer {
  private ctx: CanvasRenderingContext2D
  private lanes: Lane[]
  private visibleTimeRange: [number, number]

  render() {
    this.ctx.clearRect(0, 0, this.width, this.height)

    // 1. Draw time axis (horizontal)
    this.drawTimeAxis()

    // 2. Draw lane backgrounds + labels (vertical)
    this.drawLanes()

    // 3. Draw message markers (only visible ones)
    this.drawMessages()

    // 4. Draw processing spans
    this.drawSpans()

    // 5. Draw trace lines (connecting related messages)
    this.drawTraceLines()

    // 6. Draw debug overlay (breakpoint hits, step position)
    if (this.debugActive) {
      this.drawDebugOverlay()
    }
  }

  private drawMessages() {
    // Virtual rendering: only draw messages within visible time range
    const visible = this.getVisibleMessages()
    for (const msg of visible) {
      const x = this.timeToX(msg.timestamp)
      const y = this.laneToY(msg.componentId)
      this.drawMessageMarker(x, y, msg)
    }
  }

  private getVisibleMessages(): TimelineMessage[] {
    // Binary search for messages within visible time range
    const [start, end] = this.visibleTimeRange
    return binaryRangeSearch(this.messages, start, end)
  }
}
```

### Zoom Levels

| Level | Time Range | Message Display |
|-------|-----------|----------------|
| 1s | 1 second | Individual dots, full detail |
| 10s | 10 seconds | Individual dots |
| 1m | 1 minute | Density heatmap (aggregated) |
| 5m | 5 minutes | Density heatmap (highly aggregated) |

### Performance

- **Virtualized rendering:** Only draws messages within the visible time window
- **Binary search:** O(log n) message lookup by timestamp
- **requestAnimationFrame:** Smooth 60fps rendering
- **Buffer limit:** 60 seconds of detailed history, older messages aggregated
- **Target:** 10,000+ messages rendered smoothly

---

## MessageDetail

**Implements:** [OBS-06-MESSAGE-INSPECTOR](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-06-MESSAGE-INSPECTOR.md)

### Component API

```vue
<!-- components/messages/MessageDetail.vue -->
<template>
  <v-card v-if="message" class="message-detail">
    <v-tabs v-model="activeTab">
      <v-tab value="summary">Summary</v-tab>
      <v-tab value="value">Value</v-tab>
      <v-tab value="tags">Tags</v-tab>
      <v-tab value="journey">Journey</v-tab>
      <v-tab value="raw">JSON</v-tab>
    </v-tabs>

    <v-window v-model="activeTab">
      <!-- Summary tab -->
      <v-window-item value="summary">
        <v-list density="compact">
          <v-list-item title="Key" :subtitle="message.key" />
          <v-list-item title="Channel" :subtitle="message.channel" />
          <v-list-item title="Timestamp" :subtitle="formatTimestamp(message.timestamp)" />
          <v-list-item title="Trace ID" :subtitle="message.traceId" />
          <v-list-item title="Subscribers" :subtitle="String(message.subscriberCount)" />
        </v-list>
      </v-window-item>

      <!-- Value tab (tree view) -->
      <v-window-item value="value">
        <TreeView :data="message.value" />
      </v-window-item>

      <!-- Tags tab -->
      <v-window-item value="tags">
        <v-table density="compact">
          <thead><tr><th>Key</th><th>Value</th></tr></thead>
          <tbody>
            <tr v-for="(val, key) in message.tags" :key="key">
              <td>{{ key }}</td>
              <td>{{ val }}</td>
            </tr>
          </tbody>
        </v-table>
      </v-window-item>

      <!-- Journey tab -->
      <v-window-item value="journey">
        <v-timeline density="compact" side="end">
          <v-timeline-item
            v-for="step in message.journey"
            :key="step.timestamp"
            :dot-color="journeyColor(step.action)"
            size="small"
          >
            <div class="journey-step">
              <strong>{{ step.component }}</strong>
              <span>{{ step.action }}</span>
              <span class="text-caption">{{ formatTime(step.timestamp) }}</span>
            </div>
          </v-timeline-item>
        </v-timeline>
      </v-window-item>

      <!-- Raw JSON tab -->
      <v-window-item value="raw">
        <pre class="json-raw"><code>{{ formatJson(message) }}</code></pre>
      </v-window-item>
    </v-window>
  </v-card>
</template>
```

### Comparison Mode (MessageDiff)

```vue
<!-- components/messages/MessageDiff.vue -->
<template>
  <div class="message-diff">
    <div class="diff-header">
      <span>Input ({{ left.channel }})</span>
      <span>Output ({{ right.channel }})</span>
    </div>
    <div class="diff-content">
      <div class="diff-left">
        <TreeView :data="left.value" :highlights="leftDiffs" />
      </div>
      <div class="diff-right">
        <TreeView :data="right.value" :highlights="rightDiffs" />
      </div>
    </div>
  </div>
</template>
```

Highlights differences between input and output of a transformation.

---

## MetricCard

**Implements:** [OBS-07-METRICS-DASHBOARD](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-07-METRICS-DASHBOARD.md)

### Component API

```vue
<!-- components/metrics/MetricCard.vue -->
<template>
  <v-card class="metric-card" :class="alertClass">
    <v-card-title class="text-subtitle-2">{{ title }}</v-card-title>
    <v-card-text>
      <!-- Number display -->
      <div v-if="chartType === 'number'" class="metric-number">
        <span class="text-h4">{{ formattedValue }}</span>
        <span class="text-caption">{{ unit }}</span>
      </div>

      <!-- Line/Bar chart -->
      <component
        v-else-if="chartType === 'line' || chartType === 'bar'"
        :is="chartType === 'line' ? Line : Bar"
        :data="chartData"
        :options="chartOptions"
        :height="120"
      />

      <!-- Gauge -->
      <div v-else-if="chartType === 'gauge'" class="metric-gauge">
        <v-progress-circular
          :model-value="gaugePercent"
          :color="gaugeColor"
          :size="80"
          :width="8"
        >
          {{ formattedValue }}
        </v-progress-circular>
      </div>

      <!-- Sparkline -->
      <div v-else-if="chartType === 'sparkline'" class="metric-sparkline">
        <span class="text-h5">{{ formattedValue }}</span>
        <Line :data="sparklineData" :options="sparklineOptions" :height="40" />
      </div>
    </v-card-text>
  </v-card>
</template>
```

### Built-In Metric Cards

```typescript
// Default dashboard configuration
export const defaultMetricCards: MetricCardConfig[] = [
  {
    title: 'Throughput',
    metric: 'broker.throughput',
    chartType: 'line',
    unit: 'msg/s',
    color: '#4CAF50',
  },
  {
    title: 'Latency (p99)',
    metric: 'broker.latency',
    chartType: 'line',
    unit: 'ms',
    valueExtractor: (v: any) => v.p99,
    thresholds: { warning: 50, critical: 100 },
    color: '#2196F3',
  },
  {
    title: 'Active Channels',
    metric: 'broker.channels',
    chartType: 'number',
    unit: '',
    color: '#9C27B0',
  },
  {
    title: 'Subscriptions',
    metric: 'broker.subscriptions',
    chartType: 'number',
    unit: '',
    color: '#FF9800',
  },
  {
    title: 'Error Rate',
    metric: 'system.errors',
    chartType: 'sparkline',
    unit: '/min',
    thresholds: { warning: 1, critical: 10 },
    color: '#F44336',
  },
  {
    title: 'Memory Usage',
    metric: 'system.memory',
    chartType: 'gauge',
    unit: 'MB',
    maxValue: 512,
    thresholds: { warning: 400, critical: 480 },
    color: '#607D8B',
  },
]
```

### Chart.js Configuration

```typescript
const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 0 },  // Disable animation for real-time updates
  scales: {
    x: {
      type: 'time',
      time: { unit: 'second' },
      display: false,
    },
    y: {
      beginAtZero: true,
    },
  },
  plugins: {
    legend: { display: false },
  },
}
```

---

## DebugControls

**Implements:** [OBS-03-DEBUG-CONTROLS](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-03-DEBUG-CONTROLS.md)

### DebugToolbar

```vue
<!-- components/debug/DebugToolbar.vue -->
<template>
  <v-toolbar
    v-if="debug.state !== 'inactive'"
    class="debug-toolbar"
    density="compact"
    floating
  >
    <!-- Pause / Resume -->
    <v-btn
      :icon="debug.state === 'paused' ? 'mdi-play' : 'mdi-pause'"
      :color="debug.state === 'paused' ? 'success' : 'warning'"
      @click="debug.state === 'paused' ? resume() : pause()"
    />

    <!-- Step -->
    <v-btn
      icon="mdi-skip-next"
      :disabled="debug.state !== 'paused'"
      @click="step()"
    />

    <!-- Granularity selector -->
    <v-btn-toggle v-model="granularity" mandatory density="compact">
      <v-btn value="message" size="small">MSG</v-btn>
      <v-btn value="stage" size="small">STAGE</v-btn>
      <v-btn value="breakpoint" size="small">BP</v-btn>
    </v-btn-toggle>

    <!-- Slow-motion toggle + slider -->
    <v-btn
      :icon="slowMotion ? 'mdi-turtle' : 'mdi-rabbit'"
      :color="slowMotion ? 'info' : ''"
      @click="toggleSlowMotion(!slowMotion, slowMotionDelay)"
    />
    <v-slider
      v-if="slowMotion"
      v-model="slowMotionDelay"
      :min="100"
      :max="5000"
      :step="100"
      style="width: 120px"
      hide-details
      @end="toggleSlowMotion(true, slowMotionDelay)"
    />

    <!-- State indicator -->
    <v-chip
      :color="stateColor"
      size="small"
      class="ml-2"
    >
      {{ debug.state.toUpperCase() }}
    </v-chip>

    <!-- Step counter -->
    <span class="text-caption ml-2">#{{ debug.stepCount }}</span>

    <!-- Breakpoint count -->
    <v-btn
      :text="`BP: ${debug.breakpoints.length}`"
      size="small"
      @click="showBreakpoints = !showBreakpoints"
    />
  </v-toolbar>
</template>
```

### Keyboard Shortcuts

```typescript
// Registered in App.vue
function setupKeyboardShortcuts() {
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    // Ignore when typing in inputs
    if ((e.target as HTMLElement).tagName === 'INPUT') return

    switch (e.code) {
      case 'Space':
        e.preventDefault()
        debug.state === 'paused' ? resume() : pause()
        break
      case 'KeyN':
        if (debug.state === 'paused') step()
        break
      case 'Digit1':
        setGranularity('message')
        break
      case 'Digit2':
        setGranularity('stage')
        break
      case 'Digit3':
        setGranularity('breakpoint')
        break
      case 'KeyS':
        toggleSlowMotion(!slowMotion.value)
        break
      case 'KeyB':
        showBreakpoints.value = !showBreakpoints.value
        break
    }
  })
}
```

---

## Summary

The component library provides 5 major components:

1. **PipelineGraph** — @vue-flow/core with custom nodes, dagre layout, state-based colors
2. **TimelineChart** — Canvas-based, virtualized rendering, zoom levels, live tail
3. **MessageDetail** — 5-tab inspector (summary, value tree, tags, journey, JSON)
4. **MetricCard** — Chart.js with 4 display modes (line, bar, gauge, sparkline)
5. **DebugControls** — Floating toolbar with keyboard shortcuts

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← OBS-TECH-04](OBS-TECH-04-FRONTEND-ARCHITECTURE.md) | [OBS-TECH-00-OVERVIEW](OBS-TECH-00-OVERVIEW.md) | [OBS-TECH-06 →](OBS-TECH-06-STATE-MANAGEMENT.md) |
