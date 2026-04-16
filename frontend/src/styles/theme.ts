import type { ThemeConfig } from 'antd';
import { colors, typography, borderRadius } from './tokens';

/**
 * Ant Design theme configuration mapped from project design tokens.
 * Used in <ConfigProvider theme={theme}> to override Ant Design defaults.
 */
const theme: ThemeConfig = {
  token: {
    // Brand colors
    colorPrimary: colors.brand.primary,
    colorLink: colors.brand.secondary,
    colorSuccess: colors.semantic.success,
    colorWarning: colors.semantic.warning,
    colorError: colors.semantic.error,
    colorInfo: colors.semantic.info,

    // Typography
    fontFamily: typography.fontFamily.sans,
    fontFamilyCode: typography.fontFamily.mono,
    fontSize: typography.fontSize.base,

    // Border radius
    borderRadius: borderRadius.base,
    borderRadiusLG: borderRadius.lg,
    borderRadiusSM: borderRadius.sm,

    // Layout
    colorBgLayout: colors.neutral[50],
    colorBgContainer: '#ffffff',
    colorBorderSecondary: colors.neutral[200],
  },
  components: {
    Layout: {
      siderBg: '#ffffff',
      headerBg: '#ffffff',
      bodyBg: colors.neutral[50],
    },
    Menu: {
      itemBg: 'transparent',
      itemSelectedBg: colors.semantic.infoBg,
      itemSelectedColor: colors.brand.primary,
    },
  },
};

export default theme;
