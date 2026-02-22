<template>
  <div class="value-tab pa-2">
    <TreeNode :data="detail.value" path="value" :depth="0" />
  </div>
</template>

<script setup lang="ts">
import type { MessageDetail } from '@/types'
import TreeNode from './TreeNode.vue'

defineProps<{ detail: MessageDetail }>()
</script>

<style scoped>
.value-tab {
  font-family: monospace;
  font-size: 13px;
  overflow: auto;
}
</style>
