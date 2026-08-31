import { ReactFlowProvider } from '@xyflow/react'
import { useEffect, useState } from 'react'

import { Canvas } from './components/Canvas'
import { ConfigPanel } from './components/ConfigPanel'
import { HistoryPanel } from './components/HistoryPanel'
import { NodePalette } from './components/NodePalette'
import { RunPanel } from './components/RunPanel'
import { Toolbar } from './components/Toolbar'
import { WorkflowPicker } from './components/WorkflowPicker'
import { useFlowStore } from './store'

type Tab = 'config' | 'run' | 'history'

export default function App() {
  const loadNodeTypes = useFlowStore((s) => s.loadNodeTypes)
  const error = useFlowStore((s) => s.error)
  const clearError = useFlowStore((s) => s.clearError)
  const selectedNodeId = useFlowStore((s) => s.selectedNodeId)
  const loadWorkflowList = useFlowStore((s) => s.loadWorkflowList)
  const [tab, setTab] = useState<Tab>('config')
  const [pickerOpen, setPickerOpen] = useState(false)

  useEffect(() => {
    void loadNodeTypes()
    void loadWorkflowList()
  }, [loadNodeTypes, loadWorkflowList])

  // 选中节点时自动切到配置页，省得用户手动点
  useEffect(() => {
    if (selectedNodeId) {
      setTab('config')
    }
  }, [selectedNodeId])

  // 跑完后自动切到运行页看结果
  const execution = useFlowStore((s) => s.execution)
  useEffect(() => {
    if (execution) {
      setTab('run')
    }
  }, [execution])

  // Ctrl+S / Cmd+S 保存
  const save = useFlowStore((s) => s.save)
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
        event.preventDefault()
        void save()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [save])

  // Ctrl+Z 撤销 / Ctrl+Shift+Z 或 Ctrl+Y 重做 / Ctrl+D 复制节点
  const undo = useFlowStore((s) => s.undo)
  const redo = useFlowStore((s) => s.redo)
  const duplicateSelected = useFlowStore((s) => s.duplicateSelected)
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      const typing =
        !!target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable)
      const mod = event.ctrlKey || event.metaKey
      const key = event.key.toLowerCase()
      if (!mod) return
      if (key === 'z') {
        // 在输入框里把文本撤销交给浏览器，不抢快捷键
        if (typing) return
        event.preventDefault()
        if (event.shiftKey) redo()
        else undo()
      } else if (key === 'y') {
        if (typing) return
        event.preventDefault()
        redo()
      } else if (key === 'd') {
        // 复制节点，并拦掉浏览器「加入收藏夹」的默认行为
        if (typing) return
        event.preventDefault()
        duplicateSelected()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [undo, redo, duplicateSelected])

  return (
    <ReactFlowProvider>
      <div className="app">
        <Toolbar onOpenPicker={() => setPickerOpen(true)} />

        {error && (
          <div className="app-error" role="alert">
            <span>{error}</span>
            <button className="app-error-close" onClick={clearError}>
              ×
            </button>
          </div>
        )}

        <div className="app-body">
          <NodePalette />
          <Canvas />

          <aside className="side-panel">
            <div className="tabs">
              <button
                className={tab === 'config' ? 'tab is-active' : 'tab'}
                onClick={() => setTab('config')}
              >
                配置
              </button>
              <button
                className={tab === 'run' ? 'tab is-active' : 'tab'}
                onClick={() => setTab('run')}
              >
                运行
              </button>
              <button
                className={tab === 'history' ? 'tab is-active' : 'tab'}
                onClick={() => setTab('history')}
              >
                历史
              </button>
            </div>
            <div className="side-panel-body">
              {tab === 'config' && <ConfigPanel />}
              {tab === 'run' && <RunPanel />}
              {tab === 'history' && <HistoryPanel />}
            </div>
          </aside>
        </div>

        {pickerOpen && <WorkflowPicker onClose={() => setPickerOpen(false)} />}
      </div>
    </ReactFlowProvider>
  )
}
