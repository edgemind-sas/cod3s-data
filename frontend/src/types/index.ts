/** WebSocket message envelope */
export interface WsMessage {
  type: string
  id: string
  timestamp: string
  payload: Record<string, unknown>
}

/** Pipeline state */
export type PipelineState = 'idle' | 'running' | 'stopping' | 'stopped' | 'error'

/** Server event types */
export type EventType =
  | 'connected'
  | 'topology.update'
  | 'message.published'
  | 'metric.update'
  | 'component.state'
  | 'pipeline.state'
  | 'debug.paused'
  | 'debug.resumed'
  | 'debug.step_result'
  | 'error.occurred'

/** Channel info for a topology node */
export interface ChannelInfo {
  publishes: string[]
  subscribes: string[]
}

/** Topology node */
export interface TopologyNode {
  id: string
  type: 'source' | 'transformation' | 'destination'
  state: string
  channels: ChannelInfo
}

/** Topology edge */
export interface TopologyEdge {
  source_id: string
  target_id: string
  channel: string
  pattern: string
}

/** Message event data */
export interface MessageEvent {
  channel: string
  key: string | null
  subscriber_count: number
}

/** Metric event data */
export interface MetricEvent {
  metric_name: string
  value: number | Record<string, unknown>
  tags: Record<string, string>
}

/** Debug state */
export type DebugState = 'inactive' | 'running' | 'paused' | 'stepping'
export type Granularity = 'message' | 'stage' | 'breakpoint'

export interface Breakpoint {
  id: string
  channel_pattern: string
  condition: string | null
  component_id: string | null
  enabled: boolean
  hit_count: number
}

export interface DebugInfo {
  state: DebugState
  granularity: Granularity
  breakpoints: Breakpoint[]
  slow_motion: boolean
  slow_motion_delay_ms: number
  step_count: number
}
