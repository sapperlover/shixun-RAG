/**
 * 问答交互状态。
 * 前端阶段 phase（idle → searching → generating → done）由前端管理；
 * 业务终态 status 只来自后端响应（V1.2 §4.4 状态分层）。
 */
import { reactive } from 'vue'

import { ask } from '@/api/qa'
import type { QARequest, QAResponse, QAStatus } from '@/types/qa'

export type Phase = 'idle' | 'searching' | 'generating' | 'done'

export const qaState = reactive({
  phase: 'idle' as Phase,
  request: null as QARequest | null,
  response: null as QAResponse | null,
  forceStatus: '' as QAStatus | '',
})

export async function submit(req: QARequest): Promise<void> {
  qaState.request = req
  qaState.response = null
  qaState.phase = 'searching'
  // 后端非流式，“生成中”为估计阶段：检索一段时间后切换显示
  const timer = setTimeout(() => {
    if (qaState.phase === 'searching') qaState.phase = 'generating'
  }, 1200)
  try {
    qaState.response = await ask(req, qaState.forceStatus)
  } catch {
    qaState.response = {
      request_id: '-',
      status: 'error',
      knowledge_batch: null,
      retrieval_mode: null,
      degraded_mode: false,
      degradation_reason: null,
      answer_mode: null,
      answer: null,
      claims: [],
      paths: [],
      citations: [],
      missing_fields: [],
      error: { code: 'NETWORK_ERROR', failed_hop: null, retryable: true },
    }
  } finally {
    clearTimeout(timer)
    qaState.phase = 'done'
  }
}
