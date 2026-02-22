<template>
  <div class="pa-2">
    <div class="d-flex align-center ga-2 mb-2">
      <v-switch
        v-model="pretty"
        density="compact"
        hide-details
        label="Pretty"
        class="flex-grow-0"
      />
      <v-spacer />
      <v-btn size="small" variant="text" @click="copyJson">
        <v-icon start size="16">mdi-content-copy</v-icon>
        Copy
      </v-btn>
      <v-btn size="small" variant="text" @click="downloadJson">
        <v-icon start size="16">mdi-download</v-icon>
        Download
      </v-btn>
    </div>

    <div class="raw-json-container">
      <pre class="raw-json" v-html="highlighted"></pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { MessageDetail } from '@/types'

const props = defineProps<{ detail: MessageDetail }>()

const pretty = ref(true)

const jsonString = computed(() => {
  return JSON.stringify(props.detail, null, pretty.value ? 2 : undefined)
})

const highlighted = computed(() => highlightJson(jsonString.value))

function highlightJson(json: string): string {
  return json.replace(
    /("(?:\\.|[^"\\])*")\s*:/g,
    '<span class="json-key">$1</span>:'
  ).replace(
    /:\s*("(?:\\.|[^"\\])*")/g,
    ': <span class="json-string">$1</span>'
  ).replace(
    /:\s*(\d+\.?\d*)/g,
    ': <span class="json-number">$1</span>'
  ).replace(
    /:\s*(true|false)/g,
    ': <span class="json-boolean">$1</span>'
  ).replace(
    /:\s*(null)/g,
    ': <span class="json-null">$1</span>'
  )
}

function copyJson() {
  navigator.clipboard.writeText(jsonString.value)
}

function downloadJson() {
  const blob = new Blob([jsonString.value], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `message-${props.detail.message_id}.json`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.raw-json-container {
  max-height: 300px;
  overflow: auto;
  background: #1e1e1e;
  border-radius: 4px;
}

.raw-json {
  padding: 12px;
  margin: 0;
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.5;
  color: #d4d4d4;
  white-space: pre-wrap;
  word-break: break-all;
}

:deep(.json-key) { color: #c586c0; }
:deep(.json-string) { color: #6a9955; }
:deep(.json-number) { color: #569cd6; }
:deep(.json-boolean) { color: #ce9178; }
:deep(.json-null) { color: #808080; font-style: italic; }
</style>
