import { useState } from 'react'

import { ExecutionResult } from './ExecutionResult'
import { useFlowStore } from '../store'

export function RunPanel() {
  const run = useFlowStore((s) => s.run)
  const running = useFlowStore((s) => s.running)
  const execution = useFlowStore((s) => s.execution)
  const setError = useFlowStore((s) => s.setError)
  const workflowId = useFlowStore((s) => s.workflowId)
  const [inputsText, setInputsText] = useState('{}')

  const handleRun = async () => {
    let parsed: Record<string, unknown> = {}
    if (inputsText.trim()) {
      try {
        parsed = JSON.parse(inputsText) as Record<string, unknown>
      } catch {
        setError('运行输入不是合法的 JSON')
        return
      }
    }
    await run(parsed)
  }

  return (
    <div className="run-panel">
      <div className="field">
        <label className="field-label">运行输入（JSON）</label>
        <textarea
          className="field-input field-textarea"
          rows={4}
          value={inputsText}
          placeholder='{"topic": "冒泡排序"}'
          onChange={(event) => setInputsText(event.target.value)}
        />
        <p className="field-hint">留空则使用开始节点里定义的默认输入</p>
      </div>

      <button className="btn-primary" disabled={running} onClick={handleRun}>
        {running ? '运行中…' : '运行工作流'}
      </button>

      {!workflowId && (
        <p className="panel-hint">先保存工作流，才能触发运行</p>
      )}

      {execution && <ExecutionResult execution={execution} />}
    </div>
  )
}
