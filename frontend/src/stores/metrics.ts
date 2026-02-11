import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface MetricPoint {
  metric_name: string
  value: number | Record<string, unknown>
  tags: Record<string, string>
  timestamp: string
}

export const useMetricsStore = defineStore('metrics', () => {
  const metrics = ref<MetricPoint[]>([])
  const maxPoints = 500

  const latestByName = computed(() => {
    const map: Record<string, MetricPoint> = {}
    for (const m of metrics.value) {
      map[m.metric_name] = m
    }
    return map
  })

  function addMetric(data: { metric_name: string; value: number | Record<string, unknown>; tags: Record<string, string> }) {
    const point: MetricPoint = {
      ...data,
      timestamp: new Date().toISOString(),
    }
    metrics.value.push(point)
    if (metrics.value.length > maxPoints) {
      metrics.value = metrics.value.slice(-maxPoints)
    }
  }

  function getHistory(metricName: string, limit = 100): MetricPoint[] {
    return metrics.value.filter(m => m.metric_name === metricName).slice(-limit)
  }

  return { metrics, latestByName, addMetric, getHistory }
})
