<script setup lang="ts">
import { USE_MOCK } from '@/api/qa'
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
      <el-tag v-if="USE_MOCK" type="warning" size="small">模拟演示</el-tag>
    </el-header>
    <el-main class="main">
      <router-view />
      <footer class="footer">校园知识问答 · 请以学校最新正式发布的文件为准</footer>
    </el-main>
  </el-container>
</template>

<style>
body {
  margin: 0;
  background: #f3f6f9;
  color: #243d53;
  --el-color-primary: #285e8c;
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
.main {
  max-width: 1080px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}
</style>

<style>
.footer {
  margin-top: 40px;
  padding: 20px 0;
  border-top: 1px solid #e0e7ee;
  text-align: center;
  font-size: 12px;
  color: #81909e;
}
.el-card {
  border-radius: 12px;
}
@media (max-width: 640px) {
  .header {
    padding: 0 12px;
    gap: 8px;
  }
  .main {
    padding: 16px;
  }
  .brand {
    font-size: 14px;
  }
  .el-menu--horizontal > .el-menu-item {
    padding: 0 12px;
  }
}
</style>
