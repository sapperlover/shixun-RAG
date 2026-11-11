<script setup lang="ts">
import { ElMessage } from 'element-plus'

import { sendFeedback } from '@/api/qa'

const props = defineProps<{ requestId: string }>()

const TYPES = [
  { type: 'helpful', label: '有帮助' },
  { type: 'wrong_answer', label: '答案错误' },
  { type: 'citation_invalid', label: '引用失效' },
  { type: 'unresolved', label: '未解决' },
] as const

async function send(type: (typeof TYPES)[number]['type']) {
  const status = await sendFeedback(props.requestId, type).catch(() => 0)
  if (status === 201) ElMessage.success('已收到反馈')
  else ElMessage.error('反馈提交失败')
}
</script>

<template>
  <div class="feedback">
    <span>这个回答：</span>
    <el-button v-for="t in TYPES" :key="t.type" size="small" @click="send(t.type)">
      {{ t.label }}
    </el-button>
    <span class="rid">请求编号 {{ requestId }}</span>
  </div>
</template>

<style scoped>
.feedback {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.rid {
  margin-left: auto;
  color: #9ca3af;
  font-size: 12px;
}
</style>
