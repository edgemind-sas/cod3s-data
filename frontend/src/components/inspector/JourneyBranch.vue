<template>
  <div class="journey-node">
    <!-- Step card -->
    <div :class="['step-card', `step-card--${props.node.step.stage.toLowerCase()}`]">
      <div class="d-flex align-center ga-1 mb-1">
        <v-icon :color="stageColor" size="16">{{ stageIcon }}</v-icon>
        <span class="font-weight-medium text-caption">{{ props.node.step.stage }}</span>
        <v-chip size="x-small" variant="tonal" :color="stageColor" class="ml-1">
          {{ props.node.step.component_type }}
        </v-chip>
      </div>
      <div class="text-body-2 font-weight-medium">
        {{ props.node.step.label || props.node.step.component_id }}
        <span v-if="props.node.step.label" class="text-caption text-medium-emphasis font-weight-regular">
          ({{ props.node.step.component_id }})
        </span>
      </div>
      <div v-if="props.node.step.channel" class="text-caption text-medium-emphasis">
        {{ props.node.step.channel }}
      </div>
      <div class="text-caption text-medium-emphasis">
        {{ formatTimestamp(props.node.step.timestamp) }}
        <span class="ml-1">(+{{ delta(rootTimestamp, props.node.step.timestamp) }})</span>
      </div>
    </div>

    <!-- 2+ children: parallel lanes -->
    <div v-if="isFanOut" class="fan-out">
      <div class="fan-out-header">
        <v-icon size="14" class="mr-1">mdi-call-split</v-icon>
        <span class="text-caption text-medium-emphasis">
          {{ props.node.children.length }} branches
        </span>
      </div>
      <div class="lanes">
        <div v-for="(child, i) in props.node.children" :key="i" class="lane">
          <div class="lane-connector" />
          <JourneyBranch :node="child" :root-timestamp="rootTimestamp" />
        </div>
      </div>
    </div>

    <!-- Single child: vertical continuation -->
    <template v-else-if="props.node.children.length === 1">
      <div class="vertical-connector" />
      <JourneyBranch :node="props.node.children[0]" :root-timestamp="rootTimestamp" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { JourneyTreeNode } from '@/types'

const props = defineProps<{
  node: JourneyTreeNode
  rootTimestamp: string
}>()

// Any node can branch, not just a publication: a transformation that emits two
// messages has two children under its PROCESSED step. Requiring PUBLISHED here
// meant those children were rendered by neither arm of the template — the whole
// subtree vanished from the panel without a trace.
const isFanOut = computed(() => props.node.children.length > 1)

const stageColor = computed(() => {
  switch (props.node.step.stage) {
    case 'PUBLISHED': return 'blue'
    case 'RECEIVED': return 'orange'
    case 'PROCESSED': return 'purple'
    case 'DELIVERED': return 'green'
    default: return 'grey'
  }
})

const stageIcon = computed(() => {
  switch (props.node.step.stage) {
    case 'PUBLISHED': return 'mdi-publish'
    case 'RECEIVED': return 'mdi-inbox-arrow-down'
    case 'PROCESSED': return 'mdi-cog'
    case 'DELIVERED': return 'mdi-check-circle'
    default: return 'mdi-circle'
  }
})

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts)
    const time = d.toLocaleTimeString()
    const ms = String(d.getMilliseconds()).padStart(3, '0')
    return `${time}.${ms}`
  } catch {
    return ts
  }
}

function delta(from: string, to: string): string {
  try {
    const ms = new Date(to).getTime() - new Date(from).getTime()
    if (ms < 1) return '<1ms'
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(2)}s`
  } catch {
    return '?'
  }
}
</script>

<style scoped>
.journey-node {
  display: flex;
  flex-direction: column;
  align-items: stretch;
}

/* --- Step card --- */
.step-card {
  padding: 8px 12px;
  border-radius: 6px;
  border-left: 3px solid;
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.step-card--published { border-left-color: rgb(var(--v-theme-info)); }
.step-card--received { border-left-color: rgb(var(--v-theme-warning)); }
.step-card--processed { border-left-color: #9c27b0; }
.step-card--delivered { border-left-color: rgb(var(--v-theme-success)); }

/* --- Vertical connector (single child) --- */
.vertical-connector {
  width: 2px;
  height: 16px;
  background: rgba(var(--v-theme-on-surface), 0.2);
  margin-left: 20px;
}

/* --- Fan-out (parallel lanes) --- */
.fan-out {
  margin-top: 4px;
}

.fan-out-header {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px 0;
}

.lanes {
  display: flex;
  gap: 6px;
  position: relative;
  padding-top: 12px;
}

/* Horizontal bar across the top of all lanes */
.lanes::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: rgba(var(--v-theme-on-surface), 0.2);
}

.lane {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  position: relative;
}

/* Vertical connector from horizontal bar down to the first step card */
.lane-connector {
  width: 2px;
  height: 12px;
  background: rgba(var(--v-theme-on-surface), 0.2);
  margin-left: 20px;
}
</style>
