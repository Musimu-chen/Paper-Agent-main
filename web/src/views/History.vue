<template>
  <div class="history-page">
    <div class="page-header">
      <h1>📋 历史报告</h1>
      <div class="header-actions">
        <button class="btn-primary" @click="$router.push('/')">
          ✨ 新建调研
        </button>
        <button class="btn-refresh" @click="loadHistory" :disabled="isLoading">
          🔄 刷新
        </button>
      </div>
    </div>

    <div class="loading-state" v-if="isLoading">
      <div class="spinner"></div>
      <p>加载历史报告...</p>
    </div>

    <div class="empty-state" v-else-if="historyList.length === 0">
      <div class="empty-icon">📋</div>
      <p>暂无历史报告</p>
      <button class="btn-primary" @click="$router.push('/')">创建第一个报告</button>
    </div>

    <div class="history-grid" v-else>
      <div
        v-for="item in historyList"
        :key="item.id"
        class="history-card"
      >
        <div class="card-header">
          <div class="report-title">
            <span class="title-icon">📄</span>
            <span class="title-text">{{ item.title || '未命名报告' }}</span>
          </div>
          <span class="status-badge" :class="item.status">
            {{ statusText(item.status) }}
          </span>
        </div>

        <div class="card-body">
          <div class="card-meta">
            <span class="meta-item">📅 {{ formatDate(item.createdAt) }}</span>
            <span class="meta-item">📝 {{ item.query.length > 60 ? item.query.slice(0, 60) + '...' : item.query }}</span>
          </div>
        </div>

        <div class="card-actions">
          <button class="btn-view" @click="viewReport(item)">👁️ 查看</button>
          <button class="btn-delete" @click="deleteReport(item)">🗑️ 删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const isLoading = ref(false)
const historyList = ref([])

const statusText = (status) => {
  return { completed: '已完成', processing: '处理中', failed: '失败' }[status] || '未知'
}

const formatDate = (dateStr) => {
  if (!dateStr) return '未知'
  return new Date(dateStr).toLocaleString('zh-CN')
}

const loadHistory = () => {
  isLoading.value = true
  try {
    const saved = localStorage.getItem('reportHistory')
    historyList.value = saved ? JSON.parse(saved) : []
  } catch (e) {
    console.error('加载历史失败:', e)
    historyList.value = []
  } finally {
    isLoading.value = false
  }
}

const viewReport = (item) => {
  router.push({ path: '/', query: { reportId: item.id } })
}

const deleteReport = (item) => {
  if (!confirm(`确定删除报告"${item.title}"？此操作不可恢复。`)) return
  historyList.value = historyList.value.filter(h => h.id !== item.id)
  localStorage.setItem('reportHistory', JSON.stringify(historyList.value))
}

onMounted(() => loadHistory())
</script>

<style scoped>
.history-page {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px;
  background: #f8f9fb;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 24px;
  font-weight: 700;
  color: #1a1a2e;
}

.header-actions { display: flex; gap: 8px; }

.btn-primary {
  padding: 10px 20px;
  background: #1a73e8;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary:hover { background: #1557b0; }

.btn-refresh {
  padding: 10px 16px;
  background: #fff;
  color: #555;
  border: 1px solid #ddd;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn-refresh:hover:not(:disabled) { background: #f5f5f5; }

.spinner {
  width: 32px; height: 32px;
  border: 3px solid #f0f0f0;
  border-top: 3px solid #1a73e8;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 12px;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.loading-state, .empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  color: #888;
  text-align: center;
}

.empty-icon { font-size: 48px; margin-bottom: 12px; }

.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.history-card {
  background: #fff;
  border-radius: 12px;
  padding: 18px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  border: 1px solid #eee;
  transition: all 0.2s;
}

.history-card:hover {
  box-shadow: 0 4px 16px rgba(0,0,0,0.08);
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.report-title { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }
.title-icon { font-size: 20px; flex-shrink: 0; }
.title-text {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a2e;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-badge {
  padding: 3px 10px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}

.status-badge.completed { background: #e6f7e6; color: #1a7a1a; }
.status-badge.processing { background: #e8f4fd; color: #1a73e8; }
.status-badge.failed { background: #fde8e8; color: #c0392b; }

.card-body { margin-bottom: 12px; }

.card-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.meta-item {
  font-size: 12px;
  color: #888;
}

.card-actions {
  display: flex;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
}

.btn-view, .btn-delete {
  flex: 1;
  padding: 8px 12px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-view { background: #e8f4fd; color: #1a73e8; }
.btn-view:hover { background: #1a73e8; color: #fff; }
.btn-delete { background: #f5f5f5; color: #888; }
.btn-delete:hover { background: #e74c3c; color: #fff; }

@media (max-width: 768px) {
  .history-page { padding: 16px; }
  .history-grid { grid-template-columns: 1fr; }
  .page-header { flex-direction: column; align-items: flex-start; gap: 12px; }
}
</style>
