import { createRouter, createWebHistory } from 'vue-router'

import AnswerView from '@/views/AnswerView.vue'
import EvalView from '@/views/EvalView.vue'
import HomeView from '@/views/HomeView.vue'
import KnowledgeView from '@/views/KnowledgeView.vue'

// 四个页面对应 PRD：校园问答首页 / 问答结果页 / 知识库管理页 / 评测中心页
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView, meta: { title: '问答' } },
    { path: '/answer', name: 'answer', component: AnswerView, meta: { title: '问答结果' } },
    { path: '/knowledge', name: 'knowledge', component: KnowledgeView, meta: { title: '知识库' } },
    { path: '/eval', name: 'eval', component: EvalView, meta: { title: '评测中心' } },
  ],
})
