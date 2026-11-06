<script setup lang="ts">
import { reactive } from 'vue'
import { useRouter } from 'vue-router'

import { qaState, submit } from '@/stores/qa'
import type { QAStatus } from '@/types/qa'

const router = useRouter()
const isDev = import.meta.env.DEV
const statuses: QAStatus[] = ['success', 'needs_context', 'insufficient', 'error']

const form = reactive({
  question: qaState.request?.question ?? '',
  major_code: qaState.request?.scope.major_code ?? '',
  entry_year: qaState.request?.scope.entry_year ?? (null as number | null),
})

async function onSubmit() {
  if (!form.question.trim()) return
  router.push('/answer')
  await submit({
    question: form.question.trim(),
    scope: { major_code: form.major_code || null, entry_year: form.entry_year || null },
  })
}
</script>

<template>
  <el-card shadow="never">
    <template #header>多跳问答：培养方案与学籍规则</template>
    <el-form label-position="top" @submit.prevent="onSubmit">
      <el-form-item label="问题">
        <el-input
          v-model="form.question"
          type="textarea"
          :rows="3"
          maxlength="500"
          show-word-limit
          placeholder="例如：某专业某级的专业选修课，跨院系课程如何认定？"
        />
      </el-form-item>
      <div class="scope">
        <el-form-item label="专业代码">
          <!-- TODO(FE, D4)：改为从后端获取的专业下拉 -->
          <el-input v-model="form.major_code" placeholder="如 DEMO01" />
        </el-form-item>
        <el-form-item label="入学年级">
          <el-input-number v-model="form.entry_year" :min="2000" :max="2100" :controls="false" />
        </el-form-item>
        <el-form-item v-if="isDev" label="联调：强制终态">
          <el-select v-model="qaState.forceStatus" clearable placeholder="走真实流程">
            <el-option v-for="s in statuses" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
      </div>
      <el-button type="primary" native-type="submit" :disabled="!form.question.trim()">
        提问
      </el-button>
    </el-form>
  </el-card>
</template>

<style scoped>
.scope {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}
</style>
