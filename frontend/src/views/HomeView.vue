<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { http } from '@/api/client'
import { qaState, submit } from '@/stores/qa'

interface Program {
  major: string
  entry_year: number | null
  program_variant: string
  plan_revision: string | null
}
const router = useRouter()
const programs = ref<Program[]>([])
const summary = ref({ documents: 0, searchable_chunks: 0, graph_edges: 0 })
const notice = ref('')
const form = reactive({
  question: qaState.request?.question ?? '',
  major_code: qaState.request?.scope.major_code ?? '计算机科学与技术',
  entry_year: qaState.request?.scope.entry_year ?? 2024,
  program_variant: qaState.request?.scope.program_variant ?? 'regular',
})
const majors = computed(() => [...new Set(programs.value.map((p) => p.major))])
const years = computed(() =>
  [
    ...new Set(
      programs.value
        .filter((p) => p.major === form.major_code && p.program_variant === form.program_variant)
        .map((p) => p.entry_year)
        .filter((y): y is number => y !== null),
    ),
  ].sort(),
)
const examples = [
  '2024级培养方案中，通识教育课程必修和最低选修学分分别是多少？',
  '计算机科学与技术专业2024级学生的专业课程最多可选修本院其他专业模块课程或本专业研究生课程多少学分？',
  '申请期末考试缓考需要什么手续？',
  '学位申请被拒绝可以申请复核吗？',
]
function useExample(question: string) {
  form.question = question
  form.major_code = '计算机科学与技术'
  form.entry_year = 2024
  form.program_variant = 'regular'
}
async function onSubmit() {
  if (!form.question.trim()) return
  router.push('/answer')
  await submit({
    question: form.question.trim(),
    scope: {
      major_code: form.major_code || null,
      entry_year: form.entry_year || null,
      program_variant: form.program_variant,
    },
  })
}
onMounted(async () => {
  try {
    const [catalog, stats] = await Promise.all([
      http<{ programs: Program[] }>('GET', '/qa/scopes'),
      http<typeof summary.value>('GET', '/documents/summary'),
    ])
    if (catalog.status === 200) programs.value = catalog.body.programs
    if (stats.status === 200) summary.value = stats.body
    if (!programs.value.length) notice.value = '知识库正在准备，请先完成初始化。'
  } catch {
    notice.value = '暂时无法获取知识库状态，请检查服务连接。'
  }
})
</script>

<template>
  <section class="hero">
    <div class="eyebrow">培养方案 · 学籍规则 · 证据溯源</div>
    <h1>校园里的问题，<br />沿着证据找到答案。</h1>
    <p>选择适用的专业与年级，了解课程学分、修读要求和办事规则。</p>
    <div class="stats">
      <span
        ><b>{{ summary.documents }}</b> 份来源文档</span
      >
      <span
        ><b>{{ summary.searchable_chunks }}</b> 条可检索原文</span
      >
      <span
        ><b>{{ summary.graph_edges }}</b> 条核验关系</span
      >
    </div>
  </section>
  <el-alert v-if="notice" :title="notice" type="warning" :closable="false" class="notice" />
  <el-card shadow="never" class="question-card">
    <el-form label-position="top" @submit.prevent="onSubmit">
      <el-form-item label="你想了解什么？">
        <el-input
          v-model="form.question"
          type="textarea"
          :rows="4"
          maxlength="500"
          show-word-limit
          placeholder="例如：通识教育课程必修和最低选修学分分别是多少？"
        />
      </el-form-item>
      <div class="scope">
        <el-form-item label="专业">
          <el-select v-model="form.major_code" filterable allow-create>
            <el-option
              v-for="major in majors.length ? majors : ['计算机科学与技术']"
              :key="major"
              :label="major"
              :value="major"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="入学年级">
          <el-select v-model="form.entry_year" clearable>
            <el-option
              v-for="year in years.length ? years : [2023, 2024, 2025]"
              :key="year"
              :label="`${year}级`"
              :value="year"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="培养类型">
          <el-select v-model="form.program_variant">
            <el-option label="普通本科" value="regular" />
            <el-option label="留学生" value="international" />
            <el-option label="第二学士学位" value="second_degree" />
            <el-option label="联合培养" value="joint" />
          </el-select>
        </el-form-item>
      </div>
      <div class="submit-row">
        <span>回答会附来源，支持展开核对原文与关系路径。</span>
        <el-button
          type="primary"
          size="large"
          native-type="submit"
          :disabled="!form.question.trim()"
          >查找答案 →</el-button
        >
      </div>
    </el-form>
  </el-card>
  <section class="examples">
    <h2>从这些问题开始</h2>
    <div class="example-grid">
      <button v-for="(question, i) in examples" :key="question" @click="useExample(question)">
        <span class="example-index">0{{ i + 1 }}</span
        ><span>{{ question }}</span
        ><span>↗</span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.hero {
  padding: 30px 0 28px;
}
.eyebrow {
  color: #526f8d;
  font-size: 13px;
  letter-spacing: 2px;
}
h1 {
  margin: 18px 0;
  font-size: clamp(30px, 4vw, 44px);
  line-height: 1.4;
  letter-spacing: -1px;
  color: #142d46;
}
.hero p {
  color: #66788a;
  line-height: 1.8;
}
.stats {
  display: flex;
  gap: 28px;
  margin-top: 24px;
  font-size: 13px;
  color: #6b7a88;
  flex-wrap: wrap;
}
.stats b {
  font-size: 22px;
  color: #234f78;
  margin-right: 5px;
}
.question-card {
  border-radius: 14px;
  border-color: #dce5ee;
}
.scope {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  gap: 16px;
}
.scope .el-select {
  width: 100%;
}
.submit-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.submit-row span {
  color: #738294;
  font-size: 12px;
}
.notice {
  margin-bottom: 16px;
}
.examples {
  margin: 30px 0;
}
h2 {
  font-size: 16px;
  color: #334d65;
  font-weight: 600;
}
.example-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.example-grid button {
  text-align: left;
  background: white;
  border: 1px solid #e1e7ee;
  border-radius: 10px;
  padding: 18px;
  display: flex;
  align-items: start;
  gap: 12px;
  color: #455a6e;
  line-height: 1.7;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
}
.example-grid button:hover {
  border-color: #9db6ce;
  background: #f7fafc;
}
.example-index {
  color: #8fa5b9;
  font-size: 12px;
}
@media (max-width: 640px) {
  .scope,
  .example-grid {
    grid-template-columns: 1fr;
  }
  .submit-row {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
