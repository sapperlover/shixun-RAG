<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { http, roleHeaders } from '@/api/client'

interface Metrics {
  path_hit_rate: number | null
  answer_accuracy: number | null
  citation_coverage: number | null
  two_hop_path_hit_rate: number | null
  three_hop_path_hit_rate: number | null
  api_answer_rate: number | null
  average_latency_ms: number | null
  p95_latency_ms: number | null
  failure_distribution: Record<string, number>
}
interface Run {
  run_id: string
  status: string
  metrics: Metrics | null
  created_at: string
  error_detail: string | null
}
interface Result {
  question_id: string
  question: string
  answer: string | null
  status: string
  path_hit: boolean
  answer_correct: boolean
  failure_stage: string | null
  elapsed_ms: number
  answer_mode: string | null
}
const runs = ref<Run[]>([])
const selected = ref<Run | null>(null)
const records = ref<Result[]>([])
const dataset = ref({
  sha256: '',
  questions: 0,
  two_hop: 0,
  three_hop: 0,
  ready_to_run: false,
  setup_message: '',
})
const busy = ref(false)
const message = ref('')
const statusNames: Record<string, string> = {
  running: '进行中',
  finished: '已完成',
  failed: '失败',
}
let timer: ReturnType<typeof setInterval> | undefined
const failureNames: Record<string, string> = {
  first_hop_miss: '首跳未召回',
  later_hop_missing: '后续关系缺失',
  version_conflict: '版本冲突',
  citation_missing: '引用无效',
  model_misuse: '答案或路径未命中',
}
function pct(n: number | null | undefined) {
  return n == null ? '—' : `${(n * 100).toFixed(1)}%`
}
async function select(run: Run) {
  selected.value = run
  const result = await http<{ items: Result[] }>('GET', `/evaluations/${run.run_id}/results`)
  if (result.status === 200) records.value = result.body.items
}
async function load() {
  try {
    const response = await http<{ items: Run[] }>('GET', '/evaluations')
    if (response.status !== 200) {
      message.value = '评测记录读取失败'
      return
    }
    runs.value = response.body.items
    busy.value = runs.value.some((r) => r.status === 'running')
    const current = runs.value.find((r) => r.run_id === selected.value?.run_id) ?? runs.value[0]
    if (current) await select(current)
  } catch {
    message.value = '无法连接评测服务'
  }
}
async function start() {
  busy.value = true
  try {
    const response = await http<Run>('POST', '/evaluations/run', {
      body: { dataset_sha256: dataset.value.sha256 },
      headers: roleHeaders(),
    })
    if (response.status === 202) {
      selected.value = response.body
      ElMessage.success('评测已开始，将调用已配置的模型 API')
    } else if (response.status === 403) ElMessage.warning('需要管理员令牌，或在本机启用演示模式')
    else ElMessage.error('评测未启动，请检查服务状态或是否已有任务运行')
  } catch {
    ElMessage.error('无法连接评测服务，请检查服务状态')
  } finally {
    await load()
  }
}
onMounted(async () => {
  try {
    dataset.value = (await http<typeof dataset.value>('GET', '/evaluations/dataset')).body
  } catch {
    message.value = '评测题集暂不可用'
  }
  await load()
  timer = setInterval(() => {
    if (busy.value) void load()
  }, 5000)
})
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="evaluation">
    <div class="heading">
      <div>
        <h1>评测中心</h1>
        <p>
          {{ dataset.questions }}道多跳题 · 2跳 {{ dataset.two_hop }}道 · 3跳
          {{ dataset.three_hop }}道，另含边界负例
        </p>
      </div>
      <el-button
        type="primary"
        :loading="busy"
        :disabled="!dataset.sha256 || !dataset.ready_to_run"
        @click="start"
        >{{ busy ? '评测进行中' : '运行评测' }}</el-button
      >
    </div>
    <el-alert
      title="答案评分为基于原文要点的自动初判，需结合逐题原文复核。题集为开发验证集。"
      type="info"
      :closable="false"
    />
    <el-alert
      v-if="message || dataset.setup_message"
      :title="message || dataset.setup_message"
      type="warning"
      :closable="false"
    />
    <div v-if="selected?.metrics" class="metrics">
      <el-card shadow="never"
        ><small>路径命中率</small><b>{{ pct(selected.metrics.path_hit_rate) }}</b></el-card
      >
      <el-card shadow="never"
        ><small>答案要点命中率</small><b>{{ pct(selected.metrics.answer_accuracy) }}</b></el-card
      >
      <el-card shadow="never"
        ><small>引用覆盖率</small><b>{{ pct(selected.metrics.citation_coverage) }}</b></el-card
      >
      <el-card shadow="never"
        ><small>平均耗时</small
        ><b>{{ selected.metrics.average_latency_ms?.toFixed(0) }}<small> ms</small></b></el-card
      >
    </div>
    <el-card shadow="never" header="运行记录">
      <el-table
        :data="runs"
        highlight-current-row
        empty-text="暂无记录，点击运行评测开始"
        @row-click="select"
      >
        <el-table-column prop="run_id" label="运行编号" />
        <el-table-column label="状态" width="110"
          ><template #default="{ row }">{{
            statusNames[row.status] ?? row.status
          }}</template></el-table-column
        >
        <el-table-column label="2跳命中" width="105"
          ><template #default="{ row }">{{
            pct(row.metrics?.two_hop_path_hit_rate)
          }}</template></el-table-column
        >
        <el-table-column label="3跳命中" width="105"
          ><template #default="{ row }">{{
            pct(row.metrics?.three_hop_path_hit_rate)
          }}</template></el-table-column
        >
        <el-table-column prop="created_at" label="时间（UTC）" width="170" />
      </el-table>
    </el-card>
    <el-card v-if="selected" shadow="never">
      <template #header
        ><div class="heading">
          <b>逐题结果</b
          ><el-link
            v-if="selected.status === 'finished'"
            :href="`/api/evaluations/${selected.run_id}/report`"
            target="_blank"
            type="primary"
            >查看报告 ↗</el-link
          >
        </div></template
      >
      <el-alert v-if="selected.error_detail" :title="selected.error_detail" type="error" />
      <div v-if="selected.metrics" class="failures">
        <el-tag
          v-for="(count, stage) in selected.metrics.failure_distribution"
          :key="stage"
          type="warning"
          >{{ failureNames[stage] ?? stage }}：{{ count }}</el-tag
        ><span v-if="!Object.keys(selected.metrics.failure_distribution).length"
          >当前自动评分未发现失败项。</span
        ><span>API生成占比 {{ pct(selected.metrics.api_answer_rate) }}</span>
      </div>
      <el-table :data="records" size="small" empty-text="运行结束后显示结果">
        <el-table-column type="expand"
          ><template #default="{ row }"
            ><p class="result-answer">{{ row.answer ?? '未生成结论' }}</p></template
          ></el-table-column
        >
        <el-table-column prop="question" label="问题" min-width="280" />
        <el-table-column label="路径" width="70"
          ><template #default="{ row }">{{
            row.path_hit ? '命中' : '未命中'
          }}</template></el-table-column
        >
        <el-table-column label="答案" width="70"
          ><template #default="{ row }">{{
            row.answer_correct ? '通过' : '待复核'
          }}</template></el-table-column
        >
        <el-table-column label="生成" width="80"
          ><template #default="{ row }">{{
            row.answer_mode === 'llm'
              ? 'API'
              : row.answer_mode === 'template'
                ? '摘录降级'
                : '拒答/追问'
          }}</template></el-table-column
        >
        <el-table-column prop="elapsed_ms" label="耗时ms" width="90" />
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.evaluation {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
h1 {
  color: #193950;
  font-size: 26px;
  margin-bottom: 8px;
}
.heading p {
  color: #7b8a99;
  font-size: 13px;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}
.metrics small {
  color: #758699;
  font-size: 12px;
}
.metrics b {
  display: block;
  margin-top: 10px;
  font-size: 28px;
  color: #275779;
}
.failures {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 12px;
  color: #7b8999;
  margin-bottom: 16px;
}
.result-answer {
  padding: 12px 24px;
  white-space: pre-wrap;
  line-height: 1.8;
}
@media (max-width: 640px) {
  .metrics {
    grid-template-columns: 1fr 1fr;
  }
  .heading {
    align-items: start;
  }
}
</style>
