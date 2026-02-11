import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { WsMessage } from '@/types'
import { useTopologyStore } from './topology'
import { useMessagesStore } from './messages'
import { useMetricsStore } from './metrics'
import { useDebugStore } from './debug'
import { usePipelineStore } from './pipeline'

export const useConnectionStore = defineStore('connection', () => {
  const ws = ref<WebSocket | null>(null)
  const status = ref<'disconnected' | 'connecting' | 'connected'>('disconnected')
  const error = ref<string | null>(null)
  const serverVersion = ref('')
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let reconnectAttempts = 0
  const maxReconnectDelay = 10000

  const connected = computed(() => status.value === 'connected')
  const reconnecting = computed(() => status.value === 'connecting' && reconnectAttempts > 0)

  function getWsUrl(): string {
    const loc = window.location
    const protocol = loc.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${loc.host}/ws`
  }

  function connect() {
    if (ws.value?.readyState === WebSocket.OPEN) return

    status.value = 'connecting'
    error.value = null

    const socket = new WebSocket(getWsUrl())
    ws.value = socket

    socket.onopen = () => {
      status.value = 'connected'
      reconnectAttempts = 0
      error.value = null
    }

    socket.onmessage = (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data)
        handleMessage(msg)
      } catch (e) {
        console.error('Failed to parse WebSocket message', e)
      }
    }

    socket.onclose = () => {
      status.value = 'disconnected'
      ws.value = null
      scheduleReconnect()
    }

    socket.onerror = () => {
      error.value = 'WebSocket connection error'
    }
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    reconnectAttempts = 0
    ws.value?.close()
    ws.value = null
    status.value = 'disconnected'
  }

  function scheduleReconnect() {
    if (reconnectTimer) return
    const delay = Math.min(1000 * Math.pow(1.5, reconnectAttempts), maxReconnectDelay)
    reconnectAttempts++
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, delay)
  }

  function send(msg: WsMessage) {
    if (ws.value?.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify(msg))
    }
  }

  function handleMessage(msg: WsMessage) {
    const topologyStore = useTopologyStore()
    const messagesStore = useMessagesStore()
    const metricsStore = useMetricsStore()
    const debugStore = useDebugStore()
    const pipelineStore = usePipelineStore()

    switch (msg.type) {
      case 'connected':
        serverVersion.value = (msg.payload.server_version as string) || ''
        if (msg.payload.debug) {
          debugStore.updateFromServer(msg.payload.debug as any)
        }
        if (msg.payload.pipeline_state) {
          pipelineStore.updateFromServer({ state: msg.payload.pipeline_state as any })
        }
        if (msg.payload.topology) {
          topologyStore.setTopology(msg.payload.topology as any)
        } else if (Array.isArray(msg.payload.components)) {
          for (const comp of msg.payload.components as any[]) {
            topologyStore.updateComponent({
              component_id: comp.component_id,
              component_type: comp.component_type,
              new_state: comp.state,
            })
          }
        }
        break

      case 'pipeline.state':
        pipelineStore.updateFromServer(msg.payload as any)
        break

      case 'component.state':
        topologyStore.updateComponent(msg.payload as any)
        break

      case 'topology.update':
        topologyStore.updateSubscription(msg.payload as any)
        break

      case 'message.published':
        messagesStore.addMessage({
          ...msg.payload as any,
          timestamp: msg.timestamp,
        })
        break

      case 'metric.update':
        metricsStore.addMetric(msg.payload as any)
        break

      case 'debug.paused':
      case 'debug.resumed':
      case 'debug.step_result':
        debugStore.updateFromServer(msg.payload as any)
        break

      case 'error.occurred':
        console.error('Observatory error:', msg.payload)
        break
    }
  }

  return {
    status,
    connected,
    reconnecting,
    error,
    serverVersion,
    connect,
    disconnect,
    send,
  }
})
