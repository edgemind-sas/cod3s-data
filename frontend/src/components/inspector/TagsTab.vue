<template>
  <div class="pa-2">
    <div v-if="tagEntries.length === 0" class="text-center text-medium-emphasis pa-4">
      No tags on this message.
    </div>

    <template v-else>
      <div class="d-flex align-center mb-2 ga-2">
        <v-text-field
          v-model="filter"
          density="compact"
          variant="outlined"
          placeholder="Filter tags..."
          prepend-inner-icon="mdi-magnify"
          hide-details
          clearable
          style="max-width: 240px"
        />
        <v-spacer />
        <v-btn size="small" variant="text" @click="copyAllAsJson">
          <v-icon start size="16">mdi-content-copy</v-icon>
          Copy as JSON
        </v-btn>
      </div>

      <v-table density="compact" hover>
        <thead>
          <tr>
            <th class="cursor-pointer" @click="toggleSort('key')">
              Key
              <v-icon v-if="sortBy === 'key'" size="14">
                {{ sortAsc ? 'mdi-arrow-up' : 'mdi-arrow-down' }}
              </v-icon>
            </th>
            <th class="cursor-pointer" @click="toggleSort('value')">
              Value
              <v-icon v-if="sortBy === 'value'" size="14">
                {{ sortAsc ? 'mdi-arrow-up' : 'mdi-arrow-down' }}
              </v-icon>
            </th>
            <th>Type</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in sortedEntries" :key="entry.key">
            <td class="font-weight-medium">{{ entry.key }}</td>
            <td>{{ entry.value }}</td>
            <td class="text-caption text-medium-emphasis">{{ typeof entry.value }}</td>
          </tr>
        </tbody>
      </v-table>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { MessageDetail } from '@/types'

const props = defineProps<{ detail: MessageDetail }>()

const filter = ref('')
const sortBy = ref<'key' | 'value'>('key')
const sortAsc = ref(true)

const tagEntries = computed(() => {
  const tags = props.detail.tags || {}
  return Object.entries(tags).map(([key, value]) => ({ key, value }))
})

const filteredEntries = computed(() => {
  if (!filter.value) return tagEntries.value
  const f = filter.value.toLowerCase()
  return tagEntries.value.filter(
    e => e.key.toLowerCase().includes(f) || String(e.value).toLowerCase().includes(f)
  )
})

const sortedEntries = computed(() => {
  const entries = [...filteredEntries.value]
  entries.sort((a, b) => {
    const va = sortBy.value === 'key' ? a.key : String(a.value)
    const vb = sortBy.value === 'key' ? b.key : String(b.value)
    const cmp = va.localeCompare(vb)
    return sortAsc.value ? cmp : -cmp
  })
  return entries
})

function toggleSort(field: 'key' | 'value') {
  if (sortBy.value === field) {
    sortAsc.value = !sortAsc.value
  } else {
    sortBy.value = field
    sortAsc.value = true
  }
}

function copyAllAsJson() {
  navigator.clipboard.writeText(JSON.stringify(props.detail.tags || {}, null, 2))
}
</script>

<style scoped>
.cursor-pointer { cursor: pointer; }
</style>
