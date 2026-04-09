export const colors = {
  primary: '#201d1d',
  primaryLight: '#fdfcfc',
  surface: '#302c2c',
  lightSurface: '#f1eeee',
  inputBg: '#f8f7f7',
  accent: '#007aff',
  accentHover: '#0056b3',
  danger: '#ff3b30',
  dangerHover: '#d70015',
  success: '#30d158',
  warning: '#ff9f0a',
  warningHover: '#cc7f08',
  textPrimary: '#fdfcfc',
  textSecondary: '#9a9898',
  textSecondaryLight: '#424245',
  textMuted: '#6e6e73',
  border: 'rgba(15, 0, 0, 0.12)',
  borderStrong: '#646262',
  borderTab: '#9a9898',
} as const

export const spacing = {
  1: '4px', 2: '8px', 3: '12px', 4: '16px',
  5: '20px', 6: '24px', 8: '32px', 10: '40px',
  12: '48px', 16: '64px', 20: '80px', 24: '96px',
} as const

export const radius = {
  default: '4px',
  input: '6px',
} as const

export const typography = {
  fontFamily: "'Berkeley Mono', 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
  heading: { size: '38px', weight: 700 },
  body: { size: '16px', weight: 400 },
  caption: { size: '14px', weight: 400 },
} as const
