import { addEdge, applyEdgeChanges, applyNodeChanges } from '@xyflow/react'
import type {
  Connection,
  Edge,
  EdgeChange,
  Node as RFNode,
  NodeChange,
} from '@xyflow/react'
import { create } from 'zustand'

import { api } from './api/client'
import { TEACHING_LOOP } from './preset'
import type {
  ExecutionBrief,
  ExecutionDetail,
  JSONSchema,
  NodeType,
  NodeTypeMeta,
  WorkflowBrief,
  WorkflowEdge,
  WorkflowNode,
} from './types'

export interface NodeData extends Record<string, unknown> {
  name: string
  config: Record<string, unknown>
  nodeType: NodeType
}

export type FlowNode = RFNode<NodeData, NodeType>

export function shortId(): string {
  return Math.random().toString(16).slice(2, 10)
}

/** 从配置 JSON Schema 推导默认值，新增节点时字段不会是空的 */
export function defaultsFromSchema(schema: JSONSchema): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  for (const [key, prop] of Object.entries(schema.properties ?? {})) {
    if (prop.default !== undefined) {
      result[key] = prop.default
    } else if (prop.type === 'string') {
      result[key] = ''
    } else if (prop.type === 'integer' || prop.type === 'number') {
      result[key] = prop.minimum ?? 0
    } else if (prop.type === 'boolean') {
      result[key] = false
    } else if (prop.type === 'array') {
      result[key] = []
    } else if (prop.type === 'object') {
      result[key] = {}
    }
  }
  return result
}

/** 撤销/重做用的画布快照：只存节点与连线，不存 UI 状态 */
interface Snapshot {
  nodes: FlowNode[]
  edges: Edge[]
}

interface FlowState {
  workflowId: string | null
  name: string
  description: string
  version: number
  nodes: FlowNode[]
  edges: Edge[]
  selectedNodeId: string | null
  nodeTypes: NodeTypeMeta[]
  execution: ExecutionDetail | null
  running: boolean
  dirty: boolean
  error: string | null
  saving: boolean

  // 撤销/重做历史栈
  past: Snapshot[]
  future: Snapshot[]

  // 工作流列表与执行历史
  workflowList: WorkflowBrief[]
  executions: ExecutionBrief[]
  historyDetail: ExecutionDetail | null
  loadingList: boolean

  loadWorkflowList: () => Promise<void>
  loadExecutions: (workflowId?: string) => Promise<void>
  loadExecutionDetail: (id: string) => Promise<void>
  clearHistoryDetail: () => void

  loadNodeTypes: () => Promise<void>
  onNodesChange: (changes: NodeChange<FlowNode>[]) => void
  onEdgesChange: (changes: EdgeChange[]) => void
  onConnect: (connection: Connection) => void
  addNode: (type: NodeType, position: { x: number; y: number }) => void
  updateNodeConfig: (id: string, config: Record<string, unknown>) => void
  updateNodeName: (id: string, name: string) => void
  selectNode: (id: string | null) => void
  removeNode: (id: string) => void
  setMeta: (patch: { name?: string; description?: string }) => void
  exportJSON: () => string
  importJSON: (json: string) => void
  newWorkflow: () => void
  loadPreset: () => void
  loadWorkflow: (id: string) => Promise<void>
  deleteWorkflow: (id: string) => Promise<void>
  save: () => Promise<void>
  run: (inputs: Record<string, unknown>) => Promise<void>
  setError: (message: string | null) => void
  clearError: () => void

  // 历史相关
  takeSnapshot: () => void
  undo: () => void
  redo: () => void
  duplicateSelected: () => void
}

type AnyNode = FlowNode

export const useFlowStore = create<FlowState>((set, get) => ({
  workflowId: null,
  name: '未命名工作流',
  description: '',
  version: 1,
  nodes: [],
  edges: [],
  selectedNodeId: null,
  nodeTypes: [],
  execution: null,
  running: false,
  dirty: false,
  error: null,
  saving: false,
  past: [],
  future: [],

  workflowList: [],
  executions: [],
  historyDetail: null,
  loadingList: false,

  loadWorkflowList: async () => {
    set({ loadingList: true })
    try {
      const data = await api.listWorkflows()
      set({ workflowList: data.items, loadingList: false })
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : String(err),
        loadingList: false,
      })
    }
  },

  loadExecutions: async (workflowId) => {
    try {
      const data = await api.listExecutions({ workflowId })
      set({ executions: data.items })
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) })
    }
  },

  loadExecutionDetail: async (id) => {
    try {
      const detail = await api.getExecution(id)
      set({ historyDetail: detail })
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) })
    }
  },

  clearHistoryDetail: () => set({ historyDetail: null }),

  loadNodeTypes: async () => {
    try {
      const types = await api.listNodeTypes()
      set({ nodeTypes: types })
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) })
    }
  },

  onNodesChange: (changes) => {
    // 删除节点/连线时先留快照，这样 Delete/Backspace 删错也能撤销
    if (changes.some((c) => c.type === 'remove')) get().takeSnapshot()
    set((state) => ({ nodes: applyNodeChanges(changes, state.nodes), dirty: true }))
  },

  onEdgesChange: (changes) => {
    if (changes.some((c) => c.type === 'remove')) get().takeSnapshot()
    set((state) => ({ edges: applyEdgeChanges(changes, state.edges), dirty: true }))
  },

  onConnect: (connection) => {
    get().takeSnapshot()
    set((state) => ({
      edges: addEdge({ ...connection, id: shortId() }, state.edges),
      dirty: true,
    }))
  },

  addNode: (type, position) => {
    get().takeSnapshot()
    const meta = get().nodeTypes.find((t) => t.type === type)
    const config = meta ? defaultsFromSchema(meta.config_schema) : {}
    const node: AnyNode = {
      id: `${type}_${shortId()}`,
      type,
      position,
      data: { name: defaultName(type), config, nodeType: type },
    }
    set((state) => ({
      nodes: [...state.nodes, node],
      selectedNodeId: node.id,
      dirty: true,
    }))
  },

  updateNodeConfig: (id, config) =>
    set((state) => ({
      nodes: state.nodes.map((n) => (n.id === id ? { ...n, data: { ...n.data, config } } : n)),
      dirty: true,
    })),

  updateNodeName: (id, name) =>
    set((state) => ({
      nodes: state.nodes.map((n) => (n.id === id ? { ...n, data: { ...n.data, name } } : n)),
      dirty: true,
    })),

  selectNode: (id) => set({ selectedNodeId: id }),

  removeNode: (id) => {
    get().takeSnapshot()
    set((state) => ({
      nodes: state.nodes.filter((n) => n.id !== id),
      // 连带的连线一起清掉，否则会留下指向不存在节点的悬空连线
      edges: state.edges.filter((e) => e.source !== id && e.target !== id),
      selectedNodeId: state.selectedNodeId === id ? null : state.selectedNodeId,
      dirty: true,
    }))
  },

  setMeta: (patch) => set((state) => ({ ...state, ...patch, dirty: true })),

  exportJSON: () => {
    const state = get()
    return JSON.stringify(
      {
        name: state.name,
        description: state.description,
        nodes: state.nodes.map(toWorkflowNode),
        edges: state.edges.map(toWorkflowEdgePayload),
      },
      null,
      2,
    )
  },

  importJSON: (json) => {
    get().takeSnapshot()
    try {
      const data = JSON.parse(json) as {
        name?: string
        description?: string
        nodes?: WorkflowNode[]
        edges?: WorkflowEdge[]
      }
      // 导入的内容作为一条新工作流，保存时新建而不是覆盖原记录
      set({
        workflowId: null,
        name: data.name ?? '导入的工作流',
        description: data.description ?? '',
        version: 1,
        nodes: (data.nodes ?? []).map(toFlowNode),
        edges: (data.edges ?? []).map(toFlowEdge),
        selectedNodeId: null,
        execution: null,
        dirty: true,
        error: null,
      })
    } catch {
      set({ error: '导入失败：文件内容不是合法的 JSON' })
    }
  },

  newWorkflow: () => {
    get().takeSnapshot()
    set({
      workflowId: null,
      name: '未命名工作流',
      description: '',
      version: 1,
      nodes: [],
      edges: [],
      selectedNodeId: null,
      execution: null,
      dirty: false,
      error: null,
    })
  },

  loadPreset: () => {
    get().takeSnapshot()
    const tpl = TEACHING_LOOP
    set({
      workflowId: null,
      name: tpl.name,
      description: tpl.description,
      version: tpl.version,
      nodes: tpl.nodes.map(toFlowNode),
      edges: tpl.edges.map(toFlowEdge),
      selectedNodeId: null,
      execution: null,
      dirty: false,
      error: null,
    })
  },

  loadWorkflow: async (id) => {
    get().takeSnapshot()
    try {
      const wf = await api.getWorkflow(id)
      set({
        workflowId: wf.id,
        name: wf.name,
        description: wf.description,
        version: wf.version,
        nodes: wf.nodes.map(toFlowNode),
        edges: wf.edges.map(toFlowEdge),
        selectedNodeId: null,
        execution: null,
        dirty: false,
        error: null,
      })
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) })
    }
  },

  deleteWorkflow: async (id) => {
    try {
      await api.deleteWorkflow(id)
      set((state) => ({
        workflowList: state.workflowList.filter((w) => w.id !== id),
        // 删的是当前正在编辑的那条时，顺手回到空白状态
        ...(state.workflowId === id
          ? { workflowId: null, name: '未命名工作流', version: 1, dirty: false }
          : {}),
      }))
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) })
    }
  },

  save: async () => {
    const state = get()
    set({ saving: true, error: null })
    try {
      const payload = {
        name: state.name,
        description: state.description,
        nodes: state.nodes.map(toWorkflowNode),
        edges: state.edges.map(toWorkflowEdgePayload),
      }
      if (state.workflowId) {
        const saved = await api.updateWorkflow(state.workflowId, payload)
        set({ version: saved.version, dirty: false, saving: false })
      } else {
        const created = await api.createWorkflow(payload)
        set({ workflowId: created.id, version: created.version, dirty: false, saving: false })
      }
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : String(err),
        saving: false,
      })
    }
  },

  run: async (inputs) => {
    const state = get()
    if (!state.workflowId) {
      set({ error: '请先保存工作流再运行' })
      return
    }
    set({ running: true, error: null })
    try {
      const execution = await api.runWorkflow(state.workflowId, inputs)
      set({ execution, running: false })
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : String(err),
        running: false,
      })
    }
  },

  setError: (message) => set({ error: message }),

  clearError: () => set({ error: null }),

  // -------------------------------------------------------------- 历史栈
  takeSnapshot: () =>
    set((state) => {
      const snap: Snapshot = {
        nodes: structuredClone(state.nodes),
        edges: structuredClone(state.edges),
      }
      // 栈深上限 50，超出丢弃最旧的，避免无限增长拖慢页面
      const past = state.past.length >= 50 ? state.past.slice(1) : state.past.slice()
      past.push(snap)
      return { past, future: [] }
    }),

  undo: () =>
    set((state) => {
      if (state.past.length === 0) return {}
      const past = state.past.slice()
      const previous = past.pop() as Snapshot
      const current: Snapshot = {
        nodes: structuredClone(state.nodes),
        edges: structuredClone(state.edges),
      }
      return {
        nodes: previous.nodes,
        edges: previous.edges,
        past,
        future: state.future.concat(current),
        dirty: true,
        // 选中的节点被撤销删掉了就清空选择，避免配置面板指向幽灵节点
        selectedNodeId: previous.nodes.some((n) => n.id === state.selectedNodeId)
          ? state.selectedNodeId
          : null,
      }
    }),

  redo: () =>
    set((state) => {
      if (state.future.length === 0) return {}
      const future = state.future.slice()
      const next = future.pop() as Snapshot
      const current: Snapshot = {
        nodes: structuredClone(state.nodes),
        edges: structuredClone(state.edges),
      }
      return {
        nodes: next.nodes,
        edges: next.edges,
        past: state.past.concat(current),
        future,
        dirty: true,
        selectedNodeId: next.nodes.some((n) => n.id === state.selectedNodeId)
          ? state.selectedNodeId
          : null,
      }
    }),

  // 复制选中节点：连同与它相连的边一起复制，端点改指向新节点
  duplicateSelected: () => {
    const state = get()
    const id = state.selectedNodeId
    if (!id) return
    const node = state.nodes.find((n) => n.id === id)
    if (!node) return
    get().takeSnapshot()
    const newId = `${node.data.nodeType}_${shortId()}`
    const copy: AnyNode = structuredClone(node)
    copy.id = newId
    copy.position = { x: node.position.x + 48, y: node.position.y + 48 }
    copy.data = { ...node.data, name: `${node.data.name} 副本` }
    copy.selected = true
    const clonedEdges = state.edges
      .filter((e) => e.source === id || e.target === id)
      .map((e) => {
        const c = structuredClone(e)
        c.id = shortId()
        if (c.source === id) c.source = newId
        if (c.target === id) c.target = newId
        return c
      })
    set((s) => ({
      nodes: [...s.nodes.map((n) => ({ ...n, selected: false })), copy],
      edges: [...s.edges, ...clonedEdges],
      selectedNodeId: newId,
    }))
  },
}))

function defaultName(type: NodeType): string {
  const labels: Record<NodeType, string> = {
    start: '开始',
    llm: '调用模型',
    http: 'HTTP 请求',
    condition: '条件分支',
    end: '结束',
    question: '智能出题',
    grading: '作业批改',
    analytics: '学情分析',
  }
  return labels[type]
}

// ---------------------------------------------------------------- 结构转换

function toFlowNode(node: WorkflowNode): AnyNode {
  return {
    id: node.id,
    type: node.type,
    position: node.position,
    data: { name: node.name, config: node.config, nodeType: node.type },
  }
}

function toFlowEdge(edge: WorkflowEdge): Edge {
  return {
    id: edge.id ?? shortId(),
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.source_handle ?? undefined,
    data: { condition: edge.condition ?? null },
  }
}

function toWorkflowNode(node: AnyNode): WorkflowNode {
  return {
    id: node.id,
    type: node.data.nodeType,
    name: node.data.name,
    config: node.data.config,
    position: node.position,
  }
}

function toWorkflowEdgePayload(edge: Edge): WorkflowEdge {
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    source_handle: edge.sourceHandle ?? null,
    condition: (edge.data?.condition as string | null) ?? null,
  }
}
