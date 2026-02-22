<template>
  <!-- Collapsed bar -->
  <div
    v-if="!store.isOpen"
    class="inspector-collapsed"
    @click="store.toggle()"
  >
    <v-icon size="16" class="mr-1">mdi-magnify</v-icon>
    Inspector
  </div>

  <!-- Expanded panel -->
  <div
    v-else
    class="inspector-panel"
    :style="{ height: store.panelHeight + 'px' }"
  >
    <!-- Drag handle -->
    <div
      class="inspector-drag-handle"
      @mousedown="startResize"
    >
      <div class="drag-indicator"></div>
    </div>

    <!-- Header -->
    <div class="inspector-header d-flex align-center px-3">
      <v-tabs v-model="store.activeTab" density="compact" class="flex-grow-1">
        <v-tab value="SUMMARY" size="small">Summary</v-tab>
        <v-tab value="VALUE" size="small">Value</v-tab>
        <v-tab value="TAGS" size="small">Tags</v-tab>
        <v-tab value="JOURNEY" size="small">Journey</v-tab>
        <v-tab value="RAW" size="small">Raw JSON</v-tab>
      </v-tabs>
      <v-btn icon size="x-small" variant="text" @click="store.close()">
        <v-icon>mdi-close</v-icon>
      </v-btn>
    </div>

    <!-- Loading -->
    <v-progress-linear v-if="store.loading" indeterminate color="primary" />

    <!-- Error -->
    <div v-if="store.error" class="pa-4 text-center text-error">
      {{ store.error }}
    </div>

    <!-- Content -->
    <div v-else-if="store.messageDetail" class="inspector-content">
      <SummaryTab v-if="store.activeTab === 'SUMMARY'" :detail="store.messageDetail" />
      <ValueTab v-else-if="store.activeTab === 'VALUE'" :detail="store.messageDetail" />
      <TagsTab v-else-if="store.activeTab === 'TAGS'" :detail="store.messageDetail" />
      <JourneyTab v-else-if="store.activeTab === 'JOURNEY'" :detail="store.messageDetail" />
      <RawJsonTab v-else-if="store.activeTab === 'RAW'" :detail="store.messageDetail" />
    </div>

    <!-- No selection -->
    <div v-else-if="!store.loading" class="pa-4 text-center text-medium-emphasis">
      Click a message row to inspect it.
    </div>
  </div>
</template>

<script setup lang="ts">
import { useInspectorStore } from '@/stores/inspector'
import SummaryTab from './SummaryTab.vue'
import ValueTab from './ValueTab.vue'
import TagsTab from './TagsTab.vue'
import JourneyTab from './JourneyTab.vue'
import RawJsonTab from './RawJsonTab.vue'

const store = useInspectorStore()

function startResize(e: MouseEvent) {
  e.preventDefault()
  const startY = e.clientY
  const startHeight = store.panelHeight

  function onMouseMove(ev: MouseEvent) {
    const delta = startY - ev.clientY
    const newHeight = Math.max(200, Math.min(window.innerHeight * 0.8, startHeight + delta))
    store.panelHeight = newHeight
  }

  function onMouseUp() {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  }

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}
</script>

<style scoped>
.inspector-collapsed {
  position: fixed;
  bottom: 0;
  left: 256px;
  right: 0;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgb(var(--v-theme-surface));
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 13px;
  z-index: 10;
  user-select: none;
}

.inspector-collapsed:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.inspector-panel {
  position: fixed;
  bottom: 0;
  left: 256px;
  right: 0;
  background: rgb(var(--v-theme-surface));
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  display: flex;
  flex-direction: column;
  z-index: 10;
}

.inspector-drag-handle {
  height: 6px;
  cursor: ns-resize;
  display: flex;
  align-items: center;
  justify-content: center;
}

.drag-indicator {
  width: 40px;
  height: 3px;
  border-radius: 2px;
  background: rgba(var(--v-theme-on-surface), 0.2);
}

.inspector-drag-handle:hover .drag-indicator {
  background: rgba(var(--v-theme-on-surface), 0.4);
}

.inspector-header {
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  min-height: 40px;
}

.inspector-content {
  flex: 1;
  overflow: auto;
}
</style>
