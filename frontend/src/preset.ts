import type { Workflow } from './types'

/**
 * 预置的「教学闭环」示例工作流，用于一键演示本系统的教学场景差异化能力。
 *
 * 流程：开始（定义学生作答） → 智能出题 → 作业批改 → 学情分析 → 结束
 * 用户在工具栏点「教学示例」即可载入，保存后即可运行（mock 模式下也能跑通）。
 */
export const TEACHING_LOOP: Workflow = {
  id: '',
  name: '教学闭环示例',
  description: '智能出题 → 作业批改 → 学情分析 一条龙，演示教学场景专用节点',
  version: 1,
  nodes: [
    {
      id: 'start_1',
      type: 'start',
      name: '开始',
      config: { inputs: { student_answer: '光合作用靠叶绿素吸收光能，将二氧化碳和水合成有机物' } },
      position: { x: 80, y: 160 },
    },
    {
      id: 'q_1',
      type: 'question',
      name: '智能出题',
      config: {
        model: 'gpt-4o-mini',
        knowledge_point: '光合作用',
        difficulty: 'medium',
        question_type: 'choice',
        count: 2,
        requirements: '结合生活实例',
        temperature: 0.7,
      },
      position: { x: 340, y: 160 },
    },
    {
      id: 'g_1',
      type: 'grading',
      name: '作业批改',
      config: {
        model: 'gpt-4o-mini',
        answer: '{{student_answer}}',
        rubric: '概念准确 40 分，步骤完整 60 分',
        reference: '',
        max_score: 100,
        temperature: 0.2,
      },
      position: { x: 600, y: 160 },
    },
    {
      id: 'a_1',
      type: 'analytics',
      name: '学情分析',
      config: {
        model: 'gpt-4o-mini',
        records: '[{"kp":"光合作用","score":72},{"kp":"呼吸作用","score":58},{"kp":"蒸腾作用","score":85}]',
        dimension: 'knowledge',
        top_n: 3,
        temperature: 0.3,
      },
      position: { x: 860, y: 160 },
    },
    {
      id: 'end_1',
      type: 'end',
      name: '结束',
      config: { output_template: '批改得分 {{g_1.score}}；薄弱点分析：{{a_1.output}}' },
      position: { x: 1120, y: 160 },
    },
  ],
  edges: [
    { source: 'start_1', target: 'q_1' },
    { source: 'q_1', target: 'g_1' },
    { source: 'g_1', target: 'a_1' },
    { source: 'a_1', target: 'end_1' },
  ],
}
