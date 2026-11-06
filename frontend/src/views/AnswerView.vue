<script setup lang="ts">
import { computed, ref } from 'vue'

import EvidenceDrawer from '@/components/EvidenceDrawer.vue'
import FeedbackBar from '@/components/FeedbackBar.vue'
import PathGraph from '@/components/PathGraph.vue'
import StatusPanel from '@/components/StatusPanel.vue'
import { qaState } from '@/stores/qa'

const resp = computed(() => qaState.response)
const openCitation = ref<string | null>(null)
</script>

<template>
  <div class="answer">
    <el-page-header title="返回" @back="$router.push('/')">
      <template #content>{{ qaState.request?.question ?? '尚未提问' }}</template>
    </el-page-header>

    <StatusPanel :phase="qaState.phase" :response="resp" />

    <template v-if="resp && resp.status === 'success'">
      <el-card shadow="never" header="回答">
        <p class="answer-text">{{ resp.answer }}</p>
        <ul class="claims">
          <li v-for="c in resp.claims" :key="c.claim_id">
            {{ c.text }}
            <el-link
              v-for="cid in c.citation_ids"
              :key="cid"
              type="primary"
              class="cite"
              @click="openCitation = cid"
            >
              [{{ cid }}]
            </el-link>
          </li>
        </ul>
      </el-card>
    </template>

    <el-card v-if="resp && resp.paths.length" shadow="never" header="证据路径">
      <!-- 只根据 paths 渲染，不从 answer 文本推断关系（V1.2 附录 C.2） -->
      <PathGraph :paths="resp.paths" />
    </el-card>

    <el-card v-if="resp && resp.citations.length" shadow="never" header="引用来源">
      <el-table :data="resp.citations" size="small">
        <el-table-column prop="citation_id" label="编号" width="80" />
        <el-table-column prop="doc_id" label="文档" />
        <el-table-column prop="doc_version" label="版本" width="110" />
        <el-table-column prop="section" label="章节" />
        <el-table-column prop="page" label="页码" width="70" />
        <el-table-column label="" width="90">
          <template #default="{ row }">
            <el-link type="primary" @click="openCitation = row.citation_id">看原文</el-link>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <FeedbackBar v-if="resp && resp.status !== 'error'" :request-id="resp.request_id" />

    <EvidenceDrawer
      v-if="resp"
      :citation-id="openCitation"
      :response="resp"
      @close="openCitation = null"
    />
  </div>
</template>

<style scoped>
.answer {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.answer-text {
  white-space: pre-wrap;
  line-height: 1.7;
}
.claims {
  padding-left: 20px;
  color: #4b5563;
}
.cite {
  margin-left: 4px;
}
</style>
