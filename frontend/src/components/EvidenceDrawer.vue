<script setup lang="ts">
import { ref, watch } from 'vue'

import { getEvidence } from '@/api/qa'
import type { EvidenceOut, QAResponse } from '@/types/qa'

const props = defineProps<{ citationId: string | null; response: QAResponse }>()
const emit = defineEmits<{ close: [] }>()

const evidence = ref<EvidenceOut | null>(null)
const loading = ref(false)
const labels: Record<string, string> = {
  verified: '已核验关系证据',
  ai_source_reviewed: 'AI 对照原文核验',
  source_text_extracted: '原生文本提取',
}
function originalUrl() {
  if (!evidence.value) return '#'
  const query = new URLSearchParams({
    knowledge_batch: evidence.value.knowledge_batch,
    doc_version: evidence.value.doc_version,
  })
  return `/api/documents/${encodeURIComponent(evidence.value.doc_id)}/source?${query}#page=${evidence.value.page_start ?? 1}`
}

watch(
  () => props.citationId,
  async (id) => {
    evidence.value = null
    if (!id || !props.response.knowledge_batch) return
    loading.value = true
    // 必须按本次回答的 knowledge_batch 读回原文
    try {
      const result = await getEvidence(id, props.response.knowledge_batch, props.response)
      if (props.citationId === id) evidence.value = result
    } catch {
      if (props.citationId === id) evidence.value = null
    } finally {
      if (props.citationId === id) loading.value = false
    }
  },
)
</script>

<template>
  <el-drawer
    :model-value="!!citationId"
    :title="`原文 ${citationId ?? ''}`"
    size="min(560px, 95vw)"
    @close="emit('close')"
  >
    <div v-loading="loading">
      <template v-if="evidence">
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="文档">{{ evidence.doc_title }}</el-descriptions-item>
          <el-descriptions-item label="版本">{{ evidence.doc_version }}</el-descriptions-item>
          <el-descriptions-item label="章节">{{ evidence.section ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="页码">{{ evidence.page_start ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="核验">
            {{ labels[evidence.verification_status] ?? evidence.verification_status }}
          </el-descriptions-item>
          <el-descriptions-item label="知识批次">{{
            evidence.knowledge_batch
          }}</el-descriptions-item>
        </el-descriptions>
        <el-link
          :href="originalUrl()"
          target="_blank"
          rel="noopener"
          type="primary"
          class="original"
          >打开原始 PDF ↗</el-link
        >
        <blockquote class="text">{{ evidence.text }}</blockquote>
      </template>
      <el-empty v-else-if="!loading" description="未能读回原文" />
    </div>
  </el-drawer>
</template>

<style scoped>
.original {
  margin-top: 18px;
}
.text {
  margin: 16px 0 0;
  padding: 12px;
  background: #f8fafc;
  border-left: 3px solid #2563eb;
  white-space: pre-wrap;
  line-height: 1.7;
}
</style>
