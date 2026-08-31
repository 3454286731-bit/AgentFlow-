import { useEffect } from 'react'

import { ExecutionResult } from './ExecutionResult'
import { useFlowStore } from '../store'

const STATUS_TEXT: Record<string, string> = {
  success: '成功',
  failed: '失败',
  running: '执行中',
}

export function HistoryPanel() {
  const executions = useFlowStore((s) => s.executions)
  const loadExecutions = useFlowStore((s) => s.loadExecutions)
  const historyDetail = useFlowStore((s) => s.historyDetail)
  const loadExecutionDetail = useFlowStore((s) => s.loadExecutionDetail)
  const clearHistoryDetail = useFlowStore((s) => s.clearHistoryDetail)
  const workflowId = useFlowStore((s) => s.workflowId)

  // 切换工作流或刚跑完时刷新列表
  useEffect(() => {
    void loadExecutions(workflowId ?? undefined)
  }, [loadExecutions, workflowId])

  return (
    <div className="history-panel">
      {historyDetail ? (
        <>
          <button className="btn-mini" onClick={clearHistoryDetail}>
            ← 返回列表
          </button>
          <div className="history-detail-head">
            {historyDetail.workflow_name || historyDetail.workflow_id}
            <span className="result-meta">{formatTime(historyDetail.started_at)}</span>
          </div>
          <ExecutionResult execution={historyDetail} />
        </>
      ) : (
        <>
          <div className="history-head">
            <span className="field-label">
              {workflowId ? '当前工作流的执行记录' : '全部执行记录'}
            </span>
            <button
              className="btn-mini"
              onClick={() => void loadExecutions(workflowId ?? undefined)}
            >
              刷新
            </button>
          </div>

          {executions.length === 0 ? (
            <div className="panel-empty">
              <p>还没有执行记录</p>
              <p className="panel-empty-hint">切到运行页跑一次就会出现在这里</p>
            </div>
          ) : (
            <div className="history-list">
              {executions.map((item) => (
                <button
                  key={item.id}
                  className="history-item"
                  onClick={() => void loadExecutionDetail(item.id)}
                >
                  <div className="history-item-head">
                    <span className={`badge badge-${item.status}`}>
                      {STATUS_TEXT[item.status] ?? item.status}
                    </span>
                    <span className="result-meta">{item.duration_ms}ms</span>
                  </div>
                  <div className="history-item-name">
                    {item.workflow_name || item.workflow_id}
                  </div>
                  <div className="history-item-time">{formatTime(item.started_at)}</div>
                  {item.error && <div className="history-item-error">{item.error}</div>}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function formatTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return iso
  }
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}
