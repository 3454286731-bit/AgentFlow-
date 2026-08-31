import type {
  ExecutionBrief,
  ExecutionDetail,
  NodeTypeMeta,
  Workflow,
  WorkflowBrief,
} from '../types'

const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })

  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`
    try {
      const data = await resp.json()
      detail = data.detail ?? detail
    } catch {
      // 响应体不是 JSON，沿用状态码文案
    }
    throw new Error(detail)
  }

  if (resp.status === 204) {
    return undefined as T
  }
  return (await resp.json()) as T
}

export interface WorkflowPayload {
  name: string
  description?: string
  nodes: Workflow['nodes']
  edges: Workflow['edges']
}

export const api = {
  listNodeTypes: () => request<NodeTypeMeta[]>('/node-types'),

  listWorkflows: () => request<{ items: WorkflowBrief[]; total: number }>('/workflows'),

  getWorkflow: (id: string) => request<Workflow & { node_count: number }>(`/workflows/${id}`),

  createWorkflow: (payload: WorkflowPayload) =>
    request<Workflow & { node_count: number }>('/workflows', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateWorkflow: (id: string, payload: Partial<WorkflowPayload>) =>
    request<Workflow & { node_count: number }>(`/workflows/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  deleteWorkflow: (id: string) =>
    request<void>(`/workflows/${id}`, { method: 'DELETE' }),

  runWorkflow: (id: string, inputs: Record<string, unknown>) =>
    request<ExecutionDetail>(`/workflows/${id}/run`, {
      method: 'POST',
      body: JSON.stringify({ inputs }),
    }),

  listExecutions: (params?: { workflowId?: string; status?: string }) => {
    const search = new URLSearchParams()
    if (params?.workflowId) search.set('workflow_id', params.workflowId)
    if (params?.status) search.set('status', params.status)
    const query = search.toString()
    return request<{ items: ExecutionBrief[]; total: number }>(
      `/executions${query ? `?${query}` : ''}`,
    )
  },

  listWorkflowExecutions: (workflowId: string) =>
    request<{ items: ExecutionBrief[]; total: number }>(
      `/workflows/${workflowId}/executions`,
    ),

  getExecution: (id: string) => request<ExecutionDetail>(`/executions/${id}`),
}
