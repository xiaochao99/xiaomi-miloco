/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

// Ant Design theme config
import { theme } from 'antd';

// dark theme config
export const darkTheme = {
  algorithm: theme.darkAlgorithm,
  token: {
    // primary color
    colorPrimary: 'rgba(255, 255, 255, 1)',
    colorPrimaryHover: 'rgba(255, 255, 255, 0.14)',
    colorPrimaryActive: 'rgba(255, 255, 255, 0.14)',

    // border radius
    borderRadius: 6,
    borderRadiusLG: 8,
    borderRadiusSM: 4,
    borderRadiusXS: 2,

    // shadows
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.3)',
    boxShadowSecondary: '0 1px 4px rgba(0, 0, 0, 0.2)',
    boxShadowTertiary: '0 4px 16px rgba(0, 0, 0, 0.4)',

    // font family
    fontFamily: "'MiSans', system-ui, Avenir, Helvetica, Arial, sans-serif",
    fontSize: 14,
    fontSizeLG: 16,
    fontSizeSM: 12,
    fontSizeXL: 20,
    fontSizeHeading1: 38,
    fontSizeHeading2: 30,
    fontSizeHeading3: 24,
    fontSizeHeading4: 20,
    fontSizeHeading5: 16,

    // line height
    lineHeight: 1.5,
    lineHeightLG: 1.8,
    lineHeightSM: 1.2,

    // spacing
    padding: 16,
    paddingLG: 24,
    paddingMD: 16,
    paddingSM: 12,
    paddingXS: 8,
    paddingXXS: 4,

    margin: 16,
    marginLG: 24,
    marginMD: 16,
    marginSM: 12,
    marginXS: 8,
    marginXXS: 4,

    // component specific config
    controlHeight: 32,
    controlHeightLG: 40,
    controlHeightSM: 24,
    controlHeightXS: 20,

    // animations
    motionDurationFast: '0.1s',
    motionDurationMid: '0.2s',
    motionDurationSlow: '0.3s',
    motionEaseInOut: 'cubic-bezier(0.645, 0.045, 0.355, 1)',
    motionEaseOut: 'cubic-bezier(0.215, 0.61, 0.355, 1)',
    motionEaseIn: 'cubic-bezier(0.55, 0.055, 0.675, 0.19)',
  },
  components: {
    // Menu component config
    Menu: {
      borderRadius: 6,
      itemBorderRadius: 4,
      itemSelectedBg: 'rgba(255, 255, 255, 0.14)',
      itemActiveBg: 'rgba(255, 255, 255, 0.14)',
      itemHoverBg: 'rgba(255, 255, 255, 0.14)',
      itemHoverColor: 'rgba(255, 255, 255, 1)',
      itemSelectedColor: 'rgba(255, 255, 255, 1)',
      algorithm: true,
      borderWidth: 0,
      inlineIndent: 0,
      // itemPaddingInline: 16,
    },
    // Drawer component config
    Drawer: {
      algorithm: true,

    },
    // Button component config
    Button: {
      borderRadius: 6,
      controlHeight: 32,
      controlHeightLG: 40,
      controlHeightSM: 24,
      paddingInline: 16,
      paddingInlineLG: 24,
      paddingInlineSM: 12,
      algorithm: true,
      defaultShadow: 'none',
    },

    // Input component config
    Input: {
      borderRadius: 6,
      controlHeight: 32,
      controlHeightLG: 40,
      controlHeightSM: 24,
      paddingInline: 12,
      paddingInlineLG: 16,
      paddingInlineSM: 8,
      algorithm: true,
      borderWidth: 1,
      activeShadow: '0 0 0 1px rgba(0, 0, 0, 1)',
    },

    // Select component config
    Select: {
      borderRadius: 6,
      controlHeight: 32,
      controlHeightLG: 40,
      controlHeightSM: 24,
      algorithm: true,
      optionSelectedBg: 'rgba(0, 189, 195, 0.1)',
    },



    // Card component config
    Card: {
      borderRadius: 8,
      algorithm: true,
    },

    // Modal component config
    Modal: {
      borderRadius: 8,
      algorithm: true,
    },



    // Table component config
    Table: {
      borderRadius: 6,
      algorithm: true,
    },

    // Tag component config
    Tag: {
      borderRadius: 4,
      algorithm: true,
    },

    // Badge component config
    Badge: {
      algorithm: true,
    },

    // Progress component config
    Progress: {
      algorithm: true,
    },

    // Slider component config
    Slider: {
      algorithm: true,
    },

    // Switch component config
    Switch: {
      algorithm: true,
    },

    // Checkbox component config
    Checkbox: {
      borderRadius: 2,
      algorithm: true,
    },

    // Radio component config
    Radio: {
      algorithm: true,
    },
  },
};

// global theme config
export const globalTheme = {
  algorithm: theme.defaultAlgorithm,
  token: {
    // primary color
    colorPrimary: 'rgba(0, 0, 0, 1)',
    colorPrimaryHover: 'rgba(0, 0, 0, 1)',
    colorPrimaryActive: 'rgba(0, 0, 0, 1)',
    colorPrimaryBg: 'rgba(0, 189, 195, 0.1)',
    colorPrimaryBgHover: 'rgba(0, 189, 195, 0.05)',
    colorPrimaryBorder: 'rgba(0, 189, 195, 1)',
    colorPrimaryBorderHover: 'rgba(0, 169, 175, 1)',

    // functional colors
    colorSuccess: '#52c41a',
    colorWarning: '#faad14',
    colorError: '#ff4d4f',
    colorInfo: 'rgba(0, 189, 195, 1)',

    // neutral colors
    colorText: 'rgba(0, 0, 0, 0.85)',
    colorTextSecondary: 'rgba(0, 0, 0, 0.45)',
    colorTextTertiary: 'rgba(0, 0, 0, 0.25)',
    colorTextQuaternary: 'rgba(0, 0, 0, 0.15)',
    colorTextDisabled: 'rgba(0, 0, 0, 0.25)',

    // background colors
    colorBgContainer: '#ffffff',
    colorBgElevated: '#ffffff',
    colorBgLayout: '#f5f5f5',
    colorBgSpotlight: 'rgba(0, 0, 0, 0.85)',
    colorBgMask: 'rgba(0, 0, 0, 0.45)',

    // border colors
    colorBorder: '#d9d9d9',
    colorBorderSecondary: '#f0f0f0',

    // border radius
    borderRadius: 6,
    borderRadiusLG: 8,
    borderRadiusSM: 4,
    borderRadiusXS: 2,

    // shadows
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
    boxShadowSecondary: '0 1px 4px rgba(0, 0, 0, 0.1)',
    boxShadowTertiary: '0 4px 16px rgba(0, 0, 0, 0.2)',

    // font family
    fontFamily: "'MiSans', system-ui, Avenir, Helvetica, Arial, sans-serif",
    fontSize: 14,
    fontSizeLG: 16,
    fontSizeSM: 12,
    fontSizeXL: 20,
    fontSizeHeading1: 38,
    fontSizeHeading2: 30,
    fontSizeHeading3: 24,
    fontSizeHeading4: 20,
    fontSizeHeading5: 16,

    // line height
    lineHeight: 1.5,
    lineHeightLG: 1.8,
    lineHeightSM: 1.2,

    // spacing
    padding: 16,
    paddingLG: 24,
    paddingMD: 16,
    paddingSM: 12,
    paddingXS: 8,
    paddingXXS: 4,

    margin: 16,
    marginLG: 24,
    marginMD: 16,
    marginSM: 12,
    marginXS: 8,
    marginXXS: 4,

    // component specific config
    controlHeight: 32,
    controlHeightLG: 40,
    controlHeightSM: 24,
    controlHeightXS: 20,

    // animations
    motionDurationFast: '0.1s',
    motionDurationMid: '0.2s',
    motionDurationSlow: '0.3s',
    motionEaseInOut: 'cubic-bezier(0.645, 0.045, 0.355, 1)',
    motionEaseOut: 'cubic-bezier(0.215, 0.61, 0.355, 1)',
    motionEaseIn: 'cubic-bezier(0.55, 0.055, 0.675, 0.19)',
  },
  components: {
    // Button component config
    Button: {
      borderRadius: 6,
      controlHeight: 32,
      controlHeightLG: 40,
      controlHeightSM: 24,
      paddingInline: 16,
      paddingInlineLG: 24,
      paddingInlineSM: 12,
      algorithm: true,
      defaultShadow: 'none',
    },

    // Input component config
    Input: {
      borderRadius: 6,
      controlHeight: 32,
      controlHeightLG: 40,
      controlHeightSM: 24,
      paddingInline: 12,
      paddingInlineLG: 16,
      paddingInlineSM: 8,
      algorithm: true,
      borderWidth: 1,
      activeShadow: '0 0 0 1px rgba(0, 0, 0, 1)',
    },

    // Select component config
    Select: {
      borderRadius: 6,
      controlHeight: 32,
      controlHeightLG: 40,
      controlHeightSM: 24,
      algorithm: true,
      optionSelectedBg: 'rgba(247, 247, 247, 1)',
    },

    // Menu component config
    Menu: {
      borderRadius: 6,
      itemBorderRadius: 4,
      itemSelectedBg: 'rgba(235, 235, 235, 1)',
      itemActiveBg: 'rgba(235, 235, 235, 1)',
      itemHoverBg: 'rgba(235, 235, 235, 1)',
      itemHoverColor: 'rgba(0, 0, 0, 1)',
      itemSelectedColor: 'rgba(0, 0, 0, 1)',
      algorithm: true,
      borderWidth: 0,
      inlineIndent: 0,
      itemPaddingInline: 0,
      collapsedIconSize: 32,
      collapsedWidth: 100,
      itemHeight: 48,
      horizontalLineHeight: '70px',

    },

    // Card component config
    Card: {
      borderRadius: 8,
      algorithm: true,
    },

    // Modal component config
    Modal: {
      borderRadius: 8,
      algorithm: true,
    },

    // Drawer component config
    Drawer: {
      algorithm: true,
    },

    // Table component config
    Table: {
      borderRadius: 6,
      algorithm: true,
    },

    // Tag component config
    Tag: {
      borderRadius: 4,
      algorithm: true,
    },

    // Badge component config
    Badge: {
      algorithm: true,
    },

    // Progress component config
    Progress: {
      algorithm: true,
    },

    // Slider component config
    Slider: {
      algorithm: true,
    },

    // Switch component config
    Switch: {
      algorithm: true,
    },

    // Checkbox component config
    Checkbox: {
      borderRadius: 2,
      algorithm: true,
    },

    // Radio component config
    Radio: {
      algorithm: true,
    },
  },
};

// export theme tokens for other components
export const themeTokens = {
  // primary color
  primary: 'rgba(0, 189, 195, 1)',
  primaryHover: 'rgba(0, 169, 175, 1)',
  primaryActive: 'rgba(0, 149, 155, 1)',
  primaryLight: 'rgba(0, 189, 195, 0.1)',
  primaryLighter: 'rgba(0, 189, 195, 0.05)',

  // primary color variants
  primary90: 'rgba(0, 189, 195, 0.9)',
  primary80: 'rgba(0, 189, 195, 0.8)',
  primary70: 'rgba(0, 189, 195, 0.7)',
  primary60: 'rgba(0, 189, 195, 0.6)',
  primary50: 'rgba(0, 189, 195, 0.5)',
  primary40: 'rgba(0, 189, 195, 0.4)',
  primary30: 'rgba(0, 189, 195, 0.3)',
  primary20: 'rgba(0, 189, 195, 0.2)',
  primary10: 'rgba(0, 189, 195, 0.1)',
  primary05: 'rgba(0, 189, 195, 0.05)',

  // functional colors
  success: '#52c41a',
  warning: '#faad14',
  error: '#ff4d4f',
  info: 'rgba(0, 189, 195, 1)',

  // spacing
  spacing: {
    xs: 4,
    sm: 8,
    md: 16,
    lg: 24,
    xl: 32,
    xxl: 48,
  },

  // border radius
  borderRadius: {
    sm: 4,
    md: 6,
    lg: 8,
    xl: 12,
  },

  // shadows
  boxShadow: {
    light: '0 1px 4px rgba(0, 0, 0, 0.1)',
    default: '0 2px 8px rgba(0, 0, 0, 0.15)',
    dark: '0 4px 16px rgba(0, 0, 0, 0.2)',
    primary: '0 2px 8px rgba(0, 189, 195, 0.2)',
  },

  // animations
  transition: {
    duration: '0.2s',
    timing: 'cubic-bezier(0.645, 0.045, 0.355, 1)',
  },


};
