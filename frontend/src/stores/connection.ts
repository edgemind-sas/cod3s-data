import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { WsMessage } from '@/types'
import { useTopologyStore } from './topology'
import { useMessagesStore } from './messages'
import { useMetricsStore } from './metrics'
import { useDebugStore } from './debug'
import { usePipelineStore } from './pipeline'
import { useInspectorStore } from './inspector'
import { useParametersStore } from './parameters'

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
    const inspectorStore = useInspectorStore()
    const parametersStore = useParametersStore()

    switch (msg.type) {
      // High-frequency events arrive coalesced: one frame carrying a window of
      // envelopes, rather than one frame per published message. Each is
      // dispatched exactly as if it had come on its own.
      case 'batch': {
        const events = (msg.payload as any)?.events
        if (Array.isArray(events)) {
          for (const event of events) handleMessage(event as WsMessage)
        }
        break
      }

      case 'connected':
        serverVersion.value = (msg.payload.server_version as string) || ''
        // Before hydrating: the cap decides what the snapshot is trimmed to.
        if (typeof msg.payload.history_size === 'number') {
          messagesStore.setMaxMessages(msg.payload.history_size)
        }
        // The snapshot's history was being sent and dropped: a page reload, or
        // opening the Observatory on a pipeline already running, started from an
        // empty Timeline and an empty Messages table while the server had just
        // shipped its last hundred messages. Buffer events are wrapped as
        // {type, timestamp, data}, so the envelope's timestamp is the one to keep.
        // Only on a first connection: a reconnect would re-add messages the
        // store already has, and replacing it with the server's last hundred
        // would throw away the history the client kept.
        if (Array.isArray(msg.payload.messages) && messagesStore.messageCount === 0) {
          for (const event of msg.payload.messages as any[]) {
            if (!event?.data) continue
            messagesStore.addMessage({ ...event.data, timestamp: event.timestamp })
          }
        }
        if (msg.payload.debug) {
          debugStore.updateFromServer(msg.payload.debug as any)
        }
        if (msg.payload.pipeline_info) {
          pipelineStore.updateInfoFromServer(msg.payload.pipeline_info as any)
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
        topologyStore.markChannelActive((msg.payload as any).channel)
        break

      case 'metric.update':
        metricsStore.addMetric(msg.payload as any)
        break

      case 'debug.paused':
      case 'debug.resumed':
      case 'debug.granularity_set':
      case 'debug.slow_motion_set':
        debugStore.updateFromServer(msg.payload as any)
        break

      case 'debug.step_started':
        debugStore.setStepPending(true)
        debugStore.updateFromServer(msg.payload as any)
        break

      case 'debug.step_result':
        debugStore.setStepPending(false)
        debugStore.updateFromServer(msg.payload as any)
        break

      case 'message.detail': {
        // Clicking through rows faster than the server answers can land an
        // older reply last; keep the one that was actually asked for.
        const detail = msg.payload as any
        if (!inspectorStore.selectedMessageId || detail?.message_id === inspectorStore.selectedMessageId) {
          inspectorStore.setDetail(detail)
        }
        break
      }

      case 'param.updated':
        parametersStore.applyUpdate(msg.payload as any)
        break

      // The server sends plain 'error' for a failed command; only 'error.occurred'
      // was handled, so an inspect that missed its cache went nowhere and the
      // panel stayed on its spinner for good.
      case 'error':
      case 'error.occurred': {
        console.error('Observatory error:', msg.payload)
        const failedId = (msg.payload as any)?.message_id
        if (failedId && failedId === inspectorStore.selectedMessageId) {
          inspectorStore.setError(
            (msg.payload as any)?.message || 'Message details are no longer available.'
          )
        }
        break
      }
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
