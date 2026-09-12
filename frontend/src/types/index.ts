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
  | 'param.updated'

/** Channel info for a topology node */
export interface ChannelInfo {
  publishes: string[]
  subscribes: string[]
  /** Channels read as parameters (ParamRef), not as data */
  parameters?: ParamChannel[]
}

/** A parameter a component reads from a broker channel */
export interface ParamChannel {
  param: string
  channel: string
}

/** Topology node */
export interface TopologyNode {
  id: string
  type: 'source' | 'transformation' | 'destination'
  state: string
  label: string
  description: string
  channels: ChannelInfo
}

/** Topology edge */
export interface TopologyEdge {
  source_id: string
  target_id: string
  channel: string
  pattern: string
  /** 'data' = ordinary flow, 'parameter' = feeds a ParamRef */
  kind?: 'data' | 'parameter'
  /** Name of the parameter fed, on 'parameter' edges */
  param?: string
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

/** Message Inspector types */
export interface JourneyStep {
  stage: 'PUBLISHED' | 'RECEIVED' | 'PROCESSED' | 'DELIVERED'
  component_id: string
  component_type: string
  channel: string
  message_id: string
  parent_message_id: string
  label: string
  timestamp: string
}

/**
 * A node in the journey tree.
 *
 * Each step in the journey becomes a node. Children represent the next
 * steps in the message flow:
 * - PUBLISHED → children are the RECEIVED/DELIVERED receivers (one branch per receiver)
 * - RECEIVED → child is the PROCESSED step (if transform produces output)
 * - PROCESSED → child is the PUBLISHED step (re-publication)
 * - DELIVERED → leaf node (end of branch)
 */
export interface JourneyTreeNode {
  step: JourneyStep
  children: JourneyTreeNode[]
}

export interface MessageDetail {
  message_id: string
  channel: string
  key: string | null
  value: unknown
  value_type: string
  tags: Record<string, string>
  subscriber_count: number
  /** The source's own timestamp — what InfluxDB and Grafana index on. */
  timestamp: string
  /** When the pipeline published it: the Observatory's own clock. */
  observed_at?: string
  trace_id: string
  journey: JourneyStep[]
}

export type InspectorTab = 'SUMMARY' | 'VALUE' | 'TAGS' | 'JOURNEY' | 'RAW'

/** Pipeline parameter declared via ParamRef */
export interface Param {
  component_id: string
  component_label: string
  param_name: string
  channel: string
  key: string | null
  default: unknown
  current: unknown
}

/** WebSocket payload for param.updated events */
export interface ParamUpdatedEvent {
  component_id: string
  param_name: string
  channel: string
  old_value: unknown
  new_value: unknown
  label: string
}
