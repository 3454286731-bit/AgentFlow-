export type NodeType = 'start' | 'llm' | 'http' | 'condition' | 'end' | 'question' | 'grading' | 'analytics'

export type RunStatus = 'pending' | 'running' | 'success' | 'failed' | 'skipped'

export interface Position {
  x: number
  y: number
}

export interface WorkflowNode {
  id: string
  type: NodeType
  name: string
  config: Record<string, unknown>
  position: Position
}

export interface WorkflowEdge {
  id?: string
  source: string
  target: string
  source_handle?: string | null
  condition?: string | null
}

export interface Workflow {
  id: string
  name: string
  description: string
  version: number
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
  updated_at?: string
}

export interface JSONSchema {
  type?: string
  title?: string
  description?: string
  properties?: Record<string, JSONSchema>
  required?: string[]
  default?: unknown
  enum?: (string | number)[]
  items?: JSONSchema
  additionalProperties?: boolean
  minimum?: number
  maximum?: number
}

export interface NodeTypeMeta {
  type: NodeType
  config_schema: JSONSchema
}

export interface NodeResult {
  node_id: string
  node_type: NodeType
  status: RunStatus
  output: unknown
  error: string | null
  duration_ms: number
}

export interface ExecutionDetail {
  id: string
  workflow_id: string
  workflow_name: string
  status: string
  inputs: Record<string, unknown>
  final_output: unknown
  node_results: NodeResult[]
  error: string | null
  duration_ms: number
  started_at: string
  finished_at?: string | null
}

export interface ExecutionBrief {
  id: string
  workflow_id: string
  workflow_name: string
  status: string
  duration_ms: number
  started_at: string
  error: string | null
}

export interface WorkflowBrief {
  id: string
  name: string
  description: string
  version: number
  node_count: number
  edge_count: number
  updated_at: string
}
