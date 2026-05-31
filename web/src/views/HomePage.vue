<template>
  <div class="home-panel">
    <!-- 左侧：输入面板 -->
    <aside class="input-panel">
      <div class="panel-card">
        <h2 class="panel-title">调研话题</h2>
        <p class="panel-desc">输入你想调研的主题，AI 会自动搜索论文并生成综述报告</p>

        <div class="form-group">
          <label class="form-label">话题描述</label>
          <textarea
            v-model="userInput"
            placeholder="例如：大语言模型在代码生成中的应用与优化..."
            rows="6"
            class="input-topic"
            :disabled="isSubmitting"
          ></textarea>
        </div>

        <div class="form-group">
          <label class="form-label">
            <span class="label-icon">📚</span> 知识库（可选）
          </label>
          <div class="kb-selector">
            <select v-model="selectedDbId" class="input-select" :disabled="isSubmitting || loadingKb" @change="onKbChange">
              <option value="">— 不使用知识库 —</option>
              <option v-for="kb in kbList" :key="kb.id" :value="kb.id">
                {{ kb.name }} ({{ kb.document_count || 0 }} 篇)
              </option>
            </select>
            <button class="btn-refresh-kb" @click="loadKbList" :disabled="loadingKb" title="刷新知识库列表">
              {{ loadingKb ? '⟳' : '🔄' }}
            </button>
          </div>
          <p class="form-hint" v-if="kbList.length === 0 && !loadingKb">
            还没有知识库？<router-link to="/knowledge">去上传文件</router-link>
          </p>
        </div>

        <div class="form-group">
          <label class="form-label">论文数量</label>
          <div class="count-row">
            <input
              type="range"
              v-model.number="maxPapers"
              min="5" max="50" step="5"
              class="input-range"
              :disabled="isSubmitting"
            />
            <span class="count-value">{{ maxPapers }} 篇</span>
          </div>
        </div>

        <button
          class="btn-submit"
          @click="startResearch"
          :disabled="!userInput.trim() || isSubmitting"
        >
          <span v-if="isSubmitting" class="btn-loading">⟳</span>
          {{ isSubmitting ? '调研中...' : '🚀 开始调研' }}
        </button>

        <p class="form-footnote" v-if="!isSubmitting">
          预计耗时 3-8 分钟，请耐心等待
        </p>
      </div>
    </aside>

    <!-- 右侧：报告展示区 -->
    <section class="report-panel">
      <!-- 空状态 -->
      <div class="empty-state" v-if="!isSubmitting && steps.length === 0 && !loadedReport">
        <div class="empty-icon">🔬</div>
        <h2>开始你的论文调研</h2>
        <p>在左侧输入话题，AI 将自动搜索论文、分析内容、生成综述报告</p>
        <div class="feature-grid">
          <div class="feature-item">
            <span class="feature-icon">🔍</span>
            <span class="feature-label">智能搜索</span>
            <span class="feature-desc">Semantic Scholar 论文检索</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">📖</span>
            <span class="feature-label">深度分析</span>
            <span class="feature-desc">三阶段聚类+全局分析</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">✍️</span>
            <span class="feature-label">自动写作</span>
            <span class="feature-desc">检索增强+自动审阅</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">📝</span>
            <span class="feature-label">Markdown 报告</span>
            <span class="feature-desc">结构化综述输出</span>
          </div>
        </div>
      </div>

      <!-- 进度步骤 -->
      <div class="progress-section" v-if="steps.length > 0" id="progress-container">
        <h3 class="section-heading">📊 生成进度</h3>
        <div
          v-for="(step, i) in steps"
          :key="i"
          class="step-card"
          :class="{ error: step.isError, active: step.isProcessing, complete: !step.isProcessing && !step.isError }"
        >
          <div class="step-header">
            <span class="step-badge">
              {{ step.isError ? '❌' : step.isProcessing ? '🔄' : '✅' }}
            </span>
            <span class="step-title">{{ step.title }}</span>
            <span class="step-time">{{ formatTime(step.timestamp) }}</span>
          </div>
          <div class="step-content markdown-body" v-if="step.content" v-html="parseMarkdown(step.content)"></div>
        </div>
      </div>

      <!-- 最终报告 -->
      <div class="report-result" v-if="finalReport">
        <div class="report-header">
          <h3 class="section-heading">📝 最终报告</h3>
          <div class="report-actions">
            <button class="btn-action" @click="copyReport">{{ copied ? '✅ 已复制' : '📋 复制' }}</button>
            <button class="btn-action" @click="downloadReport">💾 下载</button>
          </div>
        </div>
        <div class="report-body markdown-body" v-html="parseMarkdown(finalReport)"></div>
      </div>

      <!-- 历史报告查看 -->
      <div class="report-result" v-if="loadedReport && !finalReport">
        <div class="report-header">
          <h3 class="section-heading">📝 历史报告</h3>
          <div class="report-actions">
            <button class="btn-action" @click="copyReport">{{ copied ? '✅ 已复制' : '📋 复制' }}</button>
            <button class="btn-action" @click="downloadReport">💾 下载</button>
          </div>
        </div>
        <div class="report-body markdown-body" v-html="parseMarkdown(loadedReport)"></div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { knowledgeApi } from '../api/knowledge'

const route = useRoute()

// ===== 输入状态 =====
const userInput = ref('')
const maxPapers = ref(20)
const isSubmitting = ref(false)
const selectedDbId = ref('')
const kbList = ref([])
const loadingKb = ref(false)

// ===== 进度状态 =====
const steps = ref([])
const eventSource = ref(null)
const currentActiveStep = ref(null)
const activeSubSteps = ref(new Map())

// ===== 报告状态 =====
const finalReport = ref('')
const loadedReport = ref('')
const copied = ref(false)

// ===== 知识库 =====
const loadKbList = async () => {
  loadingKb.value = true
  try {
    const res = await knowledgeApi.getDatabases()
    const dbs = (res.data.databases || []).map(db => ({
      ...db,
      id: db.db_id || db.id
    })).filter(db => db !== null)
    kbList.value = dbs
  } catch (e) {
    console.error('加载知识库列表失败:', e)
    kbList.value = []
  } finally {
    loadingKb.value = false
  }
}

const onKbChange = async () => {
  try {
    await knowledgeApi.selectDatabase(selectedDbId.value || '')
  } catch (e) {
    console.error('选择知识库失败:', e)
  }
}

// ===== Markdown =====
const parseMarkdown = (content) => {
  if (!content) return ''
  try {
    const html = marked.parse(content)
    return DOMPurify.sanitize(html)
  } catch {
    return content
  }
}

// ===== 步骤映射 =====
const getStepName = (step) => {
  const names = {
    searching: '论文搜索',
    reading: '论文阅读',
    analyzing: '三阶段分析',
    writing: '报告撰写',
    reporting: '报告组装',
    finished: '流程完成',
    failed: '流程失败',
  }
  if (step.startsWith('section_writing_')) {
    const num = step.split('_').pop()
    return `撰写第${num}小节`
  }
  return names[step] || step
}

const formatTime = (ts) => {
  return new Date(ts).toLocaleTimeString()
}

// ===== SSE 事件处理 =====
const handleInitializing = (step, data) => {
  const el = {
    step,
    title: `${getStepName(step)} — 初始化`,
    content: '',
    thinking: '',
    isProcessing: true,
    isError: false,
    timestamp: new Date().toISOString(),
  }
  steps.value.push(el)
  if (step.startsWith('section_writing_')) {
    activeSubSteps.value.set(step, el)
  } else {
    currentActiveStep.value = el
  }
  autoScroll()
}

const handleThinking = (step, data) => {
  let target = currentActiveStep.value
  if (step.startsWith('section_writing_')) {
    target = activeSubSteps.value.get(step)
  }
  if (!target || target.step !== step) return
  target.title = `${getStepName(step)} — 思考中`
  target.isProcessing = true
  if (data) target.thinking += data
  autoScroll()
}

const handleGenerating = (step, data) => {
  let target = currentActiveStep.value
  if (step.startsWith('section_writing_')) {
    target = activeSubSteps.value.get(step)
  }
  if (!target || target.step !== step) return
  target.title = `${getStepName(step)} — 生成中`
  target.isProcessing = true
  if (data) target.content += data
  autoScroll()
}

const handleComplete = (step, data) => {
  let target = currentActiveStep.value
  if (step.startsWith('section_writing_')) {
    target = activeSubSteps.value.get(step)
  }
  if (!target || target.step !== step) return
  target.isProcessing = false
  target.title = `${getStepName(step)} — 完成`
  if (data) target.content += data
  currentActiveStep.value = null
  autoScroll()
}

const handleError = (step, data) => {
  let target = currentActiveStep.value
  if (step.startsWith('section_writing_')) {
    target = activeSubSteps.value.get(step)
  }
  if (!target || target.step !== step) return
  target.isProcessing = false
  target.isError = true
  target.title = `${getStepName(step)} — 出错`
  if (data) target.content += data
  currentActiveStep.value = null
  autoScroll()
}

const handleFinish = () => {
  finishProcessing()
}

const handleBackendData = (data) => {
  const { step, state, data: payload } = data
  const handlers = {
    initializing: () => handleInitializing(step, payload),
    thinking: () => handleThinking(step, payload),
    generating: () => handleGenerating(step, payload),
    completed: () => handleComplete(step, payload),
    error: () => handleError(step, payload),
    finished: () => handleFinish(),
  }
  if (handlers[state]) handlers[state]()
}

// ===== 核心操作 =====
const startResearch = async () => {
  if (!userInput.value.trim() || isSubmitting.value) return

  // 先选择知识库
  if (selectedDbId.value) {
    await onKbChange()
  }

  isSubmitting.value = true
  steps.value = []
  finalReport.value = ''
  loadedReport.value = ''

  const es = new EventSource(`/api/research?query=${encodeURIComponent(userInput.value)}`)
  eventSource.value = es

  es.onmessage = (event) => {
    try {
      handleBackendData(JSON.parse(event.data))
    } catch (e) {
      console.error('SSE 解析失败:', e)
    }
  }

  es.onerror = () => {
    finishProcessing()
  }
}

const finishProcessing = () => {
  isSubmitting.value = false
  eventSource.value?.close()
  activeSubSteps.value.clear()

  // 从章节步骤中提取最终报告
  const sectionSteps = steps.value.filter(s => s.step.startsWith('section_writing_'))
  if (sectionSteps.length > 0) {
    const lines = ['# 论文调研报告', '', `> 生成时间：${new Date().toLocaleString()}`, '', '---', '']
    for (const s of sectionSteps) {
      if (s.content) {
        lines.push(s.content)
        lines.push('')
        lines.push('---')
        lines.push('')
      }
    }
    finalReport.value = lines.join('\n')

    // 保存到 localStorage
    saveToHistory(userInput.value, finalReport.value)
  }

  autoScroll()
}

const saveToHistory = (query, report) => {
  try {
    const saved = localStorage.getItem('reportHistory')
    const list = saved ? JSON.parse(saved) : []
    list.unshift({
      id: Date.now().toString(),
      title: query.length > 50 ? query.slice(0, 50) + '...' : query,
      query,
      report,
      status: 'completed',
      createdAt: new Date().toISOString(),
    })
    localStorage.setItem('reportHistory', JSON.stringify(list.slice(0, 50)))
  } catch (e) {
    console.error('保存历史报告失败:', e)
  }
}

const copyReport = async () => {
  const text = finalReport.value || loadedReport.value
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    alert('复制失败，请手动复制')
  }
}

const downloadReport = () => {
  const text = finalReport.value || loadedReport.value
  if (!text) return
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `report_${Date.now()}.md`
  a.click()
  URL.revokeObjectURL(url)
}

const autoScroll = () => {
  nextTick(() => {
    const el = document.getElementById('progress-container')
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'end' })
  })
}

// ===== 生命周期 =====
onMounted(() => {
  loadKbList()

  // 从 URL 参数加载历史报告
  const reportId = route.query.reportId
  if (reportId) {
    try {
      const saved = localStorage.getItem('reportHistory')
      const list = saved ? JSON.parse(saved) : []
      const item = list.find(h => h.id === reportId)
      if (item) {
        loadedReport.value = item.report
      }
    } catch (e) {
      console.error('加载历史报告失败:', e)
    }
  }
})

onBeforeUnmount(() => {
  eventSource.value?.close()
})
</script>

<style scoped>
/* ===== 主体分栏 ===== */
.home-panel {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ===== 左侧输入面板 ===== */
.input-panel {
  width: 360px;
  min-width: 320px;
  max-width: 400px;
  background: #fff;
  border-right: 1px solid #e8e8e8;
  overflow-y: auto;
  padding: 20px;
  flex-shrink: 0;
}

.panel-card {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.panel-title {
  font-size: 20px;
  font-weight: 700;
  color: #1a1a2e;
}

.panel-desc {
  font-size: 13px;
  color: #888;
  line-height: 1.5;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  font-size: 13px;
  font-weight: 600;
  color: #555;
  display: flex;
  align-items: center;
  gap: 6px;
}

.label-icon { font-size: 14px; }

.input-topic {
  width: 100%;
  padding: 12px 14px;
  border: 2px solid #e0e0e0;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.6;
  resize: vertical;
  font-family: inherit;
  transition: border-color 0.2s;
  min-height: 120px;
}

.input-topic:focus {
  outline: none;
  border-color: #1a73e8;
  box-shadow: 0 0 0 3px rgba(26,115,232,0.1);
}

.input-topic:disabled {
  background: #f5f5f5;
  color: #999;
}

.input-topic::placeholder { color: #bbb; }

/* 知识库选择器 */
.kb-selector {
  display: flex;
  gap: 8px;
}

.input-select {
  flex: 1;
  padding: 10px 12px;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  font-size: 13px;
  font-family: inherit;
  background: #fff;
  cursor: pointer;
  transition: border-color 0.2s;
}

.input-select:focus {
  outline: none;
  border-color: #1a73e8;
}

.btn-refresh-kb {
  padding: 8px 10px;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  background: #fafafa;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn-refresh-kb:hover {
  background: #f0f0f0;
  border-color: #ccc;
}

.form-hint {
  font-size: 12px;
  color: #999;
}

.form-hint a {
  color: #1a73e8;
  text-decoration: none;
}

.form-hint a:hover { text-decoration: underline; }

/* 论文数量 */
.count-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.input-range {
  flex: 1;
  accent-color: #1a73e8;
  height: 6px;
}

.count-value {
  font-size: 14px;
  font-weight: 600;
  color: #1a73e8;
  min-width: 48px;
  text-align: right;
}

/* 提交按钮 */
.btn-submit {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 14px 20px;
  background: linear-gradient(135deg, #1a73e8, #1557b0);
  color: #fff;
  border: none;
  border-radius: 12px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  letter-spacing: 0.5px;
}

.btn-submit:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(26,115,232,0.3);
}

.btn-submit:active:not(:disabled) { transform: translateY(0); }

.btn-submit:disabled {
  background: #c0c0c0;
  cursor: not-allowed;
  transform: none;
}

.btn-loading {
  animation: spin 1s linear infinite;
  font-size: 18px;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.form-footnote {
  font-size: 12px;
  color: #aaa;
  text-align: center;
}

/* ===== 右侧报告面板 ===== */
.report-panel {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px;
  background: #f8f9fb;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  padding: 40px;
}

.empty-icon { font-size: 64px; margin-bottom: 20px; }

.empty-state h2 {
  font-size: 22px;
  font-weight: 700;
  color: #1a1a2e;
  margin-bottom: 8px;
}

.empty-state > p {
  font-size: 14px;
  color: #888;
  max-width: 480px;
  line-height: 1.5;
  margin-bottom: 32px;
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  max-width: 500px;
}

.feature-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 16px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}

.feature-icon { font-size: 28px; }
.feature-label { font-size: 14px; font-weight: 600; color: #1a1a2e; }
.feature-desc { font-size: 12px; color: #999; }

/* 进度区域 */
.progress-section { margin-bottom: 24px; }

.section-heading {
  font-size: 16px;
  font-weight: 700;
  color: #1a1a2e;
  margin-bottom: 16px;
}

.step-card {
  background: #fff;
  border-radius: 10px;
  padding: 14px 18px;
  margin-bottom: 10px;
  border-left: 4px solid #e0e0e0;
  box-shadow: 0 1px 4px rgba(0,0,0,0.03);
  transition: all 0.2s;
}

.step-card.active {
  border-left-color: #1a73e8;
  background: #f8fbff;
}

.step-card.error {
  border-left-color: #e74c3c;
  background: #fff5f5;
}

.step-card.complete {
  border-left-color: #27ae60;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.step-badge { font-size: 16px; flex-shrink: 0; }
.step-title { flex: 1; font-size: 14px; font-weight: 600; color: #333; }
.step-time { font-size: 11px; color: #aaa; }

.step-content {
  margin-top: 10px;
  padding: 12px;
  background: #fafafa;
  border-radius: 8px;
  font-size: 13px;
  max-height: 200px;
  overflow-y: auto;
}

/* 最终报告 */
.report-result {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.05);
}

.report-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #eee;
}

.report-header .section-heading { margin-bottom: 0; }
.report-actions { display: flex; gap: 8px; }

.btn-action {
  padding: 8px 16px;
  border: 1px solid #ddd;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-action:hover {
  background: #f5f5f5;
  border-color: #ccc;
}

.report-body { line-height: 1.7; }

/* ===== Markdown 渲染 ===== */
.markdown-body {
  word-break: break-word;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin-top: 24px;
  margin-bottom: 12px;
  font-weight: 700;
  line-height: 1.3;
}

.markdown-body :deep(h1) { font-size: 24px; border-bottom: 2px solid #eee; padding-bottom: 8px; }
.markdown-body :deep(h2) { font-size: 20px; }
.markdown-body :deep(h3) { font-size: 17px; }
.markdown-body :deep(h4) { font-size: 15px; }

.markdown-body :deep(p) { margin-bottom: 12px; line-height: 1.7; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { padding-left: 24px; margin-bottom: 12px; }
.markdown-body :deep(li) { margin-bottom: 4px; }

.markdown-body :deep(strong) { font-weight: 700; color: #1a1a2e; }

.markdown-body :deep(blockquote) {
  border-left: 4px solid #1a73e8;
  margin: 12px 0;
  padding: 8px 16px;
  background: #f0f6ff;
  border-radius: 0 8px 8px 0;
  color: #555;
}

.markdown-body :deep(code) {
  padding: 2px 6px;
  font-size: 85%;
  background: #f0f0f0;
  border-radius: 4px;
  font-family: 'SF Mono', Monaco, Consolas, monospace;
}

.markdown-body :deep(pre) {
  margin: 12px 0;
  padding: 16px;
  background: #1e1e2e;
  border-radius: 8px;
  overflow-x: auto;
}

.markdown-body :deep(pre code) { background: none; color: #e0e0e0; padding: 0; }

.markdown-body :deep(a) { color: #1a73e8; text-decoration: none; }
.markdown-body :deep(a:hover) { text-decoration: underline; }

.markdown-body :deep(table) { border-collapse: collapse; width: 100%; margin: 12px 0; }
.markdown-body :deep(th),
.markdown-body :deep(td) { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
.markdown-body :deep(th) { background: #f5f5f5; font-weight: 600; }
.markdown-body :deep(hr) { border: none; border-top: 1px solid #eee; margin: 20px 0; }

/* ===== 响应式 ===== */
@media (max-width: 768px) {
  .home-panel { flex-direction: column; }

  .input-panel {
    width: 100%;
    max-width: none;
    border-right: none;
    border-bottom: 1px solid #e8e8e8;
    max-height: 50vh;
  }

  .report-panel { padding: 16px; }
  .feature-grid { grid-template-columns: 1fr 1fr; gap: 8px; }
}

@media (max-width: 480px) {
  .input-panel { padding: 12px; }
  .report-panel { padding: 12px; }
  .report-result { padding: 16px; }
  .report-header { flex-direction: column; align-items: flex-start; gap: 8px; }
  .feature-grid { grid-template-columns: 1fr; }
}
</style>
