<template>
  <div class="pa-2">
    <div v-if="!journey.length" class="text-center text-medium-emphasis pa-4">
      No journey data available.
    </div>

    <template v-else>
      <!-- One trace covers a whole fan-out: an EGM reading becomes six sensor
           messages, each smoothed, throttled, alarmed and written. Showing all
           of it to explain one message buries it under five branches it never
           touched. The lineage of the inspected message is the default; the
           whole trace stays one click away. -->
      <div class="d-flex align-center mb-1 px-1">
        <v-btn-toggle v-model="scope" mandatory density="compact" variant="outlined" divided>
          <v-btn value="lineage" size="x-small">This message</v-btn>
          <v-btn value="trace" size="x-small">Whole trace</v-btn>
        </v-btn-toggle>
        <span class="text-caption text-medium-emphasis ml-3">
          {{ renderedCount }} of {{ journey.length }} steps
          <span v-if="leafCount > 1">&middot; {{ leafCount }} branches</span>
          <!-- Span, not latency: the steps of every branch are interleaved in
               one list, so first-to-last measures the trace, not a path. -->
          &middot; span {{ delta(firstTimestamp, lastTimestamp) }}
        </span>
      </div>

      <JourneyBranch
        v-for="(root, i) in tree"
        :key="i"
        :node="root"
        :root-timestamp="firstTimestamp"
        :highlight-message-id="detail.message_id"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { MessageDetail, JourneyTreeNode } from '@/types'
import JourneyBranch from './JourneyBranch.vue'

const props = defineProps<{ detail: MessageDetail }>()

/** 'lineage' shows only what the inspected message went through. */
const scope = ref<'lineage' | 'trace'>('lineage')

interface Built {
  roots: JourneyTreeNode[]
  nodes: JourneyTreeNode[]
  parents: Map<JourneyTreeNode, JourneyTreeNode>
}

// Selecting another row must not leave the previous scope in place.
watch(() => props.detail.message_id, () => { scope.value = 'lineage' })

const journey = computed(() => props.detail.journey || [])

const firstTimestamp = computed(() => journey.value.length ? journey.value[0].timestamp : '')
const lastTimestamp = computed(() => journey.value.length ? journey.value[journey.value.length - 1].timestamp : '')

/**
 * Build the journey tree from the flat step list.
 *
 * Every step names the message it is about (`message_id`) and, for a message a
 * transformation produced, the input it came from (`parent_message_id`). That
 * parentage *is* the tree, so it is what gets used here.
 *
 * The previous version indexed by `component_id` and `channel` alone. Both keys
 * collide as soon as one trace carries several messages through the same
 * component — an `unpack` fanning a reading into six sensors is the ordinary
 * case, not a corner one. The six receptions overwrote each other, five of the
 * six PROCESSED steps then found no parent and were pushed *nowhere*, and every
 * publication hanging off them disappeared from the panel as well.
 *
 * Attachment rules, all keyed on the message:
 * - PUBLISHED  → the PROCESSED step of the input it was produced from.
 * - RECEIVED   → the PUBLISHED step of the same message, on the channel it
 *   arrived on. DELIVERED likewise.
 * - PROCESSED  → the RECEIVED step of the same message at the same component.
 *
 * Two passes, because the order of the flat list is not guaranteed: the broker
 * schedules its subscribers before awaiting the publication hook, so a RECEIVED
 * step can land ahead of the PUBLISHED it belongs under. The first pass indexes,
 * the second attaches — and anything left unattached becomes a root rather than
 * being dropped.
 */
const fullTree = computed((): Built => {
  const steps = journey.value
  const nodes: JourneyTreeNode[] = steps.map(step => ({ step, children: [] }))
  if (!steps.length) return { roots: [], nodes, parents: new Map() }

  const publishedByMessageChannel = new Map<string, JourneyTreeNode>()
  const publishedByMessage = new Map<string, JourneyTreeNode>()
  const receivedByMessageComponent = new Map<string, JourneyTreeNode>()
  const processedByMessage = new Map<string, JourneyTreeNode>()
  const processedByMessageComponent = new Map<string, JourneyTreeNode>()
  const indexOf = new Map<JourneyTreeNode, number>()

  const pair = (a: string, b: string) => `${a}|${b}`

  nodes.forEach((node, i) => {
    const { stage, message_id, component_id, channel } = node.step
    indexOf.set(node, i)
    if (stage === 'PUBLISHED') {
      // First publication wins: a message republished under the same id keeps
      // its receptions attached to the channel each arrived on.
      const key = pair(message_id, channel)
      if (!publishedByMessageChannel.has(key)) publishedByMessageChannel.set(key, node)
      if (!publishedByMessage.has(message_id)) publishedByMessage.set(message_id, node)
    } else if (stage === 'RECEIVED') {
      receivedByMessageComponent.set(pair(message_id, component_id), node)
    } else if (stage === 'PROCESSED') {
      processedByMessageComponent.set(pair(message_id, component_id), node)
      if (!processedByMessage.has(message_id)) processedByMessage.set(message_id, node)
    }
  })

  function parentOf(node: JourneyTreeNode): JourneyTreeNode | undefined {
    const { stage, message_id, parent_message_id, component_id, channel } = node.step

    if (stage === 'PUBLISHED') {
      if (parent_message_id) {
        return (
          processedByMessageComponent.get(pair(parent_message_id, component_id)) ??
          processedByMessage.get(parent_message_id)
        )
      }
      // A transformation that forwards its input unchanged republishes the same
      // id, so there is no parentage to follow: the output publication is the
      // one this component processed onto this very channel.
      const passthrough = processedByMessageComponent.get(pair(message_id, component_id))
      if (passthrough && passthrough.step.channel === channel) {
        const here = indexOf.get(node) ?? 0
        if ((indexOf.get(passthrough) ?? 0) < here) return passthrough
      }
      return undefined
    }

    if (stage === 'RECEIVED' || stage === 'DELIVERED') {
      return (
        (channel ? publishedByMessageChannel.get(pair(message_id, channel)) : undefined) ??
        publishedByMessage.get(message_id)
      )
    }

    if (stage === 'PROCESSED') {
      return receivedByMessageComponent.get(pair(message_id, component_id))
    }

    return undefined
  }

  const parents = new Map<JourneyTreeNode, JourneyTreeNode>()

  // A malformed trace must not produce a cycle: JourneyBranch recurses on its
  // children, and a loop would hang the tab rather than draw a wrong picture.
  function createsCycle(node: JourneyTreeNode, candidate: JourneyTreeNode): boolean {
    let cursor: JourneyTreeNode | undefined = candidate
    while (cursor) {
      if (cursor === node) return true
      cursor = parents.get(cursor)
    }
    return false
  }

  const roots: JourneyTreeNode[] = []
  for (const node of nodes) {
    const parent = parentOf(node)
    if (parent && parent !== node && !createsCycle(node, parent)) {
      parents.set(node, parent)
      parent.children.push(node)
    } else {
      roots.push(node)
    }
  }

  return { roots, nodes, parents }
})

/**
 * The tree reduced to what the inspected message went through.
 *
 * Kept: the steps about the message itself, everything upstream that led to it,
 * and everything downstream that came out of it. Dropped: the branches that
 * split off before it — an unpack's five other sensors, each with its own
 * smoothing, alarm and write, which say nothing about this message.
 *
 * Nodes are copied rather than trimmed in place, so the whole-trace view is
 * still there when the toggle asks for it.
 */
const lineage = computed((): JourneyTreeNode[] => {
  const { roots, nodes, parents } = fullTree.value
  const target = props.detail.message_id
  const keep = new Set<JourneyTreeNode>()

  const keepSubtree = (node: JourneyTreeNode) => {
    keep.add(node)
    node.children.forEach(keepSubtree)
  }

  let found = false
  for (const node of nodes) {
    if (node.step.message_id !== target) continue
    found = true
    keepSubtree(node)
    for (let up = parents.get(node); up; up = parents.get(up)) keep.add(up)
  }
  // A detail whose own steps are missing from the trace is better shown whole
  // than shown empty.
  if (!found) return roots

  const copy = (node: JourneyTreeNode): JourneyTreeNode => ({
    step: node.step,
    children: node.children.filter(c => keep.has(c)).map(copy),
  })
  return roots.filter(r => keep.has(r)).map(copy)
})

const tree = computed(() => (scope.value === 'trace' ? fullTree.value.roots : lineage.value))

/** Steps actually drawn, so the footer cannot claim more than the tree shows. */
const renderedCount = computed(() => countNodes(tree.value))

function countNodes(nodes: JourneyTreeNode[]): number {
  let count = 0
  for (const n of nodes) count += 1 + countNodes(n.children)
  return count
}

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
