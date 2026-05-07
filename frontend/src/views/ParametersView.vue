<template>
  <div>
    <div class="d-flex align-center mb-4">
      <h1 class="text-h5">Pipeline Parameters</h1>
      <v-spacer />
      <v-btn
        size="small"
        variant="text"
        prepend-icon="mdi-refresh"
        :loading="parametersStore.loading"
        @click="params.refresh()"
      >
        Refresh
      </v-btn>
    </div>

    <v-alert v-if="parametersStore.error" type="error" class="mb-4" density="compact">
      {{ parametersStore.error }}
    </v-alert>

    <v-card v-if="parametersStore.params.length > 0">
      <v-table density="compact">
        <thead>
          <tr>
            <th>Component</th>
            <th>Param</th>
            <th>Channel</th>
            <th>Default</th>
            <th>Current</th>
            <th style="width: 320px">New value</th>
            <th style="width: 80px"></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="p in parametersStore.params"
            :key="`${p.component_id}::${p.param_name}`"
          >
            <td>
              <div class="font-weight-medium">{{ p.component_label || p.component_id }}</div>
              <div class="text-caption text-medium-emphasis">{{ p.component_id }}</div>
            </td>
            <td><code>{{ p.param_name }}</code></td>
            <td class="text-caption">
              <code>{{ p.channel }}</code>
              <span v-if="p.key" class="text-medium-emphasis"> · key={{ p.key }}</span>
            </td>
            <td class="text-caption">{{ formatValue(p.default) }}</td>
            <td>
              <v-chip size="small" :color="hasPending(p) ? 'orange' : 'primary'" variant="tonal">
                {{ formatValue(p.current) }}
              </v-chip>
            </td>
            <td>
              <v-text-field
                :model-value="draftFor(p)"
                density="compact"
                hide-details
                variant="outlined"
                placeholder="value (number, string, JSON)"
                @update:model-value="(v: string) => setDraft(p, v)"
                @keyup.enter="apply(p)"
              />
            </td>
            <td>
              <v-btn
                size="small"
                color="primary"
                variant="flat"
                :disabled="!isDraftValid(p)"
                @click="apply(p)"
              >
                Apply
              </v-btn>
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <v-card v-else-if="!parametersStore.loading" variant="tonal">
      <v-card-text>
        <p class="text-medium-emphasis">
          No editable parameters declared.
        </p>
        <p class="text-caption mt-2">
          Declare a parameter as <code>{ ref: "params.foo", default: 1.0 }</code>
          in a transformation's <code>params</code> block to make it editable here.
        </p>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive } from 'vue'
import { useParametersStore } from '@/stores/parameters'
import { useParameters } from '@/composables/useParameters'
import type { Param } from '@/types'

const parametersStore = useParametersStore()
const params = useParameters()

// Drafts keyed by `${component_id}::${param_name}` so the user can stage a
// new value, hit Apply, and watch it propagate via the param.updated event.
const drafts = reactive<Record<string, string>>({})

const draftKey = (p: Param) => `${p.component_id}::${p.param_name}`

function draftFor(p: Param): string {
  return drafts[draftKey(p)] ?? ''
}

function setDraft(p: Param, v: string) {
  drafts[draftKey(p)] = v
}

function isDraftValid(p: Param): boolean {
  const raw = draftFor(p).trim()
  if (!raw) return false
  return parseValue(raw) !== undefined
}

function hasPending(p: Param): boolean {
  return draftFor(p).trim().length > 0
}

function apply(p: Param) {
  const raw = draftFor(p).trim()
  const parsed = parseValue(raw)
  if (parsed === undefined) return
  params.update(p.channel, parsed, p.key)
  drafts[draftKey(p)] = ''
}

function parseValue(raw: string): unknown | undefined {
  // Try number first, then JSON (covers booleans, dicts, arrays, quoted strings),
  // fall back to the raw string. Returns undefined if input is empty.
  if (!raw) return undefined
  const asNumber = Number(raw)
  if (!Number.isNaN(asNumber) && raw.match(/^-?\d+(\.\d+)?([eE][+-]?\d+)?$/)) {
    return asNumber
  }
  try {
    return JSON.parse(raw)
  } catch {
    return raw
  }
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

onMounted(() => {
  params.refresh()
})
</script>
