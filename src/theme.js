export const DEFAULT_APPEARANCE = Object.freeze({
  theme_name: 'midnight',
  theme_color: '#8b5cf6',
  background_color: '#0b1020',
  sidebar_color: '#0d1326',
  card_color: '#0f172a',
  card_hover_color: '#1e293b',
  primary_text_color: '#f8fafc',
  secondary_text_color: '#8894af',
  border_color: '#334155',
})

export function appearanceCssVariables(appearance) {
  return {
    '--theme-color': appearance.theme_color,
    '--background-color': appearance.background_color,
    '--sidebar-color': appearance.sidebar_color,
    '--card-color': appearance.card_color,
    '--card-hover-color': appearance.card_hover_color,
    '--primary-text-color': appearance.primary_text_color,
    '--secondary-text-color': appearance.secondary_text_color,
    '--border-color': appearance.border_color,
  }
}
