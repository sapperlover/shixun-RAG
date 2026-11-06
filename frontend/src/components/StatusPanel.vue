<script setup lang="ts">
import { computed } from 'vue'

import type { Phase } from '@/stores/qa'
import { ERROR_ZH, type QAResponse } from '@/types/qa'

const props = defineProps<{ phase: Phase; response: QAResponse | null }>()

const FIELD_ZH: Record<string, string> = { major_code: '专业', entry_year: '入学年级' }
const errText = computed(() => {
  const e = props.response?.error
  return e ? (ERROR_ZH[e.code] ?? e.code) : ''
})
</script>

<template>
  <div>
    <el-alert v-if="phase === 'searching'" type="info" :closable="false" show-icon>
      正在检索图谱，逐跳扩展证据路径…
    </el-alert>
    <el-alert v-else-if="phase === 'generating'" type="info" :closable="false" show-icon>
      正在依据证据生成回答…
    </el-alert>

    <template v-else-if="phase === 'done' && response">
      <el-alert
        v-if="response.status === 'success' && response.degraded_mode"
        type="warning"
        :closable="false"
        show-icon
        :title="`降级运行：${response.degradation_reason}`"
        description="检索或生成使用了降级模式，结论仍有完整引用，但表达可能较生硬。"
      />
      <el-alert
        v-else-if="response.status === 'needs_context'"
        type="warning"
        :closable="false"
        show-icon
        :title="`请补充：${response.missing_fields.map((f) => FIELD_ZH[f] ?? f).join('、')}`"
        description="不同专业、年级适用的培养方案不同，补充后再提问。"
      />
      <el-alert
        v-else-if="response.status === 'insufficient'"
        type="warning"
        :closable="false"
        show-icon
        :title="`证据不足，不给出确定结论：${errText}`"
        :description="
          response.error?.failed_hop ? `在第 ${response.error.failed_hop} 跳断开。` : undefined
        "
      />
      <el-alert
        v-else-if="response.status === 'error'"
        type="error"
        :closable="false"
        show-icon
        :title="`服务错误：${errText}`"
        :description="`请求编号 ${response.request_id}${response.error?.retryable ? '，可稍后重试' : ''}`"
      />
    </template>
  </div>
</template>
