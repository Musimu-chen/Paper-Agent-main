<template>
  <div class="app-shell">
    <!-- 顶部导航 -->
    <header class="top-nav">
      <div class="nav-brand" @click="$router.push('/')">
        <span class="brand-icon">📄</span>
        <span class="brand-text">Paper Agent</span>
        <span class="brand-badge">AI 论文调研</span>
      </div>
      <nav class="nav-links">
        <router-link to="/" class="nav-link" :class="{ active: $route.path === '/' }">
          <span class="nav-icon">✨</span> 新建调研
        </router-link>
        <router-link to="/history" class="nav-link" :class="{ active: $route.path === '/history' }">
          <span class="nav-icon">📋</span> 历史报告
        </router-link>
        <router-link to="/knowledge" class="nav-link" :class="{ active: $route.path === '/knowledge' }">
          <span class="nav-icon">📚</span> 知识库
        </router-link>
      </nav>
    </header>

    <!-- 页面内容 -->
    <router-view />
  </div>
</template>

<script setup>
// 布局外壳：顶部导航 + 路由视图
</script>

<style>
/* ===== 全局重置 ===== */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: #f0f2f5;
  color: #1a1a2e;
  overflow: hidden;
  height: 100vh;
  -webkit-font-smoothing: antialiased;
}

#app {
  height: 100vh;
}

/* ===== 整体布局 ===== */
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

/* ===== 顶部导航 ===== */
.top-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 56px;
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  z-index: 100;
  flex-shrink: 0;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}

.brand-icon { font-size: 22px; }
.brand-text { font-size: 18px; font-weight: 700; color: #1a1a2e; }

.brand-badge {
  font-size: 11px;
  color: #666;
  background: #f0f0f0;
  padding: 2px 8px;
  border-radius: 10px;
}

.nav-links { display: flex; gap: 4px; }

.nav-link {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 16px;
  border-radius: 8px;
  text-decoration: none;
  font-size: 14px;
  color: #555;
  transition: all 0.2s;
  font-weight: 500;
}

.nav-link:hover { background: #f5f5f5; color: #1a1a2e; }
.nav-link.active, .nav-link.router-link-exact-active { background: #e8f4fd; color: #1a73e8; }

.nav-icon { font-size: 16px; }

@media (max-width: 768px) {
  .top-nav { padding: 0 12px; }
  .nav-link { padding: 6px 10px; font-size: 12px; }
  .brand-badge { display: none; }
}
</style>
