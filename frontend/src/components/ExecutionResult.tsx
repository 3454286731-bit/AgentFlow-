import type { ExecutionDetail } from '../types'

/**
 * 执行结果展示。运行面板和历史回放共用这一份，
 * 保证两处看到的字段、格式、状态配色完全一致。
 */
export function ExecutionResult({ execution }: { execution: ExecutionDetail }) {
  return (
    <div className="run-result">
      <div className="result-head">
        <span className={`badge badge-${execution.status}`}>{execution.status}</span>
        <span className="result-meta">{execution.duration_ms}ms</span>
        <span className="result-meta">{execution.node_results.length} 个节点</span>
      </div>

      {execution.error && <div className="result-error">{execution.error}</div>}

      <div className="result-section">
        <h4>最终输出</h4>
        <pre className="result-pre">{formatValue(execution.final_output)}</pre>
      </div>

      <div className="result-section">
        <h4>节点明细</h4>
        {execution.node_results.map((result) => (
          <div className={`result-node status-${result.status}`} key={result.node_id}>
            <div className="result-node-head">
              <span className="result-node-name">{result.node_id}</span>
              <span className="result-meta">
                {result.status} · {result.duration_ms}ms
              </span>
            </div>
            {result.error && <div className="result-error">{result.error}</div>}
            {result.status === 'success' && (
              <pre className="result-pre">{formatValue(result.output)}</pre>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '（无输出）'
  }
  if (typeof value === 'string') {
    return value
  }
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
