import { useEffect } from 'react'

import { useFlowStore } from '../store'

/** 已保存工作流的列表，点一条就加载进画布继续编辑 */
export function WorkflowPicker({ onClose }: { onClose: () => void }) {
  const workflowList = useFlowStore((s) => s.workflowList)
  const loadWorkflowList = useFlowStore((s) => s.loadWorkflowList)
  const loadingList = useFlowStore((s) => s.loadingList)
  const loadWorkflow = useFlowStore((s) => s.loadWorkflow)
  const currentId = useFlowStore((s) => s.workflowId)
  const deleteWorkflow = useFlowStore((s) => s.deleteWorkflow)

  useEffect(() => {
    void loadWorkflowList()
  }, [loadWorkflowList])

  const handleOpen = async (id: string) => {
    await loadWorkflow(id)
    onClose()
  }

  const handleDelete = async (id: string) => {
    await deleteWorkflow(id)
    await loadWorkflowList()
  }

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <span>打开工作流</span>
          <button className="app-error-close" onClick={onClose}>
            ×
          </button>
        </div>

        {loadingList && <div className="panel-empty">加载中…</div>}

        {!loadingList && workflowList.length === 0 && (
          <div className="panel-empty">
            <p>还没有保存过工作流</p>
            <p className="panel-empty-hint">在画布上编排后点保存</p>
          </div>
        )}

        <div className="modal-list">
          {workflowList.map((wf) => (
            <div
              key={wf.id}
              className={`modal-item ${wf.id === currentId ? 'is-current' : ''}`}
            >
              <button className="modal-item-main" onClick={() => void handleOpen(wf.id)}>
                <div className="modal-item-name">
                  {wf.name}
                  <span className="result-meta">v{wf.version}</span>
                </div>
                <div className="modal-item-meta">
                  {wf.node_count} 节点 / {wf.edge_count} 连线
                </div>
              </button>
              <button
                className="btn-mini"
                onClick={() => void handleDelete(wf.id)}
                title="删除这条工作流"
              >
                删除
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
