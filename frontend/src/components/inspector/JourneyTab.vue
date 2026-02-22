<template>
  <div class="pa-2">
    <div v-if="!journey.length" class="text-center text-medium-emphasis pa-4">
      No journey data available.
    </div>

    <template v-else>
      <JourneyBranch
        v-for="(root, i) in tree"
        :key="i"
        :node="root"
        :root-timestamp="firstTimestamp"
      />

      <div v-if="journey.length >= 2" class="text-caption text-medium-emphasis mt-2 pa-2">
        Total latency: {{ delta(firstTimestamp, lastTimestamp) }}
        &middot; {{ journey.length }} steps
        <span v-if="leafCount > 1">
          &middot; {{ leafCount }} branches
        </span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { MessageDetail, JourneyStep, JourneyTreeNode } from '@/types'
import JourneyBranch from './JourneyBranch.vue'

const props = defineProps<{ detail: MessageDetail }>()

const journey = computed(() => props.detail.journey || [])

const firstTimestamp = computed(() => journey.value.length ? journey.value[0].timestamp : '')
const lastTimestamp = computed(() => journey.value.length ? journey.value[journey.value.length - 1].timestamp : '')

/**
 * Build the journey tree from the flat step list.
 *
 * Algorithm:
 * Uses channels to correctly associate each step with its parent:
 *
 * - PUBLISHED step → new node. If a previous PROCESSED step was by the same
 *   component_id, the PUBLISHED becomes a child of that PROCESSED.
 *   Otherwise it's a root. We register it in channelNodes[channel].
 *
 * - RECEIVED / DELIVERED step → child of the PUBLISHED node whose channel
 *   matches step.channel (the channel this component received on).
 *
 * - PROCESSED step → child of the RECEIVED node for the same component_id.
 *   Registers in processedByComponent for linking to a future PUBLISHED.
 */
const tree = computed((): JourneyTreeNode[] => {
  const steps = journey.value
  if (!steps.length) return []

  const roots: JourneyTreeNode[] = []

  // Map channel → the PUBLISHED tree node for that channel
  const channelNodes = new Map<string, JourneyTreeNode>()
  // Map component_id → the RECEIVED tree node (for attaching PROCESSED)
  const receivedByComponent = new Map<string, JourneyTreeNode>()
  // Map component_id → the PROCESSED tree node (for attaching child PUBLISHED)
  const processedByComponent = new Map<string, JourneyTreeNode>()

  for (const step of steps) {
    const node: JourneyTreeNode = { step, children: [] }

    if (step.stage === 'PUBLISHED') {
      // Was this PUBLISHED by a component that just PROCESSED?
      const parentProcessed = processedByComponent.get(step.component_id)
      if (parentProcessed) {
        parentProcessed.children.push(node)
        processedByComponent.delete(step.component_id)
      } else {
        roots.push(node)
      }
      channelNodes.set(step.channel, node)

    } else if (step.stage === 'RECEIVED' || step.stage === 'DELIVERED') {
      // Attach to the PUBLISHED node whose channel matches
      const parentPublish = step.channel ? channelNodes.get(step.channel) : null
      if (parentPublish) {
        parentPublish.children.push(node)
      } else {
        // Fallback: attach to most recent root if channel not resolved
        const lastRoot = roots[roots.length - 1]
        if (lastRoot) lastRoot.children.push(node)
      }
      if (step.stage === 'RECEIVED') {
        receivedByComponent.set(step.component_id, node)
      }

    } else if (step.stage === 'PROCESSED') {
      // Attach to the RECEIVED node for this component
      const parentReceived = receivedByComponent.get(step.component_id)
      if (parentReceived) {
        parentReceived.children.push(node)
        receivedByComponent.delete(step.component_id)
      }
      processedByComponent.set(step.component_id, node)
    }
  }

  return roots
})

const leafCount = computed(() => countLeaves(tree.value))

function countLeaves(nodes: JourneyTreeNode[]): number {
  let count = 0
  for (const n of nodes) {
    if (n.children.length === 0) count++
    else count += countLeaves(n.children)
  }
  return count
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
