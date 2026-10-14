<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { pluginViews } from './plugin-views.js'

const backendUrl = 'http://127.0.0.1:37651'

const sidebarOpen = ref(true)
const plugins = ref([])
const selectedPluginId = ref(null)
const loading = ref(true)
const backendReady = ref(false)
const errorMessage = ref('')
const busyPluginId = ref(null)
let pluginRefreshTimer = null

const enabledPlugins = computed(() => plugins.value.filter((plugin) => plugin.enabled))
const selectedPlugin = computed(() => plugins.value.find((plugin) => plugin.id === selectedPluginId.value) ?? null)
const selectedPluginView = computed(() => {
  const view = selectedPlugin.value?.view
  return view ? pluginViews[view] ?? null : null
})

const sleep = (duration) => new Promise((resolve) => window.setTimeout(resolve, duration))

async function requestBackend(path, options = {}) {
  const response = await fetch(`${backendUrl}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
    ...options,
  })

  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || `Backend request failed: ${response.status}`)
  }

  return response.json()
}

async function waitForBackend() {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      await requestBackend('/api/health')
      backendReady.value = true
      return
    } catch (error) {
      if (attempt === 39) {
        throw error
      }
      await sleep(250)
    }
  }
}

async function loadPlugins() {
  plugins.value = await requestBackend('/api/plugins')
  if (plugins.value.length === 0) {
    selectedPluginId.value = null
  } else if (!plugins.value.some((plugin) => plugin.id === selectedPluginId.value)) {
    selectedPluginId.value = plugins.value[0].id
  }
}

async function refreshPlugins() {
  try {
    await loadPlugins()
    errorMessage.value = ''
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
  }
}

function selectPlugin(plugin) {
  selectedPluginId.value = plugin.id
}

async function togglePlugin(plugin) {
  busyPluginId.value = plugin.id
  errorMessage.value = ''

  try {
    const updatedPlugin = await requestBackend(`/api/plugins/${encodeURIComponent(plugin.id)}/toggle`, {
      method: 'POST',
      body: JSON.stringify({ enabled: !plugin.enabled }),
    })
    const index = plugins.value.findIndex((item) => item.id === plugin.id)
    plugins.value[index] = updatedPlugin
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    busyPluginId.value = null
  }
}

onMounted(async () => {
  try {
    await waitForBackend()
    await loadPlugins()
    pluginRefreshTimer = window.setInterval(refreshPlugins, 2000)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  if (pluginRefreshTimer !== null) {
    window.clearInterval(pluginRefreshTimer)
  }
})
</script>

<template>
  <div class="app-shell" :class="{ 'sidebar-collapsed': !sidebarOpen }">
    <aside class="sidebar" :class="{ 'is-hidden': !sidebarOpen }">
      <div class="brand-block">
        <div class="brand-mark">C</div>
        <div class="brand-copy">
          <strong>Colpilot</strong>
          <span>工具驾驶舱</span>
        </div>
      </div>

      <nav class="sidebar-nav" aria-label="主导航">
        <button class="nav-item is-active" type="button">
          <span class="nav-icon">⌂</span>
          <span>仪表盘</span>
        </button>

        <div class="nav-caption">插件管理</div>
        <button
          v-for="plugin in plugins"
          :key="plugin.id"
          class="nav-item plugin-nav-item"
          :class="{ 'is-selected': plugin.id === selectedPluginId }"
          type="button"
          @click="selectPlugin(plugin)"
        >
          <span class="plugin-nav-icon" :style="{ '--plugin-color': plugin.color }">{{ plugin.icon }}</span>
          <span class="nav-item-label">{{ plugin.name }}</span>
          <span
            v-if="plugin.tool_type === 'continuous'"
            class="nav-runtime-status"
            :class="`is-${plugin.runtime?.status ?? 'stopped'}`"
            :title="plugin.runtime?.detail ?? '工具未运行'"
            :aria-label="plugin.runtime?.detail ?? '工具未运行'"
          ></span>
        </button>
      </nav>

      <div class="sidebar-footer">
        <div class="footer-orb"></div>
        <div>
          <strong>{{ enabledPlugins.length }} 个功能已启用</strong>
          <span>从侧边栏快速进入</span>
        </div>
      </div>
    </aside>

    <main class="main-content">
      <header class="topbar">
        <div class="topbar-left">
          <button class="icon-button" type="button" title="隐藏或显示侧边栏" @click="sidebarOpen = !sidebarOpen">
            <span v-if="sidebarOpen">☰</span>
            <span v-else>☷</span>
          </button>
          <div class="breadcrumb">
            <span>工作台</span>
            <span class="breadcrumb-separator">/</span>
            <strong>仪表盘</strong>
          </div>
        </div>

        <div class="topbar-right">
          <span class="connection-status" :class="{ 'is-offline': !backendReady }">
            <span class="connection-dot"></span>
            {{ backendReady ? '本地服务在线' : '正在连接本地服务' }}
          </span>
          <div class="avatar">C</div>
        </div>
      </header>

      <section class="dashboard-content">
        <div class="hero-section">
          <div>
            <p class="eyebrow">GOOD MORNING, PILOT</p>
            <h1>今天想用哪个工具？</h1>
            <p class="hero-description">把低频但重要的小工具集中在一个清晰的工作台里。</p>
          </div>
          <div class="hero-illustration" aria-hidden="true">
            <div class="illustration-ring ring-one"></div>
            <div class="illustration-ring ring-two"></div>
            <div class="illustration-core">✦</div>
          </div>
        </div>

        <div class="stats-row">
          <div class="stat-card">
            <span class="stat-label">全部功能</span>
            <strong>{{ plugins.length }}</strong>
            <span class="stat-hint">已接入工作台</span>
          </div>
          <div class="stat-card accent-card">
            <span class="stat-label">当前可用</span>
            <strong>{{ enabledPlugins.length }}</strong>
            <span class="stat-hint">随时可以打开</span>
          </div>
          <div class="stat-card">
            <span class="stat-label">工作状态</span>
            <strong>{{ backendReady ? 'Ready' : 'Wait' }}</strong>
            <span class="stat-hint">Python 服务状态</span>
          </div>
        </div>

        <div class="section-heading">
          <div>
            <p class="eyebrow">YOUR TOOLBOX</p>
            <h2>功能插件</h2>
          </div>
          <span class="section-count">{{ plugins.length }} 个功能</span>
        </div>

        <div v-if="loading" class="state-panel">
          <div class="loader"></div>
          <strong>正在载入功能清单</strong>
          <span>正在等待本地服务完成启动</span>
        </div>

        <div v-else-if="errorMessage" class="state-panel error-panel">
          <div class="state-icon">!</div>
          <strong>本地服务连接失败</strong>
          <span>{{ errorMessage }}</span>
        </div>

        <div v-else class="plugin-grid">
          <article
            v-for="plugin in plugins"
            :key="plugin.id"
            class="plugin-card"
            :class="{ 'is-disabled': !plugin.enabled, 'is-focused': plugin.id === selectedPluginId }"
            @click="selectPlugin(plugin)"
          >
            <div class="card-topline">
              <span class="plugin-icon" :style="{ '--plugin-color': plugin.color }">{{ plugin.icon }}</span>
              <span class="plugin-category">{{ plugin.category }}</span>
              <span class="enabled-pill" :class="{ 'is-disabled': !plugin.enabled }">
                {{ plugin.enabled ? '已启用' : '已停用' }}
              </span>
            </div>
            <h3>{{ plugin.name }}</h3>
            <p>{{ plugin.description }}</p>
            <div class="card-footer">
              <button class="open-button" type="button" :disabled="!plugin.enabled" @click.stop="selectPlugin(plugin)">
                打开功能 <span>→</span>
              </button>
              <button
                class="toggle-button"
                type="button"
                :disabled="busyPluginId === plugin.id"
                @click.stop="togglePlugin(plugin)"
              >
                {{ busyPluginId === plugin.id ? '处理中' : plugin.enabled ? '停用' : '启用' }}
              </button>
            </div>
          </article>
        </div>

        <section
          v-if="selectedPlugin"
          class="detail-panel"
        >
          <div class="detail-header">
            <div class="detail-icon" :style="{ '--plugin-color': selectedPlugin.color }">{{ selectedPlugin.icon }}</div>
            <div class="detail-copy">
              <p class="eyebrow">SELECTED PLUGIN</p>
              <h2>{{ selectedPlugin.name }}</h2>
              <p>{{ selectedPlugin.description }}</p>
            </div>
            <div class="detail-meta">
              <span>插件状态</span>
              <strong>{{ selectedPlugin.enabled ? '可用' : '已停用' }}</strong>
            </div>
          </div>

          <component
            v-if="selectedPluginView"
            :is="selectedPluginView"
            :plugin="selectedPlugin"
            :request-backend="requestBackend"
          />
          <div v-else class="state-panel error-panel">
            <div class="state-icon">!</div>
            <strong>插件界面不可用</strong>
            <span>当前插件没有注册可用的前端组件</span>
          </div>
        </section>
      </section>
    </main>
  </div>
</template>
