<script setup lang="ts">
import { computed, ref } from 'vue'

import EvidenceDrawer from '@/components/EvidenceDrawer.vue'
import FeedbackBar from '@/components/FeedbackBar.vue'
import PathGraph from '@/components/PathGraph.vue'
import StatusPanel from '@/components/StatusPanel.vue'
import { qaState } from '@/stores/qa'

const resp = computed(() => qaState.response)
const openCitation = ref<string | null>(null)
function number(id: string) {
  return (resp.value?.citations.findIndex((c) => c.citation_id === id) ?? -1) + 1
}
</script>

<template>
  <div class="answer">
    <el-page-header title="继续提问" @back="$router.push('/')">
      <template #content
        ><span class="question">{{ qaState.request?.question ?? '尚未提问' }}</span></template
      >
    </el-page-header>
    <StatusPanel :phase="qaState.phase" :response="resp" />
    <template v-if="resp?.status === 'success'">
      <el-card shadow="never">
        <template #header>
          <div class="answer-head">
            <b>回答</b>
            <el-tag :type="resp.retrieval_type === 'document' ? 'info' : 'success'" effect="plain">
              {{ resp.retrieval_type === 'document' ? '原文检索' : '多跳图谱推理' }}
            </el-tag>
            <span v-if="resp.resolved_scope?.major_code" class="scope"
              >{{ resp.resolved_scope.major_code }} · {{ resp.resolved_scope.entry_year }}级</span
            >
          </div>
        </template>
        <p v-for="claim in resp.claims" :key="claim.claim_id" class="claim">
          {{ claim.text }}
          <el-link
            v-for="id in claim.citation_ids"
            :key="id"
            type="primary"
            class="cite"
            @click="openCitation = id"
            >[{{ number(id) }}]</el-link
          >
        </p>
        <el-alert
          v-if="resp.retrieval_type === 'document'"
          title="当前依据为相关原文，未形成多跳关系路径；制度对特定年级的适用性请以教务确认为准。"
          type="info"
          :closable="false"
        />
      </el-card>
    </template>
    <el-button v-if="resp?.status === 'needs_context'" type="primary" @click="$router.push('/')"
      >补充条件，继续提问</el-button
    >
    <el-card v-if="resp?.paths.length" shadow="never" header="证据路径">
      <div class="path-count">
        <el-tag v-for="path in resp.paths" :key="path.path_id" effect="plain"
          >{{ path.hop_count }}跳 · {{ path.nodes[0]?.name }} →
          {{ path.nodes[path.nodes.length - 1]?.name }}</el-tag
        >
      </div>
      <PathGraph :paths="resp.paths" />
      <el-collapse v-if="resp.hop_log?.length">
        <el-collapse-item title="展开逐跳检索记录" name="hops">
          <el-table :data="resp.hop_log" size="small">
            <el-table-column prop="hop" label="跳次" />
            <el-table-column prop="candidates_in" label="候选关系" />
            <el-table-column prop="kept" label="保留路径" />
            <el-table-column label="剪枝原因"
              ><template #default="{ row }">{{
                Object.entries(row.pruned)
                  .map(([k, v]) => `${k}: ${v}`)
                  .join('，') || '无'
              }}</template></el-table-column
            >
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </el-card>
    <el-card v-if="resp?.citations.length" shadow="never" header="引用来源">
      <el-table :data="resp.citations" size="small">
        <el-table-column label="引用" width="70"
          ><template #default="{ row }">[{{ number(row.citation_id) }}]</template></el-table-column
        >
        <el-table-column label="文档"
          ><template #default="{ row }">{{
            row.doc_title ?? row.doc_id
          }}</template></el-table-column
        >
        <el-table-column prop="section" label="章节" />
        <el-table-column prop="page" label="页码" width="70" />
        <el-table-column width="100"
          ><template #default="{ row }"
            ><el-link type="primary" @click="openCitation = row.citation_id"
              >核对原文</el-link
            ></template
          ></el-table-column
        >
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
  gap: 20px;
  padding-top: 20px;
}
.question {
  font-size: 16px;
  line-height: 1.7;
}
.answer-head {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}
.scope {
  color: #738294;
  font-size: 12px;
}
.claim {
  white-space: pre-wrap;
  line-height: 1.95;
  color: #243d53;
}
.cite {
  margin-left: 6px;
  vertical-align: baseline;
}
.path-count {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
