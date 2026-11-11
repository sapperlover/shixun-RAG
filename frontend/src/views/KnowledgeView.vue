<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { getHealth, listPage } from '@/api/resources'

interface DocumentRow {
  doc_id: string
  doc_version: string
  title: string
  publish_state: string
  created_at: string
  knowledge_batch?: string
}

const docs = ref<DocumentRow[]>([])
const total = ref(0)
const message = ref('')
const health = ref<Record<string, unknown> | null>(null)
const checks = ref<{ name: string; ok: boolean; detail: string }[]>([])
const serviceNames: Record<string, string> = {
  neo4j: '关系图谱',
  sqlite: '来源与日志',
  active_batch: '已发布知识图谱',
  generation_api: '答案生成 API',
  faiss: '实体向量索引',
  document_corpus: '全文来源库',
  document_vectors: '全文向量索引',
}

function sourceUrl(row: DocumentRow) {
  const query = new URLSearchParams({
    knowledge_batch: row.knowledge_batch ?? '',
    doc_version: row.doc_version,
  })
  return `/api/documents/${encodeURIComponent(row.doc_id)}/source?${query}`
}

async function load() {
  const { status, body } = await listPage<DocumentRow>('/documents')
  if (status === 200) {
    docs.value = body.items
    total.value = body.total
    message.value = ''
  } else {
    message.value = `加载失败（HTTP ${status}）`
  }
  health.value = (await getHealth()).body
  const states = health.value?.checks as Record<string, { ok: boolean; detail: string }> | undefined
  checks.value = Object.entries(states ?? {}).map(([key, value]) => ({
    name: serviceNames[key] ?? key,
    ok: value.ok,
    detail:
      key === 'generation_api'
        ? value.ok
          ? '已配置，问答时验证连通性'
          : '请填写模型 API 配置'
        : value.ok
          ? '可用'
          : '待初始化或暂不可用',
  }))
}
onMounted(load)
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="head">
        <span>知识库文档（{{ total }}）</span>
        <el-button size="small" @click="load">刷新</el-button>
      </div>
    </template>
    <el-alert v-if="message" :title="message" type="warning" :closable="false" />
    <el-table :data="docs" size="small" empty-text="暂无文档">
      <el-table-column prop="title" label="标题" />
      <el-table-column prop="doc_version" label="版本" width="120" />
      <el-table-column prop="publish_state" label="状态" width="100" />
      <el-table-column label="来源" width="100"
        ><template #default="{ row }"
          ><el-link v-if="row.knowledge_batch" :href="sourceUrl(row)" target="_blank" type="primary"
            >原始 PDF</el-link
          ></template
        ></el-table-column
      >
    </el-table>
  </el-card>

  <el-card shadow="never" header="服务状态" class="health">
    <el-alert
      v-if="health && !health.ready"
      title="知识库尚未就绪，请先完成初始化。"
      type="warning"
      :closable="false"
    />
    <el-table :data="checks" size="small">
      <el-table-column prop="name" label="服务" />
      <el-table-column label="状态"
        ><template #default="{ row }"
          ><el-tag :type="row.ok ? 'success' : 'warning'" effect="plain">{{
            row.detail
          }}</el-tag></template
        ></el-table-column
      >
    </el-table>
  </el-card>
</template>

<style scoped>
.head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.head span {
  flex: 1;
}
.health {
  margin-top: 16px;
}
.health pre {
  margin: 0;
  font-size: 12px;
  overflow-x: auto;
}
</style>
