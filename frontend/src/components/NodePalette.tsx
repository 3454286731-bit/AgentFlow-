import { DRAG_MIME } from './Canvas'
import { useFlowStore } from '../store'
import type { NodeType } from '../types'

const PALETTE: Array<{ type: NodeType; label: string; desc: string }> = [
  { type: 'start', label: '开始', desc: '定义工作流输入变量' },
  { type: 'llm', label: '模型调用', desc: '调用大模型生成内容' },
  { type: 'http', label: 'HTTP 请求', desc: '调用外部接口取数据' },
  { type: 'condition', label: '条件分支', desc: '按表达式判断走哪条路' },
  { type: 'end', label: '结束', desc: '定义最终输出' },
  { type: 'question', label: '智能出题', desc: '按知识点批量生成题目' },
  { type: 'grading', label: '作业批改', desc: '按评分细则打分给旁批' },
  { type: 'analytics', label: '学情分析', desc: '提炼薄弱点与掌握度' },
]

export function NodePalette() {
  const addNode = useFlowStore((s) => s.addNode)

  return (
    <aside className="palette">
      <h2 className="panel-title">节点</h2>
      {PALETTE.map((item) => (
        <div
          key={item.type}
          className="palette-item"
          draggable
          onDragStart={(event) => {
            event.dataTransfer.setData(DRAG_MIME, item.type)
            event.dataTransfer.effectAllowed = 'move'
          }}
          onDoubleClick={() =>
            addNode(item.type, { x: 120 + Math.random() * 80, y: 80 + Math.random() * 80 })
          }
        >
          <span className={`palette-dot dot-${item.type}`} />
          <div>
            <div className="palette-label">{item.label}</div>
            <div className="palette-desc">{item.desc}</div>
          </div>
        </div>
      ))}
      <p className="palette-hint">拖到画布，或双击直接添加</p>
    </aside>
  )
}
