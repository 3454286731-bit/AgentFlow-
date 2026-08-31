import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  useReactFlow,
} from '@xyflow/react'
import type { Connection } from '@xyflow/react'
import { useCallback } from 'react'

import { nodeTypes } from '../nodes/WorkflowNodeCard'
import { useFlowStore } from '../store'
import type { NodeType } from '../types'

export const DRAG_MIME = 'application/agentflow-node'

export function Canvas() {
  const nodes = useFlowStore((s) => s.nodes)
  const edges = useFlowStore((s) => s.edges)
  const onNodesChange = useFlowStore((s) => s.onNodesChange)
  const onEdgesChange = useFlowStore((s) => s.onEdgesChange)
  const connect = useFlowStore((s) => s.onConnect)
  const addNode = useFlowStore((s) => s.addNode)
  const selectNode = useFlowStore((s) => s.selectNode)
  const setError = useFlowStore((s) => s.setError)
  const takeSnapshot = useFlowStore((s) => s.takeSnapshot)

  const { screenToFlowPosition } = useReactFlow()

  const onConnect = useCallback(
    (connection: Connection) => {
      // 后端也会校验，这里提前拦一下，避免用户连完才发现保存失败
      const source = nodes.find((n) => n.id === connection.source)
      const target = nodes.find((n) => n.id === connection.target)
      if (target?.data.nodeType === 'start') {
        setError('开始节点不能有入边')
        return
      }
      if (source?.data.nodeType === 'end') {
        setError('结束节点不能有出边')
        return
      }
      connect(connection)
    },
    [connect, nodes, setError],
  )

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()
      const type = event.dataTransfer.getData(DRAG_MIME) as NodeType
      if (!type) return
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })
      addNode(type, position)
    },
    [addNode, screenToFlowPosition],
  )

  // 拖动开始时记一次快照：整段拖动只算一步撤销，不会每像素存一帧
  const onNodeDragStart = useCallback(() => {
    takeSnapshot()
  }, [takeSnapshot])

  // 条件分支的边显示出口名，方便一眼看清走的是哪条路
  const displayEdges = edges.map((edge) => ({
    ...edge,
    label: edge.sourceHandle ?? undefined,
  }))

  return (
    <div className="canvas" onDrop={onDrop} onDragOver={onDragOver}>
      <ReactFlow
        nodes={nodes}
        edges={displayEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeDragStart={onNodeDragStart}
        onNodeClick={(_, node) => selectNode(node.id)}
        onPaneClick={() => selectNode(null)}
        // 默认只认 Backspace，台式机上按 Delete 删不掉节点，这里两个都放行
        deleteKeyCode={['Delete', 'Backspace']}
        fitView
        minZoom={0.2}
        maxZoom={2}
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
        <Controls />
        <MiniMap pannable zoomable />
      </ReactFlow>

      {nodes.length === 0 && (
        <div className="canvas-empty">
          从左侧拖一个节点进来开始编排
        </div>
      )}
    </div>
  )
}
