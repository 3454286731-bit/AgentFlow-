import { useRef } from 'react'

import { useFlowStore } from '../store'

export function Toolbar({ onOpenPicker }: { onOpenPicker: () => void }) {
  const name = useFlowStore((s) => s.name)
  const version = useFlowStore((s) => s.version)
  const workflowId = useFlowStore((s) => s.workflowId)
  const dirty = useFlowStore((s) => s.dirty)
  const saving = useFlowStore((s) => s.saving)
  const setMeta = useFlowStore((s) => s.setMeta)
  const save = useFlowStore((s) => s.save)
  const newWorkflow = useFlowStore((s) => s.newWorkflow)
  const loadPreset = useFlowStore((s) => s.loadPreset)
  const exportJSON = useFlowStore((s) => s.exportJSON)
  const importJSON = useFlowStore((s) => s.importJSON)
  const undo = useFlowStore((s) => s.undo)
  const redo = useFlowStore((s) => s.redo)
  const duplicateSelected = useFlowStore((s) => s.duplicateSelected)
  const canUndo = useFlowStore((s) => s.past.length > 0)
  const canRedo = useFlowStore((s) => s.future.length > 0)
  const hasSelection = useFlowStore((s) => s.selectedNodeId !== null)
  const nodeCount = useFlowStore((s) => s.nodes.length)
  const edgeCount = useFlowStore((s) => s.edges.length)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleExport = () => {
    const blob = new Blob([exportJSON()], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${(name || 'workflow').replace(/[\\/:*?"<>|]/g, '_')}.json`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const handleImport = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => importJSON(String(reader.result))
    reader.readAsText(file)
    // 清空 value，否则连续导入同一个文件不会再触发 change
    event.target.value = ''
  }

  return (
    <header className="toolbar">
      <div className="toolbar-brand">AgentFlow</div>

      <input
        className="toolbar-name"
        value={name}
        onChange={(event) => setMeta({ name: event.target.value })}
      />

      <span className="toolbar-meta">
        {workflowId ? `v${version}` : '未保存'} · {nodeCount} 节点 / {edgeCount} 连线
        {dirty && <em className="toolbar-dirty"> · 有未保存修改</em>}
      </span>

      <div className="toolbar-actions">
        <button className="btn" onClick={undo} disabled={!canUndo} title="撤销 (Ctrl+Z)">
          撤销
        </button>
        <button className="btn" onClick={redo} disabled={!canRedo} title="重做 (Ctrl+Shift+Z)">
          重做
        </button>
        <button
          className="btn"
          onClick={duplicateSelected}
          disabled={!hasSelection}
          title="复制选中节点 (Ctrl+D)"
        >
          复制
        </button>
        <button className="btn" onClick={loadPreset} title="载入「智能出题→作业批改→学情分析」教学闭环示例">
          教学示例
        </button>
        <button className="btn" onClick={onOpenPicker}>
          打开
        </button>
        <button className="btn" onClick={handleExport} disabled={nodeCount === 0}>
          导出
        </button>
        <button className="btn" onClick={() => fileRef.current?.click()}>
          导入
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="application/json,.json"
          hidden
          onChange={handleImport}
        />
        <button className="btn" onClick={newWorkflow}>
          新建
        </button>
        <button className="btn-primary" disabled={saving} onClick={save}>
          {saving ? '保存中…' : '保存'}
        </button>
      </div>
    </header>
  )
}
