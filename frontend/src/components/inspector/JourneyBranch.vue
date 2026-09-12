<template>
  <div class="journey-node">
    <div
      :class="[
        'step-card',
        `step-card--${props.node.step.stage.toLowerCase()}`,
        { 'step-card--focus': isFocus },
      ]"
    >
      <v-icon :color="stageColor" size="13" class="mr-1">{{ stageIcon }}</v-icon>
      <span class="stage-name" :style="{ color: `rgb(var(--v-theme-${stageColor}))` }">
        {{ props.node.step.stage }}
      </span>
      <span class="who" :title="props.node.step.component_id">
        {{ props.node.step.label || props.node.step.component_id }}
      </span>
      <span v-if="props.node.step.channel" class="chan">{{ props.node.step.channel }}</span>
      <span class="delta">+{{ delta(rootTimestamp, props.node.step.timestamp) }}</span>
    </div>

    <div v-if="props.node.children.length" class="children">
      <div v-if="props.node.children.length > 1" class="branch-count">
        <v-icon size="12" class="mr-1">mdi-call-split</v-icon>
        {{ props.node.children.length }} branches
      </div>
      <JourneyBranch
        v-for="(child, i) in props.node.children"
        :key="i"
        :node="child"
        :root-timestamp="rootTimestamp"
        :highlight-message-id="highlightMessageId"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * One step of a journey, and its children beneath it.
 *
 * Children are stacked and indented rather than laid out in side-by-side lanes.
 * A trace of any depth fans out several times — an `unpack` into six sensors,
 * each smoothed, throttled, alarmed and written — and columns divided by six,
 * then by three again, left 26 of 32 lanes under 120px wide inside a panel a
 * few hundred pixels tall. An indented outline reads at any width, and stays
 * readable as the tree deepens.
 *
 * The card itself is one line: the stage, who handled it, on which channel, and
 * how long after the start of the trace. Four stacked lines per step made 59
 * steps into 1700px of scrolling.
 */
import { computed } from 'vue'
import type { JourneyTreeNode } from '@/types'

const props = defineProps<{
  node: JourneyTreeNode
  rootTimestamp: string
  /** The message being inspected: its own steps are marked in the lineage. */
  highlightMessageId?: string
}>()

const isFocus = computed(
  () => !!props.highlightMessageId && props.node.step.message_id === props.highlightMessageId
)

const stageColor = computed(() => {
  switch (props.node.step.stage) {
    case 'PUBLISHED': return 'info'
    case 'RECEIVED': return 'warning'
    case 'PROCESSED': return 'secondary'
    case 'DELIVERED': return 'success'
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

function delta(from: string, to: string): string {
  try {
    const ms = new Date(to).getTime() - new Date(from).getTime()
    if (ms < 1) return '0ms'
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
}

.step-card {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 3px 8px;
  border-left: 2px solid;
  background: rgba(var(--v-theme-on-surface), 0.03);
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
  overflow: hidden;
}
.step-card--published { border-left-color: rgb(var(--v-theme-info)); }
.step-card--received { border-left-color: rgb(var(--v-theme-warning)); }
.step-card--processed { border-left-color: rgb(var(--v-theme-secondary)); }
.step-card--delivered { border-left-color: rgb(var(--v-theme-success)); }

/* The steps that are about the inspected message itself. */
.step-card--focus {
  background: rgba(var(--v-theme-primary), 0.14);
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-primary), 0.35);
}

.stage-name {
  font-weight: 600;
  font-size: 10px;
  letter-spacing: 0.04em;
  min-width: 68px;
}

.who {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chan {
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-family: monospace;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.delta {
  margin-left: auto;
  color: rgba(var(--v-theme-on-surface), 0.4);
  font-size: 11px;
  padding-left: 8px;
}

/* Children hang under their parent, indented, with a spine joining them. */
.children {
  margin-left: 10px;
  padding-left: 10px;
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-top: 2px;
}

.branch-count {
  display: flex;
  align-items: center;
  font-size: 10px;
  color: rgba(var(--v-theme-on-surface), 0.4);
  padding: 1px 0;
}
</style>
