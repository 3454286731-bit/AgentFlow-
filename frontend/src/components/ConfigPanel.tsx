import { useMemo, useState } from 'react'

import { SchemaForm } from './SchemaForm'
import { useFlowStore } from '../store'

/**
 * 节点配置面板。表单完全由后端返回的 JSON Schema 驱动，
 * 后端新增配置字段时前端不需要改一行代码。
 */
export function ConfigPanel() {
  const selectedNodeId = useFlowStore((s) => s.selectedNodeId)
  const nodes = useFlowStore((s) => s.nodes)
  const nodeTypes = useFlowStore((s) => s.nodeTypes)
  const updateNodeConfig = useFlowStore((s) => s.updateNodeConfig)
  const updateNodeName = useFlowStore((s) => s.updateNodeName)
  const removeNode = useFlowStore((s) => s.removeNode)

  const node = nodes.find((n) => n.id === selectedNodeId)

  if (!node) {
    return (
      <div className="panel-empty">
        <p>在画布上选中一个节点</p>
        <p className="panel-empty-hint">选中后这里会显示它的配置项</p>
      </div>
    )
  }

  const meta = nodeTypes.find((t) => t.type === node.data.nodeType)
  if (!meta) {
    return <div className="panel-empty">节点类型元数据还没加载完</div>
  }

  return (
    <div className="config-panel">
      <div className="field">
        <label className="field-label">节点名称</label>
        <input
          className="field-input"
          value={node.data.name}
          onChange={(event) => updateNodeName(node.id, event.target.value)}
        />
      </div>

      <UpstreamVars nodeId={node.id} />

      <div className="panel-divider" />

      <SchemaForm
        schema={meta.config_schema}
        value={node.data.config}
        onChange={(next) => updateNodeConfig(node.id, next as Record<string, unknown>)}
      />

      <p className="panel-hint">
        字段与校验规则来自后端 <code>/api/node-types</code>，星号表示必填
      </p>

      <button className="btn-danger" onClick={() => removeNode(node.id)}>
        删除此节点
      </button>
    </div>
  )
}

/**
 * 列出当前节点可以引用的上游变量，点击即复制。
 * 手写 {{node_1.output}} 很容易写错节点 ID，这里直接给出可点的选项。
 */
function UpstreamVars({ nodeId }: { nodeId: string }) {
  const nodes = useFlowStore((s) => s.nodes)
  const edges = useFlowStore((s) => s.edges)
  const [copied, setCopied] = useState<string | null>(null)

  const variables = useMemo(() => {
    const upstreamIds = edges.filter((e) => e.target === nodeId).map((e) => e.source)
    const list: Array<{ label: string; value: string }> = []
    for (const id of upstreamIds) {
      const upstream = nodes.find((n) => n.id === id)
      if (!upstream) continue
      list.push({ label: `${upstream.data.name} 的输出`, value: `{{${id}.output}}` })
      // 开始节点定义的输入变量可以直接按名字引用
      if (upstream.data.nodeType === 'start') {
        const inputs = upstream.data.config.inputs as Record<string, unknown> | undefined
        for (const key of Object.keys(inputs ?? {})) {
          list.push({ label: `${upstream.data.name} · ${key}`, value: `{{${key}}}` })
        }
      }
    }
    return list
  }, [edges, nodes, nodeId])

  if (variables.length === 0) {
    return null
  }

  const copy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(value)
      window.setTimeout(() => setCopied(null), 1500)
    } catch {
      // 浏览器限制剪贴板访问时静默降级，用户仍可手动选中复制
    }
  }

  return (
    <div className="vars-block">
      <div className="vars-title">可引用的上游变量</div>
      <div className="vars-list">
        {variables.map((item) => (
          <button
            key={item.value}
            className="var-chip"
            title="点击复制"
            onClick={() => void copy(item.value)}
          >
            <span>{item.label}</span>
            <code>{item.value}</code>
          </button>
        ))}
      </div>
      {copied && <div className="vars-copied">已复制 {copied}</div>}
    </div>
  )
}
