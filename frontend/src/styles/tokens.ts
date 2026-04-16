/**
 * Design tokens extracted from docs/system-design/13-design-tokens.md
 * Single source of truth for all visual constants.
 */

// ─── Colors ───────────────────────────────────────────────────────────────────

export const colors = {
  brand: {
    primary: '#C8102E',
    primaryHover: '#A30D25',
    primaryActive: '#7F091C',
    secondary: '#0B3D91',
    secondaryHover: '#093174',
    secondaryActive: '#072558',
  },

  semantic: {
    success: '#2E7D32',
    successBg: '#E8F5E9',
    warning: '#E65100',
    warningBg: '#FFF3E0',
    error: '#C62828',
    errorBg: '#FFEBEE',
    info: '#0B3D91',
    infoBg: '#E3F2FD',
  },

  neutral: {
    50: '#F8F9FA',
    100: '#F1F3F5',
    200: '#E9ECEF',
    300: '#DEE2E6',
    400: '#CED4DA',
    500: '#ADB5BD',
    600: '#868E96',
    700: '#495057',
    800: '#343A40',
    900: '#212529',
    950: '#0D1117',
  },

  /** Asset status badge colors */
  assetStatus: {
    inStock: '#0B3D91',
    inUse: '#2E7D32',
    pendingRepair: '#E65100',
    underRepair: '#E65100',
    disposed: '#616161',
  },

  /** Repair request status badge colors */
  repairStatus: {
    pendingReview: '#0B3D91',
    underRepair: '#E65100',
    completed: '#2E7D32',
    rejected: '#C62828',
  },
} as const;

// ─── Typography ───────────────────────────────────────────────────────────────

export const typography = {
  fontFamily: {
    sans: "'Inter', 'Noto Sans TC', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    mono: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
  },

  fontSize: {
    xs: 12,
    sm: 14,
    base: 16,
    lg: 18,
    xl: 20,
    '2xl': 24,
    '3xl': 30,
    '4xl': 36,
  },

  fontWeight: {
    regular: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
  },

  lineHeight: {
    tight: 1.25,
    normal: 1.5,
    relaxed: 1.75,
  },
} as const;

// ─── Spacing (8px grid) ──────────────────────────────────────────────────────

export const spacing = {
  0: 0,
  1: 4,
  2: 8,
  3: 12,
  4: 16,
  5: 20,
  6: 24,
  8: 32,
  10: 40,
  12: 48,
  16: 64,
  20: 80,
} as const;

// ─── Border Radius ───────────────────────────────────────────────────────────

export const borderRadius = {
  none: 0,
  sm: 2,
  base: 4,
  md: 6,
  lg: 8,
  full: 9999,
} as const;

// ─── Shadows ─────────────────────────────────────────────────────────────────

export const shadows = {
  xs: '0 1px 2px rgba(0, 0, 0, 0.05)',
  sm: '0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06)',
  md: '0 4px 6px rgba(0, 0, 0, 0.07), 0 2px 4px rgba(0, 0, 0, 0.06)',
  lg: '0 10px 15px rgba(0, 0, 0, 0.1), 0 4px 6px rgba(0, 0, 0, 0.05)',
  xl: '0 20px 25px rgba(0, 0, 0, 0.1), 0 10px 10px rgba(0, 0, 0, 0.04)',
} as const;

// ─── Breakpoints ─────────────────────────────────────────────────────────────

export const breakpoints = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  '2xl': 1536,
} as const;

// ─── Motion ──────────────────────────────────────────────────────────────────

export const motion = {
  duration: {
    fast: '75ms',
    normal: '150ms',
    slow: '300ms',
    slower: '350ms',
  },
  easing: {
    default: 'cubic-bezier(0.4, 0, 0.2, 1)',
    in: 'cubic-bezier(0.4, 0, 1, 1)',
    out: 'cubic-bezier(0, 0, 0.2, 1)',
    inOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
  },
} as const;

// ─── Layout ──────────────────────────────────────────────────────────────────

export const layout = {
  sidebarWidth: 224,
  sidebarCollapsedWidth: 80,
  headerHeight: 56,
  contentMaxWidth: 1280,
  contentPadding: 24,
} as const;
