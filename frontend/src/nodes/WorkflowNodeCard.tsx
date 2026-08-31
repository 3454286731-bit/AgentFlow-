import { Handle, Position } from '@xyflow/react'
import type { NodeProps } from '@xyflow/react'

import { useFlowStore } from '../store'
import type { FlowNode, NodeData } from '../store'
import type { NodeType, RunStatus } from '../types'

const TYPE_LABEL: Record<NodeType, string> = {
  start: '开始',
  llm: '模型',
  http: 'HTTP',
  condition: '条件',
  end: '结束',
  question: '出题',
  grading: '批改',
  analytics: '学情',
}

const STATUS_LABEL: Record<RunStatus, string> = {
  pending: '等待',
  running: '执行中',
  success: '成功',
  failed: '失败',
  skipped: '跳过',
}

/**
 * 画布上的节点卡片。五种类型共用一个组件，靠 data.nodeType 区分渲染内容。
 * 条件节点会按分支数量渲染多个出口句柄，每个句柄对应一个分支。
 */
export function WorkflowNodeCard({ id, data, selected }: NodeProps<FlowNode>) {
  const execution = useFlowStore((s) => s.execution)
  const result = execution?.node_results.find((r) => r.node_id === id)

  return (
    <div className={`node-card node-${data.nodeType} ${selected ? 'is-selected' : ''}`}>
      {data.nodeType !== 'start' && <Handle type="target" position={Position.Left} />}

      <div className="node-head">
        <span className="node-type">{TYPE_LABEL[data.nodeType]}</span>
        {result && (
          <span className={`node-status status-${result.status}`} title={result.error ?? ''}>
            {STATUS_LABEL[result.status]}
            {result.duration_ms > 0 && ` ${result.duration_ms}ms`}
          </span>
        )}
      </div>

      <div className="node-name">{data.name}</div>
      <div className="node-summary">{summarize(data)}</div>

      <ConditionHandles data={data} />
    </div>
  )
}

function ConditionHandles({ data }: { data: NodeData }) {
  if (data.nodeType === 'end') {
    return null
  }

  if (data.nodeType !== 'condition') {
    return <Handle type="source" position={Position.Right} />
  }

  const branches = (data.config.branches as Array<{ handle: string; label?: string }>) ?? []
  const defaultHandle = (data.config.default_handle as string | undefined) ?? 'else'
  const outlets = [
    ...branches.map((b) => ({ handle: b.handle, label: b.label || b.handle })),
    { handle: defaultHandle, label: '默认' },
  ]

  return (
    <div className="node-branches">
      {outlets.map((outlet) => (
        <div className="branch-row" key={outlet.handle}>
          <span className="branch-label">{outlet.label}</span>
          <Handle type="source" position={Position.Right} id={outlet.handle} />
        </div>
      ))}
    </div>
  )
}

function summarize(data: NodeData): string {
  const cfg = data.config
  switch (data.nodeType) {
    case 'start': {
      const inputs = (cfg.inputs as Record<string, unknown>) ?? {}
      const keys = Object.keys(inputs)
      return keys.length ? `输入变量：${keys.join('、')}` : '未定义输入变量'
    }
    case 'llm': {
      const prompt = String(cfg.prompt ?? '')
      return prompt ? `提示词：${truncate(prompt, 40)}` : '未填写提示词'
    }
    case 'http':
      return `${cfg.method ?? 'GET'} ${truncate(String(cfg.url ?? ''), 32) || '未填写地址'}`
    case 'condition': {
      const branches = (cfg.branches as Array<unknown>) ?? []
      return `${branches.length + 1} 个出口分支`
    }
    case 'end': {
      const tpl = String(cfg.output_template ?? '')
      return tpl ? `输出：${truncate(tpl, 40)}` : '直接输出上游结果'
    }
    case 'question': {
      const kp = String(cfg.knowledge_point ?? '')
      const n = Number(cfg.count ?? 0)
      return kp ? `知识点：${truncate(kp, 24)} × ${n} 题` : '未填写知识点'
    }
    case 'grading': {
      const rubric = String(cfg.rubric ?? '')
      return rubric ? `评分细则：${truncate(rubric, 28)}` : '未填写评分细则'
    }
    case 'analytics': {
      const dim = String(cfg.dimension ?? 'knowledge')
      return `维度：${DIM_LABEL[dim as keyof typeof DIM_LABEL] ?? dim}`
    }
    default:
      return ''
  }
}

const DIM_LABEL: Record<string, string> = {
  knowledge: '知识点',
  skill: '能力',
  progress: '进度',
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}…` : text
}

export const nodeTypes = {
  start: WorkflowNodeCard,
  llm: WorkflowNodeCard,
  http: WorkflowNodeCard,
  condition: WorkflowNodeCard,
  end: WorkflowNodeCard,
  question: WorkflowNodeCard,
  grading: WorkflowNodeCard,
  analytics: WorkflowNodeCard,
}
