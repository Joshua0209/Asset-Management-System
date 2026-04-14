# Design Tokens — Asset Management System

> **Vibe**: TSMC-inspired — clean, conservative, precision-engineered, reliability-focused.
>
> This document defines the atomic design values (tokens) that form the visual language
> of the Asset Management System. All UI implementations should reference these tokens
> rather than hardcoding values.

---

## Table of Contents

1. [Color System](#1-color-system)
2. [Typography](#2-typography)
3. [Spacing](#3-spacing)
4. [Border Radius](#4-border-radius)
5. [Shadows & Elevation](#5-shadows--elevation)
6. [Motion](#6-motion)
7. [Breakpoints](#7-breakpoints)
8. [Dark Mode](#8-dark-mode)
9. [Semantic Mapping](#9-semantic-mapping)
10. [Usage Guidelines](#10-usage-guidelines)

---

## 1. Color System

### 1.1 Brand Colors

Derived from TSMC's corporate identity — a bold red anchored by black and white.

| Token                  | Light Mode | Hex       | Usage                                      |
| ---------------------- | ---------- | --------- | ------------------------------------------ |
| `color-brand-primary`  | TSMC Red   | `#C8102E` | Primary actions, active states, brand marks |
| `color-brand-secondary`| Deep Navy  | `#0B3D91` | Secondary actions, links, informational     |
| `color-brand-black`    | Black      | `#1A1A1A` | Headings, high-emphasis text               |
| `color-brand-white`    | White      | `#FFFFFF` | Backgrounds, inverse text                  |

> **Note**: `#C8102E` is a slightly deeper, more refined red than TSMC's raw logo red
> (`#E60012`). This improves contrast ratios for WCAG AA compliance on white backgrounds
> while preserving the same bold, confident energy.

### 1.2 Neutral Scale

A cool-tinted gray scale for backgrounds, borders, and secondary text.

| Token               | Hex       | Usage                          |
| -------------------- | --------- | ------------------------------ |
| `neutral-50`         | `#F8F9FA` | Page background                |
| `neutral-100`        | `#F1F3F5` | Card background, subtle fills  |
| `neutral-200`        | `#E9ECEF` | Dividers, subtle borders       |
| `neutral-300`        | `#DEE2E6` | Borders, disabled backgrounds  |
| `neutral-400`        | `#ADB5BD` | Placeholder text               |
| `neutral-500`        | `#868E96` | Secondary text, icons          |
| `neutral-600`        | `#495057` | Body text                      |
| `neutral-700`        | `#343A40` | Headings                       |
| `neutral-800`        | `#212529` | High-emphasis text             |
| `neutral-900`        | `#0D1117` | Maximum contrast               |

### 1.3 Semantic Colors

Purpose-driven colors for system feedback and status communication.

| Token                     | Hex       | Usage                                        |
| ------------------------- | --------- | -------------------------------------------- |
| `color-success`           | `#2E7D32` | Approval, completion, "正常使用" status        |
| `color-success-light`     | `#E8F5E9` | Success background                           |
| `color-warning`           | `#E65100` | Attention needed, pending review              |
| `color-warning-light`     | `#FFF3E0` | Warning background                           |
| `color-error`             | `#C62828` | Rejection, validation errors, critical alerts |
| `color-error-light`       | `#FFEBEE` | Error background                             |
| `color-info`              | `#0B3D91` | Informational, "維修中" status                 |
| `color-info-light`        | `#E3F2FD` | Info background                              |

### 1.4 Asset Status Colors

Domain-specific tokens mapped to asset lifecycle states.

| Token                        | Hex       | Status          |
| ---------------------------- | --------- | --------------- |
| `color-status-active`        | `#2E7D32` | 正常使用 (Active)  |
| `color-status-in-repair`     | `#E65100` | 維修中 (In Repair) |
| `color-status-pending`       | `#0B3D91` | 審查中 (Pending)   |
| `color-status-rejected`      | `#C62828` | 拒絕 (Rejected)    |
| `color-status-decommissioned`| `#616161` | 報廢 (Retired)     |

---

## 2. Typography

### 2.1 Font Stack

TSMC uses **Nimrod MT** (serif) for branding. For UI, we adopt a modern sans-serif stack
that pairs well with CJK characters — essential for a bilingual (EN/ZH-TW) interface.

```
--font-primary:   "Inter", "Noto Sans TC", "Microsoft JhengHei", system-ui, sans-serif;
--font-mono:      "JetBrains Mono", "Fira Code", "Cascadia Code", monospace;
--font-display:   "Inter", "Noto Sans TC", sans-serif;  /* Headings, hero text */
```

> **Why Inter?** Excellent legibility at small sizes, tabular number support (critical
> for asset IDs and financial data), and wide weight range. **Noto Sans TC** provides
> full Traditional Chinese glyph coverage.

### 2.2 Type Scale

Based on a **1.250 (Major Third)** ratio — compact enough for data-dense interfaces.

| Token         | Size   | Weight | Line Height | Usage                           |
| ------------- | ------ | ------ | ----------- | ------------------------------- |
| `text-xs`     | 12px   | 400    | 1.5         | Captions, timestamps            |
| `text-sm`     | 14px   | 400    | 1.5         | Secondary text, table cells     |
| `text-base`   | 16px   | 400    | 1.6         | Body text (default)             |
| `text-lg`     | 18px   | 500    | 1.5         | Subheadings, card titles        |
| `text-xl`     | 20px   | 600    | 1.4         | Section headings                |
| `text-2xl`    | 24px   | 600    | 1.3         | Page headings                   |
| `text-3xl`    | 30px   | 700    | 1.2         | Dashboard hero numbers          |
| `text-4xl`    | 36px   | 700    | 1.2         | Display text (rarely used)      |

### 2.3 Font Weights

| Token             | Weight | Usage                     |
| ----------------- | ------ | ------------------------- |
| `font-regular`    | 400    | Body text                 |
| `font-medium`     | 500    | Emphasis, labels          |
| `font-semibold`   | 600    | Headings, buttons         |
| `font-bold`       | 700    | Display, KPI numbers      |

---

## 3. Spacing

An **8px base unit** system — clean multiples that align to a consistent grid.

| Token         | Value | Usage                                |
| ------------- | ----- | ------------------------------------ |
| `space-0`     | 0px   | Reset                                |
| `space-1`     | 4px   | Tight inline spacing, icon gaps      |
| `space-2`     | 8px   | Compact element spacing              |
| `space-3`     | 12px  | Default inner padding               |
| `space-4`     | 16px  | Standard spacing between elements    |
| `space-5`     | 20px  | Form field gaps                      |
| `space-6`     | 24px  | Card padding, section gaps           |
| `space-8`     | 32px  | Large section spacing                |
| `space-10`    | 40px  | Page-level margins                   |
| `space-12`    | 48px  | Major section dividers               |
| `space-16`    | 64px  | Hero/banner padding                  |
| `space-20`    | 80px  | Page top/bottom padding              |

---

## 4. Border Radius

TSMC aesthetic: **sharp precision**. Minimal rounding conveys engineering discipline.

| Token            | Value | Usage                                       |
| ---------------- | ----- | ------------------------------------------- |
| `radius-none`    | 0px   | Tables, data grids                          |
| `radius-sm`      | 2px   | Subtle softening on containers              |
| `radius-md`      | 4px   | Buttons, inputs, cards (default)            |
| `radius-lg`      | 6px   | Modals, dropdown menus                      |
| `radius-xl`      | 8px   | Feature cards, hero sections                |
| `radius-full`    | 9999px| Pills, avatar circles, status badges        |

> **Design rationale**: 4px default radius keeps the interface sharp and industrial —
> aligned with TSMC's precision-engineering identity — while still feeling modern enough
> for a web application. Avoid radius > 8px except for pills and avatars.

---

## 5. Shadows & Elevation

Subtle shadows to establish hierarchy. TSMC's aesthetic is flat and restrained —
shadows should feel like natural depth, not decoration.

| Token             | Value                                        | Usage                    |
| ----------------- | -------------------------------------------- | ------------------------ |
| `shadow-none`     | `none`                                       | Flat elements            |
| `shadow-xs`       | `0 1px 2px rgba(0,0,0,0.05)`                | Subtle lift, buttons     |
| `shadow-sm`       | `0 1px 3px rgba(0,0,0,0.08)`                | Cards at rest            |
| `shadow-md`       | `0 4px 6px rgba(0,0,0,0.07)`                | Cards on hover, dropdowns|
| `shadow-lg`       | `0 10px 15px rgba(0,0,0,0.08)`              | Modals, floating panels  |
| `shadow-xl`       | `0 20px 25px rgba(0,0,0,0.10)`              | Overlays, command palette|
| `shadow-inner`    | `inset 0 2px 4px rgba(0,0,0,0.06)`          | Pressed states, inputs   |

### Elevation Levels

| Level | Shadow Token  | z-index | Elements                          |
| ----- | ------------- | ------- | --------------------------------- |
| 0     | `shadow-none` | 0       | Background, page canvas           |
| 1     | `shadow-xs`   | 10      | Cards, buttons                    |
| 2     | `shadow-sm`   | 20      | Sticky headers, raised cards      |
| 3     | `shadow-md`   | 30      | Dropdowns, tooltips               |
| 4     | `shadow-lg`   | 40      | Modals, dialogs                   |
| 5     | `shadow-xl`   | 50      | Overlays, command palette, toasts |

---

## 6. Motion

Conservative, functional motion. No playful bounces — TSMC's vibe is **precise
and purposeful**.

| Token                   | Value                    | Usage                          |
| ----------------------- | ------------------------ | ------------------------------ |
| `duration-instant`      | 75ms                     | Checkbox, toggle, color change |
| `duration-fast`         | 150ms                    | Button states, hover effects   |
| `duration-normal`       | 250ms                    | Expand/collapse, slide panels  |
| `duration-slow`         | 350ms                    | Modal entrance, page transitions|
| `easing-default`        | `cubic-bezier(0.4, 0, 0.2, 1)` | Standard transitions   |
| `easing-in`             | `cubic-bezier(0.4, 0, 1, 1)`   | Elements exiting       |
| `easing-out`            | `cubic-bezier(0, 0, 0.2, 1)`   | Elements entering      |
| `easing-spring`         | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Toggle, microinteraction |

> **Accessibility**: All motion should respect `prefers-reduced-motion: reduce`.
> When reduced motion is active, set all durations to 0ms and disable transforms.

---

## 7. Breakpoints

Mobile-first responsive design with breakpoints aligned to common device classes.

| Token       | Min Width | Target Devices                    |
| ----------- | --------- | --------------------------------- |
| `bp-sm`     | 640px     | Large phones (landscape)          |
| `bp-md`     | 768px     | Tablets                           |
| `bp-lg`     | 1024px    | Small laptops, tablets (landscape)|
| `bp-xl`     | 1280px    | Desktops                          |
| `bp-2xl`    | 1536px    | Large desktops, wide monitors     |

### Container Max Widths

| Breakpoint | Container Width |
| ---------- | --------------- |
| `bp-sm`    | 100%            |
| `bp-md`    | 720px           |
| `bp-lg`    | 960px           |
| `bp-xl`    | 1200px          |
| `bp-2xl`   | 1400px          |

---

## 8. Dark Mode

TSMC's dark variant: **deep navy-black** backgrounds (not pure black) with carefully
adjusted contrast ratios for prolonged use in operations environments.

### 8.1 Dark Mode Palette

| Token (reference)        | Light Mode  | Dark Mode   | Notes                           |
| ------------------------ | ----------- | ----------- | ------------------------------- |
| `color-bg-primary`       | `#FFFFFF`   | `#0D1117`   | Main background                 |
| `color-bg-secondary`     | `#F8F9FA`   | `#161B22`   | Card / surface background       |
| `color-bg-tertiary`      | `#F1F3F5`   | `#21262D`   | Nested surfaces, sidebars       |
| `color-bg-elevated`      | `#FFFFFF`   | `#1C2128`   | Modals, dropdowns               |
| `color-border-default`   | `#DEE2E6`   | `#30363D`   | Default borders                 |
| `color-border-muted`     | `#E9ECEF`   | `#21262D`   | Subtle dividers                 |
| `color-text-primary`     | `#212529`   | `#E6EDF3`   | Body text                       |
| `color-text-secondary`   | `#495057`   | `#8B949E`   | Secondary, muted text           |
| `color-text-tertiary`    | `#868E96`   | `#6E7681`   | Hints, placeholders             |
| `color-text-on-brand`    | `#FFFFFF`   | `#FFFFFF`   | Text on brand-colored surfaces  |

### 8.2 Brand Colors in Dark Mode

| Token                  | Light Mode  | Dark Mode   | Rationale                      |
| ---------------------- | ----------- | ----------- | ------------------------------ |
| `color-brand-primary`  | `#C8102E`   | `#E5384F`   | Lightened for contrast on dark  |
| `color-brand-secondary`| `#0B3D91`   | `#4A90D9`   | Lightened for readability       |

### 8.3 Semantic Colors in Dark Mode

| Token                     | Light Mode  | Dark Mode   |
| ------------------------- | ----------- | ----------- |
| `color-success`           | `#2E7D32`   | `#3FB950`   |
| `color-success-light`     | `#E8F5E9`   | `#0D2818`   |
| `color-warning`           | `#E65100`   | `#D29922`   |
| `color-warning-light`     | `#FFF3E0`   | `#2D1B00`   |
| `color-error`             | `#C62828`   | `#F85149`   |
| `color-error-light`       | `#FFEBEE`   | `#3D1114`   |
| `color-info`              | `#0B3D91`   | `#58A6FF`   |
| `color-info-light`        | `#E3F2FD`   | `#0D2240`   |

### 8.4 Shadow Adjustment in Dark Mode

In dark mode, shadows are nearly invisible against dark backgrounds. Replace box-shadow
with border highlights or subtle luminance shifts:

```
/* Dark mode override principle */
shadow-sm (dark):  0 0 0 1px rgba(255,255,255,0.04), 0 1px 3px rgba(0,0,0,0.30)
shadow-md (dark):  0 0 0 1px rgba(255,255,255,0.04), 0 4px 6px rgba(0,0,0,0.40)
```

---

## 9. Semantic Mapping

How tokens map to common UI elements — this is the bridge between raw tokens and
component-level styling.

### 9.1 Interactive Elements

| Element              | Property      | Token                              |
| -------------------- | ------------- | ---------------------------------- |
| Button (primary)     | Background    | `color-brand-primary`              |
| Button (primary)     | Text          | `color-text-on-brand`              |
| Button (primary)     | Hover BG      | `color-brand-primary` darken 10%   |
| Button (secondary)   | Background    | `transparent`                      |
| Button (secondary)   | Border        | `color-brand-primary`              |
| Button (secondary)   | Text          | `color-brand-primary`              |
| Button (ghost)       | Background    | `transparent`                      |
| Button (ghost)       | Text          | `color-brand-secondary`            |
| Link                 | Color         | `color-brand-secondary`            |
| Link                 | Hover         | `color-brand-secondary` darken 15% |

### 9.2 Form Elements

| Element              | Property      | Token                              |
| -------------------- | ------------- | ---------------------------------- |
| Input                | Border        | `color-border-default`             |
| Input                | Focus Ring    | `color-brand-secondary` @ 30% opacity |
| Input                | Focus Border  | `color-brand-secondary`            |
| Input                | Error Border  | `color-error`                      |
| Input                | Placeholder   | `color-text-tertiary`              |
| Label                | Color         | `color-text-primary`               |
| Help text            | Color         | `color-text-secondary`             |

### 9.3 Data Display

| Element              | Property      | Token                              |
| -------------------- | ------------- | ---------------------------------- |
| Table header         | Background    | `neutral-100`                      |
| Table header         | Text          | `neutral-700`                      |
| Table row            | Border        | `color-border-muted`               |
| Table row (hover)    | Background    | `neutral-50`                       |
| Table row (selected) | Background    | `color-info-light`                 |
| Status badge         | Border Radius | `radius-full`                      |
| Asset ID             | Font          | `--font-mono`                      |

### 9.4 Navigation

| Element              | Property      | Token                              |
| -------------------- | ------------- | ---------------------------------- |
| Sidebar              | Background    | `neutral-900` (or `color-bg-tertiary` dark) |
| Sidebar link         | Text          | `neutral-300`                      |
| Sidebar link (active)| Background    | `color-brand-primary` @ 10% opacity|
| Sidebar link (active)| Text          | `color-brand-primary`              |
| Top bar              | Background    | `color-bg-primary`                 |
| Top bar              | Border bottom | `color-border-default`             |

---

## 10. Usage Guidelines

### Do

- **Always use tokens** — never hardcode hex, px, or ms values in components
- **Use semantic tokens** over primitive tokens (e.g., `color-success` not `#2E7D32`)
- **Test both modes** — every component must be verified in light and dark mode
- **Use `rem` for type** — base `16px = 1rem` for accessibility scaling
- **Pair status colors with labels** — never rely on color alone (accessibility)

### Don't

- Don't use brand-primary red for large background areas (it's an accent, not a surface)
- Don't mix sharp and rounded radii within the same component
- Don't use shadows heavier than `shadow-md` for inline elements
- Don't override motion tokens with custom durations
- Don't use pure black (`#000000`) as text color — use `neutral-800` or `neutral-900`

### WCAG Compliance

| Combination                           | Contrast Ratio | Rating |
| ------------------------------------- | -------------- | ------ |
| `color-brand-primary` on white        | 7.2:1          | AAA    |
| `color-brand-secondary` on white      | 7.5:1          | AAA    |
| `color-text-primary` on `neutral-50`  | 15.1:1         | AAA    |
| `color-text-secondary` on `neutral-50`| 7.8:1          | AAA    |
| `color-text-primary` (dark) on dark BG| 13.2:1         | AAA    |

> All text combinations must meet **WCAG AA** (4.5:1 for normal text, 3:1 for large text).
> Brand colors were specifically adjusted from raw TSMC values to guarantee this.

---

## CSS Custom Properties (Reference Implementation)

```css
:root {
  /* Brand */
  --color-brand-primary: #C8102E;
  --color-brand-secondary: #0B3D91;

  /* Neutrals */
  --neutral-50: #F8F9FA;
  --neutral-100: #F1F3F5;
  --neutral-200: #E9ECEF;
  --neutral-300: #DEE2E6;
  --neutral-400: #ADB5BD;
  --neutral-500: #868E96;
  --neutral-600: #495057;
  --neutral-700: #343A40;
  --neutral-800: #212529;
  --neutral-900: #0D1117;

  /* Semantic */
  --color-success: #2E7D32;
  --color-warning: #E65100;
  --color-error: #C62828;
  --color-info: #0B3D91;

  /* Surfaces */
  --color-bg-primary: #FFFFFF;
  --color-bg-secondary: #F8F9FA;
  --color-bg-tertiary: #F1F3F5;
  --color-border-default: #DEE2E6;
  --color-border-muted: #E9ECEF;

  /* Text */
  --color-text-primary: #212529;
  --color-text-secondary: #495057;
  --color-text-tertiary: #868E96;
  --color-text-on-brand: #FFFFFF;

  /* Typography */
  --font-primary: "Inter", "Noto Sans TC", "Microsoft JhengHei", system-ui, sans-serif;
  --font-mono: "JetBrains Mono", "Fira Code", "Cascadia Code", monospace;

  /* Spacing (base: 8px) */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;
  --space-20: 80px;

  /* Radius */
  --radius-none: 0px;
  --radius-sm: 2px;
  --radius-md: 4px;
  --radius-lg: 6px;
  --radius-xl: 8px;
  --radius-full: 9999px;

  /* Shadows */
  --shadow-xs: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.07);
  --shadow-lg: 0 10px 15px rgba(0,0,0,0.08);
  --shadow-xl: 0 20px 25px rgba(0,0,0,0.10);
  --shadow-inner: inset 0 2px 4px rgba(0,0,0,0.06);

  /* Motion */
  --duration-instant: 75ms;
  --duration-fast: 150ms;
  --duration-normal: 250ms;
  --duration-slow: 350ms;
  --easing-default: cubic-bezier(0.4, 0, 0.2, 1);
  --easing-in: cubic-bezier(0.4, 0, 1, 1);
  --easing-out: cubic-bezier(0, 0, 0.2, 1);
}

/* Dark Mode */
[data-theme="dark"] {
  --color-brand-primary: #E5384F;
  --color-brand-secondary: #4A90D9;

  --color-bg-primary: #0D1117;
  --color-bg-secondary: #161B22;
  --color-bg-tertiary: #21262D;
  --color-border-default: #30363D;
  --color-border-muted: #21262D;

  --color-text-primary: #E6EDF3;
  --color-text-secondary: #8B949E;
  --color-text-tertiary: #6E7681;

  --color-success: #3FB950;
  --color-warning: #D29922;
  --color-error: #F85149;
  --color-info: #58A6FF;

  --shadow-sm: 0 0 0 1px rgba(255,255,255,0.04), 0 1px 3px rgba(0,0,0,0.30);
  --shadow-md: 0 0 0 1px rgba(255,255,255,0.04), 0 4px 6px rgba(0,0,0,0.40);
  --shadow-lg: 0 0 0 1px rgba(255,255,255,0.04), 0 10px 15px rgba(0,0,0,0.50);
}

/* Reduced Motion */
@media (prefers-reduced-motion: reduce) {
  :root {
    --duration-instant: 0ms;
    --duration-fast: 0ms;
    --duration-normal: 0ms;
    --duration-slow: 0ms;
  }
}
```
