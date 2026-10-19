<script setup>
import { onMounted, ref } from 'vue'

import { DEFAULT_APPEARANCE } from './theme.js'

const props = defineProps({
  requestBackend: {
    type: Function,
    required: true,
  },
})

const emit = defineEmits(['close', 'appearance-changed'])

const activeSection = ref('appearance')
const appearance = ref({ ...DEFAULT_APPEARANCE })
const themes = ref([])
const about = ref({ author: 'Colboi', version: '0.1.0' })
const installedPlugins = ref([])
const repositoryUrl = ref('')
const zipFileInput = ref(null)
const updateInterval = ref(120)
const loading = ref(true)
const savingAppearance = ref(false)
const savingInterval = ref(false)
const downloading = ref(false)
const importingZip = ref(false)
const checkingUpdates = ref(false)
const message = ref('')
const errorMessage = ref('')
const selectedThemeId = ref('midnight')

const sections = [
  { id: 'appearance', label: '外观' },
  { id: 'plugins', label: '插件下载' },
  { id: 'about', label: '关于' },
]

const colorFields = [
  { key: 'theme_color', label: '主题色' },
  { key: 'background_color', label: '主背景色' },
  { key: 'sidebar_color', label: '左侧栏颜色' },
  { key: 'card_color', label: '卡片颜色' },
  { key: 'card_hover_color', label: '卡片悬停颜色' },
  { key: 'primary_text_color', label: '主要文字颜色' },
  { key: 'secondary_text_color', label: '次要文字颜色' },
  { key: 'border_color', label: '边框颜色' },
]

function clearMessage() {
  message.value = ''
  errorMessage.value = ''
}

function applyTheme(themeId) {
  const theme = themes.value.find((item) => item.id === themeId)
  if (!theme) {
    appearance.value.theme_name = 'custom'
    selectedThemeId.value = 'custom'
    return
  }
  appearance.value = {
    ...appearance.value,
    ...theme.colors,
    theme_name: theme.id,
  }
  selectedThemeId.value = theme.id
}

function markCustomAppearance() {
  appearance.value.theme_name = 'custom'
  selectedThemeId.value = 'custom'
}

async function loadSettings() {
  const settings = await props.requestBackend('/api/settings')
  appearance.value = { ...DEFAULT_APPEARANCE, ...settings.appearance }
  themes.value = settings.themes ?? []
  about.value = settings.about ?? about.value
  updateInterval.value = settings.plugin_update_interval_minutes ?? 120
  selectedThemeId.value = themes.value.some(
    (theme) => theme.id === appearance.value.theme_name,
  )
    ? appearance.value.theme_name
    : 'custom'
}

async function loadInstalledPlugins() {
  installedPlugins.value = await props.requestBackend('/api/plugins/installed')
}

async function saveAppearance() {
  clearMessage()
  savingAppearance.value = true
  try {
    const response = await props.requestBackend('/api/settings/appearance', {
      method: 'POST',
      body: JSON.stringify(appearance.value),
    })
    appearance.value = { ...appearance.value, ...response.appearance }
    emit('appearance-changed', appearance.value)
    message.value = '外观设置已保存'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    savingAppearance.value = false
  }
}

async function saveUpdateInterval() {
  clearMessage()
  savingInterval.value = true
  try {
    const response = await props.requestBackend('/api/settings/plugin-update-interval', {
      method: 'POST',
      body: JSON.stringify({ minutes: Number(updateInterval.value) }),
    })
    updateInterval.value = response.plugin_update_interval_minutes
    message.value = '更新检查间隔已保存'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    savingInterval.value = false
  }
}

async function downloadPlugin() {
  clearMessage()
  downloading.value = true
  try {
    const response = await props.requestBackend('/api/plugins/download', {
      method: 'POST',
      body: JSON.stringify({ repository_url: repositoryUrl.value }),
    })
    installedPlugins.value = response.installed ?? []
    repositoryUrl.value = ''
    message.value = '插件已经安装，重启 Colpilot 后会加载插件。'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    downloading.value = false
  }
}

function openZipPicker() {
  zipFileInput.value?.click()
}

async function importZipPlugin(event) {
  const selectedFile = event.target.files?.[0]
  event.target.value = ''
  if (!selectedFile) {
    return
  }

  clearMessage()
  importingZip.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile, selectedFile.name)
    const response = await props.requestBackend('/api/plugins/import-zip', {
      method: 'POST',
      body: formData,
    })
    installedPlugins.value = response.installed ?? []
    message.value = '插件已经导入，重启 Colpilot 后会加载插件。'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    importingZip.value = false
  }
}

async function checkUpdates() {
  clearMessage()
  checkingUpdates.value = true
  try {
    installedPlugins.value = await props.requestBackend('/api/plugins/check-updates', {
      method: 'POST',
    })
    message.value = '插件更新状态已经检查'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    checkingUpdates.value = false
  }
}

function statusClass(status) {
  return `is-${status}`
}

onMounted(async () => {
  try {
    await Promise.all([loadSettings(), loadInstalledPlugins()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="settings-overlay" role="dialog" aria-modal="true" aria-label="设置">
    <section class="settings-window">
      <header class="settings-header">
        <div>
          <span class="settings-eyebrow">Colpilot</span>
          <h2>设置</h2>
        </div>
        <button class="settings-close-button" type="button" aria-label="关闭设置" @click="emit('close')">
          ×
        </button>
      </header>

      <div class="settings-layout">
        <nav class="settings-sidebar" aria-label="设置分类">
          <button
            v-for="section in sections"
            :key="section.id"
            class="settings-nav-item"
            :class="{ 'is-active': activeSection === section.id }"
            type="button"
            @click="activeSection = section.id"
          >
            {{ section.label }}
          </button>
        </nav>

        <div class="settings-content">
          <div v-if="loading" class="settings-loading">正在载入设置</div>
          <div v-else>
            <div v-if="errorMessage" class="settings-message is-error">{{ errorMessage }}</div>
            <div v-else-if="message" class="settings-message">{{ message }}</div>

            <section v-if="activeSection === 'appearance'" class="settings-section">
              <div class="settings-section-heading">
                <div>
                  <span class="settings-eyebrow">Appearance</span>
                  <h3>外观</h3>
                </div>
                <button
                  class="settings-primary-button"
                  type="button"
                  :disabled="savingAppearance"
                  @click="saveAppearance"
                >
                  {{ savingAppearance ? '保存中' : '保存外观' }}
                </button>
              </div>

              <label class="settings-field settings-theme-select">
                <span>主题预设</span>
                <select v-model="selectedThemeId" @change="applyTheme(selectedThemeId)">
                  <option value="custom">自定义</option>
                  <option v-for="theme in themes" :key="theme.id" :value="theme.id">
                    {{ theme.name }}
                  </option>
                </select>
              </label>

              <div class="settings-color-grid">
                <label v-for="field in colorFields" :key="field.key" class="settings-color-field">
                  <span>{{ field.label }}</span>
                  <span class="settings-color-control">
                    <input
                      v-model="appearance[field.key]"
                      class="settings-color-input"
                      type="color"
                      :aria-label="field.label"
                      @input="markCustomAppearance"
                    />
                    <code>{{ appearance[field.key] }}</code>
                  </span>
                </label>
              </div>
            </section>

            <section v-else-if="activeSection === 'plugins'" class="settings-section">
              <div class="settings-section-heading">
                <div>
                  <span class="settings-eyebrow">Plugins</span>
                  <h3>插件下载</h3>
                </div>
                <button
                  class="settings-secondary-button"
                  type="button"
                  :disabled="checkingUpdates"
                  @click="checkUpdates"
                >
                  {{ checkingUpdates ? '检查中' : '检查更新' }}
                </button>
              </div>

              <form class="settings-download-form" @submit.prevent="downloadPlugin">
                <label class="settings-field">
                  <span>GitHub 仓库 URL</span>
                  <input
                    v-model="repositoryUrl"
                    type="url"
                    placeholder="https://github.com/owner/repository"
                    required
                  />
                </label>
                <button class="settings-primary-button" type="submit" :disabled="downloading">
                  {{ downloading ? '下载中' : '下载插件' }}
                </button>
              </form>

              <div class="settings-zip-import">
                <input
                  ref="zipFileInput"
                  class="settings-hidden-file-input"
                  type="file"
                  accept=".zip,application/zip"
                  @change="importZipPlugin"
                />
                <div class="settings-zip-copy">
                  <strong>导入私有插件</strong>
                  <span>从本地 ZIP 仓库文件安装插件</span>
                </div>
                <button
                  class="settings-secondary-button"
                  type="button"
                  :disabled="importingZip"
                  @click="openZipPicker"
                >
                  {{ importingZip ? '导入中' : '导入 ZIP' }}
                </button>
              </div>

              <div class="settings-plugin-check">
                <label class="settings-field">
                  <span>更新检查间隔（分钟）</span>
                  <input v-model.number="updateInterval" type="number" min="5" max="1440" required />
                </label>
                <button
                  class="settings-secondary-button"
                  type="button"
                  :disabled="savingInterval"
                  @click="saveUpdateInterval"
                >
                  {{ savingInterval ? '保存中' : '保存间隔' }}
                </button>
              </div>

              <div class="settings-list-heading">
                <h4>已安装插件</h4>
                <span>{{ installedPlugins.length }} 项</span>
              </div>
              <div v-if="installedPlugins.length === 0" class="settings-empty-state">
                当前没有已安装插件
              </div>
              <ul v-else class="settings-plugin-list">
                <li v-for="plugin in installedPlugins" :key="plugin.id" class="settings-plugin-item">
                  <div class="settings-plugin-main">
                    <strong>{{ plugin.name }}</strong>
                    <span>{{ plugin.id }}</span>
                    <a
                      v-if="plugin.source_type === 'github' && plugin.source_url"
                      :href="plugin.source_url"
                      target="_blank"
                      rel="noreferrer"
                    >
                      {{ plugin.source_url }}
                    </a>
                    <span v-else>{{ plugin.source_url || '来源：本地插件' }}</span>
                  </div>
                  <span class="settings-plugin-status" :class="statusClass(plugin.status)">
                    {{ plugin.status_label }}
                  </span>
                </li>
              </ul>
            </section>

            <section v-else class="settings-section settings-about-section">
              <span class="settings-eyebrow">About</span>
              <h3>关于</h3>
              <div class="settings-about-card">
                <span>作者</span>
                <strong>{{ about.author }}</strong>
                <span>版本</span>
                <strong>{{ about.version }}</strong>
              </div>
            </section>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
