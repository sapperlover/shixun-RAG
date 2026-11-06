<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { listPage } from '@/api/resources'

interface RunRow {
  run_id: string
  status: string
  git_commit: string
  metrics: {
    path_hit_rate: number | null
    answer_accuracy: number | null
    citation_coverage: number | null
  } | null
  created_at: string
}

const runs = ref<RunRow[]>([])
const message = ref('')

function pct(x: number | null | undefined) {
  return x === null || x === undefined ? 'N/A' : `${(x * 100).toFixed(1)}%`
}

onMounted(async () => {
  const { status, body } = await listPage<RunRow>('/evaluations')
  if (status === 200) runs.value = body.items
  else message.value = status === 403 ? '需要系统管理员角色' : `加载失败（HTTP ${status}）`
})
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <!-- TODO(QA/BE, D5)：发起评测、逐题结果、失败分布图（ECharts）、报告导出 -->
      评测记录（当前请用 make eval 运行）
    </template>
    <el-alert v-if="message" :title="message" type="warning" :closable="false" />
    <el-table :data="runs" size="small" empty-text="暂无评测记录">
      <el-table-column prop="run_id" label="运行编号" />
      <el-table-column label="路径命中率" width="110">
        <template #default="{ row }">{{ pct(row.metrics?.path_hit_rate) }}</template>
      </el-table-column>
      <el-table-column label="答案正确率" width="110">
        <template #default="{ row }">{{ pct(row.metrics?.answer_accuracy) }}</template>
      </el-table-column>
      <el-table-column label="引用覆盖率" width="110">
        <template #default="{ row }">{{ pct(row.metrics?.citation_coverage) }}</template>
      </el-table-column>
      <el-table-column prop="git_commit" label="commit" width="100" />
    </el-table>
  </el-card>
</template>
