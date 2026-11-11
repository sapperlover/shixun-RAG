/**
 * POST /qa/ask 契约的 TypeScript 版本（与 backend/app/schemas/qa.py、contracts/qa_ask.schema.json 一致）。
 * ★ 冻结契约：后端改契约时必须同步修改本文件。
 */

export type QAStatus = 'success' | 'needs_context' | 'insufficient' | 'error'
export type ScopeField = 'major_code' | 'entry_year' | 'program_variant'
export type NodeLabel =
  'College' | 'Professional' | 'ProgramPlan' | 'CourseCategory' | 'Course' | 'RuleClause'
export type RelationType = 'BELONGS_TO' | 'CONTAINS' | 'APPLIES_TO' | 'CITES' | 'PREREQUISITE_OF'

export interface Scope {
  major_code: string | null
  entry_year: number | null
  program_variant?: 'regular' | 'international' | 'second_degree' | 'joint' | null
  plan_revision?: string | null
  college?: string | null
}

export interface QARequest {
  question: string
  scope: Scope
  session_id?: string | null
}

export interface PathNode {
  node_id: string
  label: NodeLabel
  name: string
}

export interface PathEdge {
  relation_id: string
  type: RelationType
  from: string
  to: string
}

export interface Path {
  path_id: string
  hop_count: number
  nodes: PathNode[]
  edges: PathEdge[]
}

export interface Claim {
  claim_id: string
  text: string
  path_ids: string[]
  citation_ids: string[]
}

export interface Citation {
  citation_id: string
  relation_id: string | null
  chunk_id: string
  doc_id: string
  doc_version: string
  section: string | null
  page: number | null
  excerpt: string
  doc_title?: string | null
}

export interface ErrorInfo {
  code: string
  failed_hop: number | null
  retryable: boolean
}

export interface QAResponse {
  request_id: string
  status: QAStatus
  knowledge_batch: string | null
  retrieval_mode: 'hybrid' | 'graph_only' | 'keyword_only' | null
  retrieval_type?: 'graph' | 'document'
  warnings?: string[]
  resolved_scope?: Scope | null
  hop_log?: { hop: number; candidates_in: number; kept: number; pruned: Record<string, number> }[]
  degraded_mode: boolean
  degradation_reason: string | null
  answer_mode: 'llm' | 'template' | null
  answer: string | null
  claims: Claim[]
  paths: Path[]
  citations: Citation[]
  missing_fields: ScopeField[]
  error: ErrorInfo | null
}

export interface EvidenceOut {
  citation_id: string
  knowledge_batch: string
  relation_id: string | null
  chunk_id: string
  doc_id: string
  doc_title: string
  doc_version: string
  section: string | null
  page_start: number | null
  page_end: number | null
  text: string
  verification_status: string
}

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export const LABEL_ZH: Record<NodeLabel, string> = {
  College: '学院',
  Professional: '专业',
  ProgramPlan: '培养方案',
  CourseCategory: '课程类别',
  Course: '课程',
  RuleClause: '规则条款',
}

export const RELATION_ZH: Record<RelationType, string> = {
  BELONGS_TO: '所属',
  CONTAINS: '包含',
  APPLIES_TO: '适用',
  CITES: '引用',
  PREREQUISITE_OF: '先修',
}

/** 前端按错误码显示文案；未列出的码显示码本身 */
export const ERROR_ZH: Record<string, string> = {
  ANCHOR_NOT_FOUND: '问题中没有找到可匹配的专业、方案、课程或条款',
  PATH_INCOMPLETE: '关系链在中途断开，无法形成完整的证据路径',
  EVIDENCE_UNVERIFIED: '路径中有关系尚未经过原文核验',
  VERSION_CONFLICT: '不同版本的条款存在冲突',
  CITATION_INVALID: '生成的结论无法与原文引用一一对应',
  GRAPH_UNAVAILABLE: '图谱服务暂时不可用',
  METADATA_UNAVAILABLE: '元数据服务暂时不可用',
  NO_ACTIVE_BATCH: '知识库尚未发布',
  LLM_UNAVAILABLE: '生成模型暂时不可用',
  INTERNAL_ERROR: '服务内部错误',
  VALIDATION_ERROR: '请求格式不正确',
  NETWORK_ERROR: '无法连接服务器',
}
