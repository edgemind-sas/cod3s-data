<template>
  <div class="json-tree-node">
    <!-- Line: toggle + icon + value -->
    <div class="d-flex align-center tree-line">
      <v-icon
        v-if="isExpandable"
        size="16"
        class="mr-1 cursor-pointer"
        @click="expanded = !expanded"
      >
        {{ expanded ? 'mdi-chevron-down' : 'mdi-chevron-right' }}
      </v-icon>
      <span v-else style="width: 24px; display: inline-block"></span>

      <v-icon size="14" :color="iconColor" class="mr-1">{{ icon }}</v-icon>

      <span
        v-if="isExpandable"
        class="text-medium-emphasis cursor-pointer"
        @click="expanded = !expanded"
      >
        {{ expandableLabel }}
      </span>
      <span
        v-else
        :class="`value-${dataType}`"
        @contextmenu.prevent="copyValue"
      >
        {{ displayValue }}
      </span>
    </div>

    <!-- Children -->
    <div v-if="isExpandable && expanded" class="tree-children">
      <div v-for="[key, val] in visibleEntries" :key="key" class="tree-child">
        <span class="tree-key mr-1">{{ key }}:</span>
        <TreeNode :data="val" :path="`${path}.${key}`" :depth="depth + 1" />
      </div>
      <v-btn
        v-if="hasMore"
        size="x-small"
        variant="text"
        color="primary"
        class="ml-6"
        @click="showMore += 100"
      >
        Load more ({{ totalLength - showMore }} remaining)
      </v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  data: unknown
  path: string
  depth: number
}>()

const expanded = ref(props.depth < 2)
const showMore = ref(100)

const dataType = computed((): string => {
  if (props.data === null || props.data === undefined) return 'null'
  if (Array.isArray(props.data)) return 'array'
  return typeof props.data
})

const icon = computed((): string => {
  switch (dataType.value) {
    case 'object': return 'mdi-code-braces'
    case 'array': return 'mdi-code-brackets'
    case 'string': return 'mdi-format-text'
    case 'number': return 'mdi-numeric'
    case 'boolean': return 'mdi-checkbox-marked'
    default: return 'mdi-null'
  }
})

const iconColor = computed((): string | undefined => {
  switch (dataType.value) {
    case 'string': return 'green'
    case 'number': return 'blue'
    case 'boolean': return 'orange'
    case 'null': return 'grey'
    default: return undefined
  }
})

const isExpandable = computed((): boolean => dataType.value === 'object' || dataType.value === 'array')

const totalLength = computed((): number => {
  if (dataType.value === 'array') return (props.data as unknown[]).length
  if (dataType.value === 'object') return Object.keys(props.data as Record<string, unknown>).length
  return 0
})

const childCount = computed(() => totalLength.value)

const expandableLabel = computed((): string => {
  if (dataType.value === 'array') return '[' + childCount.value + ']'
  return '{' + childCount.value + '}'
})

const visibleEntries = computed((): [string, unknown][] => {
  if (dataType.value === 'array') {
    return (props.data as unknown[]).slice(0, showMore.value).map((v, i) => [String(i), v])
  }
  if (dataType.value === 'object') {
    return Object.entries(props.data as Record<string, unknown>)
  }
  return []
})

const hasMore = computed((): boolean => {
  if (dataType.value === 'array') return (props.data as unknown[]).length > showMore.value
  return false
})

const displayValue = computed((): string => {
  if (props.data === null || props.data === undefined) return 'null'
  if (typeof props.data === 'string') {
    const s = props.data
    if (s.length > 500) return `"${s.slice(0, 500)}..."`
    return `"${s}"`
  }
  if (typeof props.data === 'boolean' || typeof props.data === 'number') return String(props.data)
  return ''
})

function copyValue() {
  navigator.clipboard.writeText(JSON.stringify(props.data, null, 2))
}
</script>

<style scoped>
.tree-line {
  min-height: 24px;
}
.tree-child {
  padding-left: 20px;
  display: flex;
  align-items: flex-start;
}
.tree-key {
  color: #9c27b0;
  white-space: nowrap;
}
.value-string { color: #2e7d32; }
.value-number { color: #1565c0; }
.value-boolean { color: #ef6c00; }
.value-null { color: #757575; font-style: italic; }
.cursor-pointer { cursor: pointer; }
</style>
