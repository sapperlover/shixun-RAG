<script setup lang="ts">
import { ref, watch } from 'vue'

import { getEvidence } from '@/api/qa'
import type { EvidenceOut, QAResponse } from '@/types/qa'

const props = defineProps<{ citationId: string | null; response: QAResponse }>()
const emit = defineEmits<{ close: [] }>()

const evidence = ref<EvidenceOut | null>(null)
const loading = ref(false)

watch(
  () => props.citationId,
  async (id) => {
    evidence.value = null
    if (!id || !props.response.knowledge_batch) return
    loading.value = true
    // 必须按本次回答的 knowledge_batch 读回原文
    evidence.value = await getEvidence(id, props.response.knowledge_batch, props.response)
    loading.value = false
  },
)
</script>

<template>
  <el-drawer
    :model-value="!!citationId"
    :title="`原文 ${citationId ?? ''}`"
    size="420px"
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
            {{ evidence.verification_status }}
          </el-descriptions-item>
          <el-descriptions-item label="知识批次">{{
            evidence.knowledge_batch
          }}</el-descriptions-item>
        </el-descriptions>
        <blockquote class="text">{{ evidence.text }}</blockquote>
      </template>
      <el-empty v-else-if="!loading" description="未能读回原文" />
    </div>
  </el-drawer>
</template>

<style scoped>
.text {
  margin: 16px 0 0;
  padding: 12px;
  background: #f8fafc;
  border-left: 3px solid #2563eb;
  white-space: pre-wrap;
  line-height: 1.7;
}
</style>
