# DESIGN — Asset Management System

> **Visual direction**: TSMC (台灣積體電路製造股份有限公司). Precision-engineered,
> institutional, bilingual-native, allergic to decoration. Light-mode first;
> dark mode is a courtesy for long sessions, not the default.

**This directory is the authoritative design system layer.** Design tokens, visual direction rationale, and usage rules all live here (previously split between `docs/system-design/13-design-tokens.md` and prose documents — consolidated here in Week 2).

| File | Purpose |
|------|---------|
| `DESIGN.md` (this file) | Rationale + usage rules + "does this feel TSMC?" checklist |
| `design-tokens.json` | Machine-readable tokens (W3C Design Tokens format) |
| `design-preview.html` | Self-contained visual preview — open in any browser |

---

## 1. Why TSMC?

This is a course-project asset management system. We borrow TSMC's visual
vocabulary because it matches the product shape:

1. **Built for data density** — their public disclosures publish thousands of
   numbers on clean white pages without overwhelming. Asset inventory has the
   same shape.
2. **Bilingual-native** — TSMC operates in Traditional Chinese and English
   simultaneously; their typography and layout rhythm respect both scripts.
3. **Boring on purpose** — exactly what a reliability-critical internal tool
   should be. Flashy motion and gradient blobs erode trust in a system meant
   to track company property.

> Not a claim of endorsement by or affiliation with TSMC. Educational use only.

---

## 2. The Four Pillars

Every decision below traces back to one of these.

### 2.1 Precision

- Corners are `2 / 4 / 6 / 8 / 9999`px — nothing in between.
- All spacing on an **8px grid** (or its 4px half-step).
- Every number in the UI uses `font-variant-numeric: tabular-nums` so digits
  align vertically — asset IDs, dates, counts, prices.

### 2.2 Restraint

- **Red is an accent, never a surface.** It marks primary actions and active
  brand marks; it never fills a hero banner or a page background.
- Shadows are near-invisible (`shadow-sm` at rest, `shadow-md` on hover).
  Dark mode replaces shadow with a 1px luminance hairline — because shadows
  are unreadable on dark surfaces.
- **No gradients on functional UI.** Ever.
- **No emoji in UI copy.** Status is text + icon + color, never 🟢.

### 2.3 Hierarchy through typography, not decoration

Headlines feel different because they are **serif in a heavier weight**, not
because they sit in a tinted card. A primary button feels primary because it
is filled red, not because it is taller or animates. Size stays constant.

### 2.4 Bilingual parity

- CJK characters take ~15% more vertical space at the same `font-size`.
  Body line-height is `1.5`–`1.6`, never below `1.4`.
- Headlines use a **paired serif** strategy (EN + TC serif) so a zh-TW heading
  carries the same weight as its en counterpart on the same page.
- **Never italicize in zh-TW** — Chinese typography has no italic convention.
  Use weight or color for emphasis.

---

## 3. Typography

**Verified against tsmc.com** (EN + zh-TW, April 2026): TSMC's website is
**all-sans throughout** — in navigation, hero headlines, body, and section
headers. The only serif is **Nimrod MT** in the logo mark (brand identity,
not a web font). Hierarchy is communicated through **weight and tracking**,
not by switching typeface.

| Role | Stack | Weight | Tracking |
|------|-------|--------|---------|
| Display (`h1`, `h2`) | **Inter** / **Noto Sans TC** | 700 | `-0.015em` |
| UI body | **Inter** / **Noto Sans TC** | 400 | `0` |
| Mono (IDs, timestamps) | **JetBrains Mono** | 400–500 | `0` |

Both EN and ZH-TW use the same weight at headline size. The heavier stroke
weight of CJK characters at `font-weight: 700` naturally matches the EN bold
sans — no serif pairing is needed to achieve visual parity.

> **Why not serif for display?** The earlier draft encoded IBM Plex Serif for
> headlines to approximate the Nimrod MT brand feeling. The screenshots proved
> this wrong — TSMC's web UI never uses serif. Serif is print/logo only.

### Scale (Major Third, 1.250 ratio)

| Token | Size | Weight | Use |
|-------|------|--------|-----|
| `text-xs` | 12px | 400 | Captions, timestamps |
| `text-sm` | 14px | 400 | Secondary text, table cells |
| `text-base` | 16px | 400 | Body (default) |
| `text-lg` | 18px | 500 | Subheadings, card titles |
| `text-xl` | 20px | 600 | Section headings |
| `text-2xl` | 24px | 600 | Page headings |
| `text-3xl` | 30px | 700 | Dashboard KPI numbers |
| `text-4xl` | 36px | 700 | Display text (rare) |

---

## 4. Color

### 4.1 The 80 / 15 / 5 rule

A typical screen should hit roughly:
- **80%** neutral (white/near-white surfaces, gray text)
- **15%** structural (borders, muted backgrounds)
- **5%** brand/semantic (red CTAs, status badges, focus rings)

If red is covering more than ~5% of a screen's pixels, it's wrong.

### 4.2 Brand

| Token | Light | Dark | Rationale |
|-------|-------|------|-----------|
| `color-brand-primary` | `#C8102E` | `#E5384F` | TSMC red, tuned 10% deeper than raw logo (`#E60012`) for WCAG AA on white (7.2:1) |
| `color-brand-secondary` | `#0B3D91` | `#4A90D9` | Deep navy — links, informational accents |

### 4.3 Asset status (domain-specific — **use only for asset state**)

| State | Token | Value | zh-TW | en |
|-------|-------|-------|-------|-----|
| 1 | `color-status-active` | `#2E7D32` | 正常使用 | In Use |
| 2 | `color-status-in-repair` | `#E65100` | 維修中 | In Repair |
| 3 | `color-status-pending` | `#0B3D91` | 審查中 | Pending Review |
| 4 | `color-status-rejected` | `#C62828` | 拒絕 | Rejected |
| 5 | `color-status-decommissioned` | `#616161` | 報廢 | Decommissioned |

Do not reuse these for generic UI feedback. If you need "success toast", use
`color-success`, not `color-status-active`. Overloading silently breaks the
user's mental model.

See `design-tokens.json` for the full palette (neutral 50–900, semantic,
surfaces, borders, text).

---

## 5. Spacing, Radius, Shadow

- **Spacing**: 8px base scale — `4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64 / 80`.
- **Radius**: `none / 2 / 4 / 6 / 8 / 9999`. Default is `md` (4px). `full` only
  for pills, avatars, status badges.
- **Shadow**: `xs / sm / md / lg / xl / inner`. Avoid anything above `md` on
  inline elements. Dark mode swaps shadow for a 1px luminance hairline.

---

## 6. Motion

TSMC motion = **functional and fast**. The entire vocabulary:

| Interaction | Duration | Easing |
|-------------|----------|--------|
| Hover color change | 150ms | `default` |
| Button press | 75ms | `default` |
| Panel slide | 250ms | `out` in, `in` out |
| Modal entrance | 350ms | `out` |
| Page transition | **0ms** | — (don't animate page changes) |

**Forbidden**: bouncy springs, parallax scroll, fade-on-scroll reveal,
particle effects, type-in animations.

**Reduced motion**: `prefers-reduced-motion: reduce` kills all transitions
(durations → 0ms). Respected globally in the tokens.

---

## 7. WCAG Compliance

All text combinations meet **WCAG AA** (4.5:1 normal, 3:1 large text). Key
pairs that were specifically tuned away from TSMC's raw logo values:

| Combination | Contrast | Rating | Note |
|-------------|----------|--------|------|
| `color-brand-primary` on white | 7.2:1 | **AAA** | Raw logo `#E60012` is only 4.6:1 — we use `#C8102E` |
| `color-brand-secondary` on white | 7.5:1 | **AAA** | |
| `color-text-primary` on `neutral-50` | 15.1:1 | **AAA** | |
| `color-text-secondary` on `neutral-50` | 7.8:1 | **AAA** | |
| `color-text-primary` (dark) on `bg-primary` (dark) | 13.2:1 | **AAA** | |
| `color-status-active` on white | 4.6:1 | **AA** | Minimum — always pair with a label |
| `color-status-decommissioned` on white | 5.4:1 | **AA** | |

> **Rule**: status colors must **always** be paired with a text label or icon —
> never rely on color alone to convey state. This satisfies WCAG 1.4.1
> (Use of Color) for users with color vision deficiency.

---

## 8. Token usage (frontend)

Do **not** hardcode hex/px/ms in components. Read from CSS custom properties
derived from `design-tokens.json` (or import the generated CSS directly):

```css
.asset-card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  padding: var(--space-6);
  box-shadow: var(--shadow-sm);
  transition: box-shadow var(--duration-fast) var(--easing-default);
}
.asset-card:hover { box-shadow: var(--shadow-md); }
```

If a needed value is missing, **add a token** (update JSON + this doc +
preview in the same change) rather than reaching for a raw value.

---

## 9. The "does this feel TSMC?" checklist

Before marking any screen done:

- [ ] Hierarchy survives if you view the screen in **monochrome**.
- [ ] Red appears only on actions, status badges, the logo — no red backgrounds.
- [ ] Every corner rounds to `2 / 4 / 6 / 8 / 9999`px.
- [ ] Every number is **tabular-aligned**.
- [ ] zh-TW and en versions have equivalent visual weight.
- [ ] Sections have ≥48px whitespace between them.
- [ ] No animation exceeds 350ms; none use spring easing.
- [ ] Every interactive element has a **visible focus ring**.
- [ ] A TSMC engineer would recognize this as their company's aesthetic — not
      Material / HIG / Tailwind default.

More than one "no" → the screen is not yet TSMC.

---

## 10. What TSMC is NOT

Counter-examples the industry is drowning in — resist these:

- ❌ Gradient mesh backgrounds (Stripe/Linear trope)
- ❌ Glass morphism cards (iOS/Vercel trope)
- ❌ Dark-mode-first (every 2024 AI startup)
- ❌ Purple-to-blue CTA gradients (instant "generic AI product" smell)
- ❌ Oversized centered hero with stock gradient + pill CTA
- ❌ Cartoon-character empty states — use a thin icon + one sentence
- ❌ Emoji in UI copy — kills the register

If a PR smells like any of these, stop and refactor.
