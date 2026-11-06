<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { getHealth, listPage } from '@/api/resources'

interface DocumentRow {
  doc_id: string
  doc_version: string
  title: string
  publish_state: string
  created_at: string
}

const docs = ref<DocumentRow[]>([])
const total = ref(0)
const message = ref('')
const health = ref<Record<string, unknown> | null>(null)

async function load() {
  const { status, body } = await listPage<DocumentRow>('/documents')
  if (status === 200) {
    docs.value = body.items
    total.value = body.total
    message.value = ''
  } else {
    message.value = status === 403 ? '需要知识管理员角色' : `加载失败（HTTP ${status}）`
  }
  health.value = (await getHealth()).body
}
onMounted(load)
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="head">
        <span>知识库文档（{{ total }}）</span>
        <!-- TODO(Data/BE, D2)：上传对话框，必填来源、授权依据、适用范围、版本说明 -->
        <el-button size="small" disabled>上传文档（D2）</el-button>
        <el-button size="small" @click="load">刷新</el-button>
      </div>
    </template>
    <el-alert v-if="message" :title="message" type="warning" :closable="false" />
    <el-table :data="docs" size="small" empty-text="暂无文档">
      <el-table-column prop="title" label="标题" />
      <el-table-column prop="doc_version" label="版本" width="120" />
      <el-table-column prop="publish_state" label="状态" width="100" />
      <el-table-column prop="created_at" label="创建时间" width="180" />
    </el-table>
  </el-card>

  <el-card shadow="never" header="服务状态" class="health">
    <pre>{{ JSON.stringify(health, null, 2) }}</pre>
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
