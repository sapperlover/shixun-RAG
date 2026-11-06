<script setup lang="ts">
import { demoRole } from '@/api/client'
import { USE_MOCK } from '@/api/qa'

const isDev = import.meta.env.DEV
</script>

<template>
  <el-container class="layout">
    <el-header class="header">
      <span class="brand">校园知识问答</span>
      <el-menu mode="horizontal" router :default-active="$route.path" class="nav" :ellipsis="false">
        <el-menu-item index="/">问答</el-menu-item>
        <el-menu-item index="/knowledge">知识库</el-menu-item>
        <el-menu-item index="/eval">评测中心</el-menu-item>
      </el-menu>
      <div v-if="isDev" class="dev">
        <el-tag v-if="USE_MOCK" type="warning" size="small">Mock 模式</el-tag>
        <el-select v-model="demoRole.value" placeholder="联调角色" size="small" clearable>
          <el-option label="学生" value="student" />
          <el-option label="知识管理员" value="knowledge_admin" />
          <el-option label="系统管理员" value="system_admin" />
        </el-select>
      </div>
    </el-header>
    <el-main class="main">
      <router-view />
    </el-main>
  </el-container>
</template>

<style>
body {
  margin: 0;
  background: #f6f7f9;
  font-family:
    system-ui,
    -apple-system,
    'PingFang SC',
    'Microsoft YaHei',
    sans-serif;
}
.layout {
  min-height: 100vh;
}
.header {
  display: flex;
  align-items: center;
  gap: 16px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
}
.brand {
  font-weight: 600;
  white-space: nowrap;
}
.nav {
  flex: 1;
  border-bottom: none !important;
}
.dev {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 220px;
}
.main {
  max-width: 1080px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}
</style>
