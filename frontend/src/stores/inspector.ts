import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { MessageDetail, InspectorTab } from '@/types'

export const useInspectorStore = defineStore('inspector', () => {
  const isOpen = ref(false)
  const panelHeight = ref(400)
  const activeTab = ref<InspectorTab>('SUMMARY')
  const selectedMessageId = ref<string | null>(null)
  const messageDetail = ref<MessageDetail | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const hasDetail = computed(() => messageDetail.value !== null)

  function selectMessage(id: string) {
    selectedMessageId.value = id
    isOpen.value = true
    loading.value = true
    error.value = null
    messageDetail.value = null
  }

  function setDetail(detail: MessageDetail) {
    messageDetail.value = detail
    loading.value = false
    error.value = null
  }

  function setError(msg: string) {
    loading.value = false
    error.value = msg
  }

  function close() {
    isOpen.value = false
    selectedMessageId.value = null
    messageDetail.value = null
    loading.value = false
    error.value = null
  }

  function toggle() {
    if (isOpen.value) {
      close()
    } else {
      isOpen.value = true
    }
  }

  return {
    isOpen,
    panelHeight,
    activeTab,
    selectedMessageId,
    messageDetail,
    loading,
    error,
    hasDetail,
    selectMessage,
    setDetail,
    setError,
    close,
    toggle,
  }
})
