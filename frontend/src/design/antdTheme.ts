import type { ThemeConfig } from "antd";

import designTokens from "../../../docs/designs/design-tokens.json";

type TokenLeaf<T = string> = {
  $value: T;
};

type ShadowValue =
  | {
      offsetX: string;
      offsetY: string;
      blur: string;
      spread?: string;
      color: string;
      inset?: boolean;
    }
  | Array<{
      offsetX: string;
      offsetY: string;
      blur: string;
      spread?: string;
      color: string;
      inset?: boolean;
    }>;

const tokens = designTokens as unknown as {
  color: {
    brand: Record<string, TokenLeaf>;
    neutral: Record<string, TokenLeaf>;
    semantic: Record<string, TokenLeaf>;
    status: Record<string, TokenLeaf>;
    surface: Record<string, TokenLeaf>;
    border: Record<string, TokenLeaf>;
    text: Record<string, TokenLeaf>;
  };
  "color-dark": {
    brand: Record<string, TokenLeaf>;
    semantic: Record<string, TokenLeaf>;
    surface: Record<string, TokenLeaf>;
    border: Record<string, TokenLeaf>;
    text: Record<string, TokenLeaf>;
  };
  "font-family": Record<string, TokenLeaf<string[]>>;
  "font-size": Record<string, TokenLeaf>;
  "line-height": Record<string, TokenLeaf<number>>;
  spacing: Record<string, TokenLeaf>;
  radius: Record<string, TokenLeaf>;
  shadow: Record<string, TokenLeaf<ShadowValue>>;
  "shadow-dark": Partial<Record<string, TokenLeaf<ShadowValue>>>;
  duration: Record<string, TokenLeaf>;
  easing: Record<string, TokenLeaf<number[]>>;
  layout: Record<string, TokenLeaf>;
  density: Record<string, TokenLeaf>;
};

const value = <T,>(token: TokenLeaf<T>): T => token.$value;

const pxNumber = (dimension: string): number => {
  if (dimension.endsWith("rem")) {
    return Number.parseFloat(dimension) * 16;
  }
  return Number.parseFloat(dimension);
};

const fontFamily = (name: keyof typeof tokens["font-family"]) =>
  value(tokens["font-family"][name]).join(", ");

const shadowLayerToCss = (shadow: Exclude<ShadowValue, unknown[]>): string =>
  [
    shadow.inset ? "inset" : "",
    shadow.offsetX,
    shadow.offsetY,
    shadow.blur,
    shadow.spread ?? "",
    shadow.color,
  ]
    .filter(Boolean)
    .join(" ");

const shadowToCss = (shadow: ShadowValue): string =>
  Array.isArray(shadow)
    ? shadow.map((layer) => shadowLayerToCss(layer)).join(", ")
    : shadowLayerToCss(shadow);

const lightThemeTokens = {
  brand: tokens.color.brand,
  semantic: tokens.color.semantic,
  surface: tokens.color.surface,
  border: tokens.color.border,
  text: tokens.color.text,
};

const darkThemeTokens = {
  brand: { ...tokens.color.brand, ...tokens["color-dark"].brand },
  semantic: { ...tokens.color.semantic, ...tokens["color-dark"].semantic },
  surface: { ...tokens.color.surface, ...tokens["color-dark"].surface },
  border: { ...tokens.color.border, ...tokens["color-dark"].border },
  text: { ...tokens.color.text, ...tokens["color-dark"].text },
};

export const getAntdTheme = (isDarkMode: boolean): ThemeConfig => {
  const colorTokens = isDarkMode ? darkThemeTokens : lightThemeTokens;

  return {
    cssVar: { prefix: "ams" },
    token: {
      colorPrimary: value(colorTokens.brand.primary),
      colorInfo: value(colorTokens.semantic.info),
      colorSuccess: value(colorTokens.semantic.success),
      colorWarning: value(colorTokens.semantic.warning),
      colorError: value(colorTokens.semantic.error),
      colorLink: value(colorTokens.brand.secondary),
      colorTextBase: value(colorTokens.text.primary),
      colorBgBase: value(colorTokens.surface["bg-primary"]),
      fontFamily: fontFamily("primary"),
      fontFamilyCode: fontFamily("mono"),
      fontSize: pxNumber(value(tokens["font-size"].sm)),
      lineHeight: value(tokens["line-height"].normal),
      borderRadius: pxNumber(value(tokens.radius.md)),
      controlHeight: pxNumber(value(tokens.density.compact)),
      sizeUnit: 4,
      sizeStep: 4,
      wireframe: false,
    },
    components: {
      Layout: {
        bodyBg: value(colorTokens.surface["bg-secondary"]),
        headerBg: value(colorTokens.surface["bg-primary"]),
        siderBg: value(isDarkMode ? tokens["color-dark"].surface["bg-secondary"] : tokens.color.neutral[900]),
        triggerBg: value(tokens.color.neutral[800]),
        triggerColor: value(tokens.color.brand.white),
      },
      Card: {
        headerBg: value(colorTokens.surface["bg-elevated"]),
      },
      Table: {
        headerBg: value(tokens.color.neutral[100]),
        headerColor: value(tokens.color.neutral[700]),
        rowHoverBg: value(colorTokens.surface["bg-secondary"]),
        borderColor: value(colorTokens.border.muted),
      },
      Menu: {
        itemSelectedColor: value(colorTokens.brand.primary),
        itemSelectedBg: isDarkMode ? "rgb(229 56 79 / 0.12)" : "rgb(200 16 46 / 0.08)",
      },
      Segmented: {
        itemSelectedBg: value(colorTokens.brand.primary),
        itemSelectedColor: value(tokens.color.text["on-brand"]),
      },
    },
  };
};

export const getDesignCssVariables = (isDarkMode: boolean): Record<string, string> => {
  const colorTokens = isDarkMode ? darkThemeTokens : lightThemeTokens;
  const shadowTokens = isDarkMode ? tokens["shadow-dark"] : tokens.shadow;

  return {
    "--color-brand-primary": value(colorTokens.brand.primary),
    "--color-brand-secondary": value(colorTokens.brand.secondary),
    "--color-bg-primary": value(colorTokens.surface["bg-primary"]),
    "--color-bg-secondary": value(colorTokens.surface["bg-secondary"]),
    "--color-bg-tertiary": value(colorTokens.surface["bg-tertiary"]),
    "--color-bg-elevated": value(colorTokens.surface["bg-elevated"]),
    "--color-border-default": value(colorTokens.border.default),
    "--color-border-muted": value(colorTokens.border.muted),
    "--color-border-strong": value(colorTokens.border.strong),
    "--color-text-primary": value(colorTokens.text.primary),
    "--color-text-secondary": value(colorTokens.text.secondary),
    "--color-text-tertiary": value(colorTokens.text.tertiary),
    "--color-text-on-brand": value(tokens.color.text["on-brand"]),
    "--font-family-primary": fontFamily("primary"),
    "--font-family-display": fontFamily("display"),
    "--font-family-mono": fontFamily("mono"),
    "--font-size-xs": value(tokens["font-size"].xs),
    "--font-size-sm": value(tokens["font-size"].sm),
    "--font-size-base": value(tokens["font-size"].base),
    "--font-size-xl": value(tokens["font-size"].xl),
    "--font-size-2xl": value(tokens["font-size"]["2xl"]),
    "--line-height-normal": String(value(tokens["line-height"].normal)),
    "--line-height-relaxed": String(value(tokens["line-height"].relaxed)),
    "--space-1": value(tokens.spacing[1]),
    "--space-2": value(tokens.spacing[2]),
    "--space-3": value(tokens.spacing[3]),
    "--space-4": value(tokens.spacing[4]),
    "--space-5": value(tokens.spacing[5]),
    "--space-6": value(tokens.spacing[6]),
    "--space-8": value(tokens.spacing[8]),
    "--radius-md": value(tokens.radius.md),
    "--radius-lg": value(tokens.radius.lg),
    "--radius-xl": value(tokens.radius.xl),
    "--radius-full": value(tokens.radius.full),
    "--shadow-xs": shadowToCss(value(shadowTokens.xs ?? tokens.shadow.xs)),
    "--shadow-sm": shadowToCss(value(shadowTokens.sm ?? tokens.shadow.sm)),
    "--shadow-md": shadowToCss(value(shadowTokens.md ?? tokens.shadow.md)),
    "--shadow-focus": shadowToCss(value(tokens.shadow.focus)),
    "--duration-fast": value(tokens.duration.fast),
    "--duration-normal": value(tokens.duration.normal),
    "--easing-default": `cubic-bezier(${value(tokens.easing.default).join(", ")})`,
    "--layout-sidebar-width": value(tokens.layout["sidebar-width"]),
    "--layout-topbar-height": value(tokens.layout["topbar-height"]),
  };
};

export const applyDesignCssVariables = (isDarkMode: boolean): void => {
  const root = document.documentElement;
  root.dataset.theme = isDarkMode ? "dark" : "light";
  Object.entries(getDesignCssVariables(isDarkMode)).forEach(([name, tokenValue]) => {
    root.style.setProperty(name, tokenValue);
  });
};
