const manifestModules = import.meta.glob('../plugins/*/manifest.json', {
  eager: true,
  import: 'default',
})
const viewModules = import.meta.glob('../plugins/*/ui/*.vue', {
  eager: true,
  import: 'default',
})

export const pluginViews = Object.fromEntries(
  Object.entries(manifestModules).map(([manifestPath, manifest]) => {
    const pluginRoot = manifestPath.replace(/\/manifest\.json$/, '')
    const frontendPath = `${pluginRoot}/${manifest.frontend}`
    return [manifest.view, viewModules[frontendPath] ?? null]
  }),
)
