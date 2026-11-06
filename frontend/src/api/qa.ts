import errorMock from '@contracts/mocks/error.json'
import insufficientMock from '@contracts/mocks/insufficient.json'
import needsContextMock from '@contracts/mocks/needs_context.json'
import successMock from '@contracts/mocks/success.json'

import type { EvidenceOut, QARequest, QAResponse, QAStatus } from '@/types/qa'

import { http, roleHeaders } from './client'

export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

const MOCKS: Record<QAStatus, QAResponse> = {
  success: successMock as unknown as QAResponse,
  needs_context: needsContextMock as unknown as QAResponse,
  insufficient: insufficientMock as unknown as QAResponse,
  error: errorMock as unknown as QAResponse,
}

/**
 * 提问。forceStatus 仅用于开发联调：
 * - mock 模式：直接返回 contracts/mocks 中对应终态；
 * - 连后端：发送 X-Debug-Force-Status 头（后端仅在 APP_ENV=dev 时生效）。
 */
export async function ask(req: QARequest, forceStatus?: QAStatus | ''): Promise<QAResponse> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 600))
    return structuredClone(MOCKS[forceStatus || 'success'])
  }
  const headers = forceStatus ? { 'X-Debug-Force-Status': forceStatus } : undefined
  const { body } = await http<QAResponse>('POST', '/qa/ask', { body: req, headers })
  return body
}

export async function getEvidence(
  citationId: string,
  knowledgeBatch: string,
  fallback?: QAResponse,
): Promise<EvidenceOut | null> {
  if (USE_MOCK && fallback) {
    const c = fallback.citations.find((x) => x.citation_id === citationId)
    return c
      ? {
          ...c,
          knowledge_batch: knowledgeBatch,
          doc_title: c.doc_id,
          page_start: c.page,
          page_end: c.page,
          text: c.excerpt,
          verification_status: 'verified',
        }
      : null
  }
  const q = new URLSearchParams({ knowledge_batch: knowledgeBatch })
  const { status, body } = await http<EvidenceOut>(
    'GET',
    `/evidence/${encodeURIComponent(citationId)}?${q}`,
  )
  return status === 200 ? body : null
}

export async function sendFeedback(
  requestId: string,
  type: 'helpful' | 'wrong_answer' | 'citation_invalid' | 'unresolved',
): Promise<number> {
  const { status } = await http('POST', '/feedback', {
    body: { request_id: requestId, type },
    headers: roleHeaders(),
  })
  return status
}
