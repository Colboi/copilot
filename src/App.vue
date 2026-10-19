<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { invoke } from '@tauri-apps/api/core'

import { pluginViews } from './plugin-views.js'
import SettingsPanel from './SettingsPanel.vue'
import WindowTitleBar from './WindowTitleBar.vue'
import { appearanceCssVariables, DEFAULT_APPEARANCE } from './theme.js'

const plugins = ref([])
const selectedPluginId = ref(null)
const loading = ref(true)
const errorMessage = ref('')
const busyPluginId = ref(null)
const draggingPluginId = ref(null)
const dropGapIndex = ref(null)
const reordering = ref(false)
const settingsOpen = ref(false)
const appearance = ref({ ...DEFAULT_APPEARANCE })
const appearanceStyle = computed(() => appearanceCssVariables(appearance.value))
let backendUrl = null
let pluginRefreshTimer = null
let pendingPluginDrag = null
let pluginDragPreview = null
let suppressPluginClick = false

const sleep = (duration) => new Promise((resolve) => window.setTimeout(resolve, duration))

async function resolveBackendUrl() {
  backendUrl = await invoke('get_backend_url')
}

async function requestBackend(path, options = {}) {
  if (backendUrl === null) {
    throw new Error('本地服务地址尚未初始化')
  }

  const headers = {
    ...(options.headers ?? {}),
  }
  const isFormDataBody = typeof FormData !== 'undefined' && options.body instanceof FormData
  if (
    options.body !== undefined
    && !isFormDataBody
    && headers['Content-Type'] === undefined
    && headers['content-type'] === undefined
  ) {
    headers['Content-Type'] = 'application/json'
  }

  const response = await fetch(`${backendUrl}${path}`, {
    ...options,
    headers,
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

async function loadSettings() {
  const settings = await requestBackend('/api/settings')
  appearance.value = { ...DEFAULT_APPEARANCE, ...settings.appearance }
}

async function refreshPlugins() {
  if (reordering.value || pendingPluginDrag !== null) {
    return
  }

  try {
    await loadPlugins()
    errorMessage.value = ''
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
  }
}

function scrollToPlugin(plugin) {
  selectedPluginId.value = plugin.id
  document.getElementById(`plugin-card-${plugin.id}`)?.scrollIntoView({
    behavior: 'smooth',
    block: 'start',
  })
}

function createPluginDragPreview(sourceElement, event) {
  const previewElement = sourceElement.cloneNode(true)
  const sourceBounds = sourceElement.getBoundingClientRect()
  previewElement.classList.remove('is-selected', 'is-dragging', 'is-drag-target')
  previewElement.classList.add('plugin-drag-preview')
  previewElement.setAttribute('aria-hidden', 'true')
  previewElement.style.width = `${sourceBounds.width}px`
  previewElement.style.transform = `translate3d(${event.clientX + 12}px, ${event.clientY + 12}px, 0)`
  document.body.append(previewElement)
  pluginDragPreview = previewElement
}

function updatePluginDragPreview(clientX, clientY) {
  if (pluginDragPreview === null) {
    return
  }

  pluginDragPreview.style.transform = `translate3d(${clientX + 12}px, ${clientY + 12}px, 0)`
}

function updatePluginDropGap(clientX, clientY) {
  const element = document.elementFromPoint(clientX, clientY)
  const sidebarNav = element?.closest('.sidebar-nav')
  if (!(sidebarNav instanceof HTMLElement)) {
    dropGapIndex.value = null
    return
  }

  const pluginElements = Array.from(sidebarNav.querySelectorAll('[data-plugin-id]'))
  let nextDropGapIndex = pluginElements.length
  for (let index = 0; index < pluginElements.length; index += 1) {
    const pluginBounds = pluginElements[index].getBoundingClientRect()
    if (clientY < pluginBounds.top + pluginBounds.height / 2) {
      nextDropGapIndex = index
      break
    }
  }

  dropGapIndex.value = nextDropGapIndex
}

function startPluginPointerDrag(pluginId, event) {
  if (reordering.value || event.button !== 0) {
    return
  }

  const sourceElement = event.currentTarget
  if (!(sourceElement instanceof HTMLElement)) {
    return
  }

  pendingPluginDrag = {
    pluginId,
    pointerId: event.pointerId,
    sourceElement,
    startX: event.clientX,
    startY: event.clientY,
    active: false,
  }
  sourceElement.setPointerCapture(event.pointerId)
  window.addEventListener('pointermove', handlePluginPointerMove, { passive: false })
  window.addEventListener('pointerup', handlePluginPointerUp)
  window.addEventListener('pointercancel', handlePluginPointerCancel)
}

function handlePluginPointerMove(event) {
  if (pendingPluginDrag === null || event.pointerId !== pendingPluginDrag.pointerId) {
    return
  }

  const distance = Math.hypot(
    event.clientX - pendingPluginDrag.startX,
    event.clientY - pendingPluginDrag.startY,
  )
  if (!pendingPluginDrag.active) {
    if (distance < 5) {
      return
    }

    pendingPluginDrag.active = true
    draggingPluginId.value = pendingPluginDrag.pluginId
    dropGapIndex.value = null
    document.body.classList.add('is-plugin-dragging')
    createPluginDragPreview(pendingPluginDrag.sourceElement, event)
  }

  event.preventDefault()
  updatePluginDragPreview(event.clientX, event.clientY)
  updatePluginDropGap(event.clientX, event.clientY)
}

function handlePluginPointerUp(event) {
  if (pendingPluginDrag === null || event.pointerId !== pendingPluginDrag.pointerId) {
    return
  }

  const currentDrag = pendingPluginDrag
  if (currentDrag.active) {
    event.preventDefault()
    updatePluginDropGap(event.clientX, event.clientY)
  }
  const currentDropGapIndex = currentDrag.active ? dropGapIndex.value : null
  finishPluginPointerDrag()

  if (currentDrag.active && currentDropGapIndex !== null) {
    void persistPluginOrder(currentDrag.pluginId, currentDropGapIndex)
  }
}

function handlePluginPointerCancel(event) {
  if (pendingPluginDrag === null || event.pointerId !== pendingPluginDrag.pointerId) {
    return
  }

  finishPluginPointerDrag()
}

function finishPluginPointerDrag() {
  const currentDrag = pendingPluginDrag
  if (currentDrag?.sourceElement.hasPointerCapture(currentDrag.pointerId)) {
    currentDrag.sourceElement.releasePointerCapture(currentDrag.pointerId)
  }
  window.removeEventListener('pointermove', handlePluginPointerMove)
  window.removeEventListener('pointerup', handlePluginPointerUp)
  window.removeEventListener('pointercancel', handlePluginPointerCancel)
  pluginDragPreview?.remove()
  pluginDragPreview = null
  draggingPluginId.value = null
  dropGapIndex.value = null
  document.body.classList.remove('is-plugin-dragging')

  if (currentDrag?.active) {
    suppressPluginClick = true
    window.setTimeout(() => {
      suppressPluginClick = false
    }, 0)
  }
  pendingPluginDrag = null
}

async function persistPluginOrder(sourcePluginId, insertionIndex) {
  const previousPlugins = [...plugins.value]
  const sourceIndex = previousPlugins.findIndex((plugin) => plugin.id === sourcePluginId)
  if (sourceIndex < 0 || insertionIndex < 0 || insertionIndex > previousPlugins.length) {
    return
  }

  const nextPlugins = [...previousPlugins]
  const [movedPlugin] = nextPlugins.splice(sourceIndex, 1)
  const adjustedInsertionIndex = sourceIndex < insertionIndex ? insertionIndex - 1 : insertionIndex
  nextPlugins.splice(adjustedInsertionIndex, 0, movedPlugin)

  if (nextPlugins.every((plugin, index) => plugin.id === previousPlugins[index].id)) {
    return
  }

  plugins.value = nextPlugins
  reordering.value = true
  errorMessage.value = ''

  try {
    plugins.value = await requestBackend('/api/plugins/order', {
      method: 'POST',
      body: JSON.stringify({
        order: nextPlugins.map((plugin) => plugin.id),
      }),
    })
  } catch (error) {
    plugins.value = previousPlugins
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    reordering.value = false
  }
}

function handlePluginClick(plugin, event) {
  if (suppressPluginClick) {
    event.preventDefault()
    return
  }

  scrollToPlugin(plugin)
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

function handleAppearanceChanged(nextAppearance) {
  appearance.value = { ...DEFAULT_APPEARANCE, ...nextAppearance }
}

onMounted(async () => {
  try {
    await resolveBackendUrl()
    await waitForBackend()
    pluginRefreshTimer = window.setInterval(refreshPlugins, 2000)
    await Promise.all([
      loadPlugins().finally(() => { loading.value = false }),
      loadSettings(),
    ])
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
  finishPluginPointerDrag()
})
</script>

<template>
  <div class="app-shell" :style="appearanceStyle">
    <WindowTitleBar />
    <div class="app-layout">
    <aside class="sidebar">
      <div class="sidebar-header">
        <h1 class="app-title">Colpilot</h1>
        <button
          class="settings-button"
          type="button"
          title="设置"
          aria-label="设置"
          @click="settingsOpen = true"
        >
          ⚙
        </button>
      </div>

      <nav class="sidebar-nav" aria-label="插件管理">
        <div class="nav-caption">插件管理</div>
        <div
          class="plugin-drop-gap"
          :class="{ 'is-active': dropGapIndex === 0 }"
          aria-hidden="true"
        ></div>
        <template v-for="(plugin, index) in plugins" :key="plugin.id">
          <button
            class="nav-item plugin-nav-item"
            :class="{
              'is-selected': plugin.id === selectedPluginId,
              'is-dragging': plugin.id === draggingPluginId,
            }"
            type="button"
            :data-plugin-id="plugin.id"
            :aria-grabbed="plugin.id === draggingPluginId"
            @pointerdown="startPluginPointerDrag(plugin.id, $event)"
            @click="handlePluginClick(plugin, $event)"
          >
            <span
              v-if="plugin.icon"
              class="plugin-nav-icon"
              :style="{ '--plugin-color': plugin.color }"
            >
              {{ plugin.icon }}
            </span>
            <span class="nav-item-label">{{ plugin.name }}</span>
            <span
              class="nav-runtime-status"
              :class="`is-${plugin.runtime?.status ?? 'stopped'}`"
              :title="plugin.runtime?.detail ?? '工具未运行'"
              :aria-label="plugin.runtime?.detail ?? '工具未运行'"
            ></span>
          </button>
          <div
            class="plugin-drop-gap"
            :class="{ 'is-active': dropGapIndex === index + 1 }"
            aria-hidden="true"
          ></div>
        </template>
      </nav>
    </aside>

    <main class="main-content">
      <section class="dashboard-content">
        <div v-if="loading" class="state-panel">
          <div class="loader"></div>
          <strong>正在载入功能清单</strong>
          <span>正在等待本地服务完成启动</span>
        </div>

        <div v-else-if="errorMessage && plugins.length === 0" class="state-panel error-panel">
          <div class="state-icon">!</div>
          <strong>本地服务连接失败</strong>
          <span>{{ errorMessage }}</span>
        </div>

        <div v-else>
          <div v-if="errorMessage" class="inline-error">
            <span>{{ errorMessage }}</span>
          </div>

          <div class="plugin-grid">
            <article
              v-for="plugin in plugins"
              :key="plugin.id"
              :id="`plugin-card-${plugin.id}`"
              class="plugin-card"
              :class="{ 'is-disabled': !plugin.enabled, 'is-focused': plugin.id === selectedPluginId }"
            >
              <div class="card-topline">
                <span
                  v-if="plugin.icon"
                  class="plugin-icon"
                  :style="{ '--plugin-color': plugin.color }"
                >
                  {{ plugin.icon }}
                </span>
                <span class="plugin-category">{{ plugin.category }}</span>
                <span class="enabled-pill" :class="{ 'is-disabled': !plugin.enabled }">
                  {{ plugin.enabled ? '已启用' : '已停用' }}
                </span>
              </div>
              <h3>{{ plugin.name }}</h3>
              <p class="plugin-description">{{ plugin.description }}</p>

              <div class="plugin-card-view">
                <div
                  v-if="plugin.enabled && !plugin.backend_ready && plugin.runtime?.status === 'error'"
                  class="plugin-runtime-state is-error"
                  role="alert"
                >
                  <strong>插件启动或运行失败</strong>
                  <span>{{ plugin.runtime.detail }}</span>
                </div>
                <div
                  v-else-if="plugin.enabled && (!plugin.backend_ready || ['starting', 'stopping'].includes(plugin.runtime?.status))"
                  class="plugin-runtime-state"
                  role="status"
                >
                  <div class="loader"></div>
                  <strong>{{ plugin.runtime?.status === 'stopping' ? '正在停止插件' : '正在启动插件' }}</strong>
                  <span>{{ plugin.runtime?.detail }}</span>
                </div>
                <component
                  v-else-if="plugin.enabled && pluginViews[plugin.view]"
                  :is="pluginViews[plugin.view]"
                  :plugin="plugin"
                  :request-backend="requestBackend"
                />
                <div v-else-if="plugin.enabled" class="plugin-unavailable-state">
                  <strong>插件界面不可用</strong>
                  <span>当前插件没有注册可用的前端组件</span>
                </div>
                <div v-else class="plugin-disabled-state">
                  <strong>插件已停用</strong>
                  <span>启用插件后可以使用对应功能</span>
                </div>
              </div>

              <div class="card-footer">
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
        </div>
      </section>
    </main>
    </div>

    <SettingsPanel
      v-if="settingsOpen"
      :request-backend="requestBackend"
      @close="settingsOpen = false"
      @appearance-changed="handleAppearanceChanged"
    />
  </div>
</template>
