import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Param, ParamUpdatedEvent } from '@/types'

export const useParametersStore = defineStore('parameters', () => {
  const params = ref<Param[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchAll() {
    loading.value = true
    error.value = null
    try {
      const res = await fetch('/api/params')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const body = (await res.json()) as { params: Param[] }
      params.value = body.params
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  function applyUpdate(evt: ParamUpdatedEvent) {
    // Match on (component_id, param_name) — channel may be shared by multiple components.
    const target = params.value.find(
      (p) => p.component_id === evt.component_id && p.param_name === evt.param_name,
    )
    if (target) {
      target.current = evt.new_value
    }
  }

  return { params, loading, error, fetchAll, applyUpdate }
})
