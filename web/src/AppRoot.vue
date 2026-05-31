<template>
  <router-view />
</template>

<script setup>
// App 根组件 — 直接渲染路由视图
// App.vue 自带顶部导航布局，不需要额外 Layout 包装
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
</style>
