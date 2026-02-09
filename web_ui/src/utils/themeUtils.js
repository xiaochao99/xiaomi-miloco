/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

// theme tool function

/**
 * get CSS variable value
 * @param {string} variable - CSS variable name
 * @returns {string} CSS variable value
 */
export const getCSSVariable = (variable) => {
  return getComputedStyle(document.documentElement).getPropertyValue(variable).trim();
};

/**
 * get theme color related variables
 */
export const getPrimaryColors = () => ({
  primary: getCSSVariable('--primary-color'),
  primaryHover: getCSSVariable('--primary-color-hover'),
  primaryActive: getCSSVariable('--primary-color-active'),
  primaryLight: getCSSVariable('--primary-color-light'),
  primaryLighter: getCSSVariable('--primary-color-lighter'),
  primary90: getCSSVariable('--primary-color-90'),
  primary80: getCSSVariable('--primary-color-80'),
  primary70: getCSSVariable('--primary-color-70'),
  primary60: getCSSVariable('--primary-color-60'),
  primary50: getCSSVariable('--primary-color-50'),
  primary40: getCSSVariable('--primary-color-40'),
  primary30: getCSSVariable('--primary-color-30'),
  primary20: getCSSVariable('--primary-color-20'),
  primary10: getCSSVariable('--primary-color-10'),
  primary05: getCSSVariable('--primary-color-05'),
});

/**
 * get functional colors
 */
export const getFunctionalColors = () => ({
  success: getCSSVariable('--success-color'),
  warning: getCSSVariable('--warning-color'),
  error: getCSSVariable('--error-color'),
  info: getCSSVariable('--info-color'),
});

/**
 * get text colors
 */
export const getTextColors = () => ({
  text: getCSSVariable('--text-color'),
  textSecondary: getCSSVariable('--text-color-secondary'),
  textDisabled: getCSSVariable('--text-color-disabled'),
  textInverse: getCSSVariable('--text-color-inverse'),
});

/**
 * get background colors
 */
export const getBackgroundColors = () => ({
  bg: getCSSVariable('--bg-color'),
  bgLight: getCSSVariable('--bg-color-light'),
  bgLighter: getCSSVariable('--bg-color-lighter'),
  bgDark: getCSSVariable('--bg-color-dark'),
  bgDarker: getCSSVariable('--bg-color-darker'),
});

/**
 * get border colors
 */
export const getBorderColors = () => ({
  border: getCSSVariable('--border-color'),
  borderLight: getCSSVariable('--border-color-light'),
  borderLighter: getCSSVariable('--border-color-lighter'),
  borderDark: getCSSVariable('--border-color-dark'),
  borderDarker: getCSSVariable('--border-color-darker'),
});

/**
 * get shadows
 */
export const getShadows = () => ({
  shadow: getCSSVariable('--box-shadow'),
  shadowLight: getCSSVariable('--box-shadow-light'),
  shadowDark: getCSSVariable('--box-shadow-dark'),
  shadowPrimary: getCSSVariable('--box-shadow-primary'),
});

/**
 * get border radius
 */
export const getBorderRadius = () => ({
  radius: getCSSVariable('--border-radius'),
  radiusSm: getCSSVariable('--border-radius-sm'),
  radiusLg: getCSSVariable('--border-radius-lg'),
  radiusXl: getCSSVariable('--border-radius-xl'),
});

/**
 * get spacing
 */
export const getSpacing = () => ({
  xs: getCSSVariable('--spacing-xs'),
  sm: getCSSVariable('--spacing-sm'),
  md: getCSSVariable('--spacing-md'),
  lg: getCSSVariable('--spacing-lg'),
  xl: getCSSVariable('--spacing-xl'),
  xxl: getCSSVariable('--spacing-xxl'),
});

/**
 * get font sizes
 */
export const getFontSizes = () => ({
  xs: getCSSVariable('--font-size-xs'),
  sm: getCSSVariable('--font-size-sm'),
  md: getCSSVariable('--font-size-md'),
  lg: getCSSVariable('--font-size-lg'),
  xl: getCSSVariable('--font-size-xl'),
  xxl: getCSSVariable('--font-size-xxl'),
});

/**
 * get transition animations
 */
export const getTransitions = () => ({
  duration: getCSSVariable('--transition-duration'),
  timing: getCSSVariable('--transition-timing'),
});

/**
 * generate inline styles object
 * @param {Object} styles - styles object
 * @returns {Object} inline styles object
 */
export const createInlineStyles = (styles) => {
  const result = {};

  Object.entries(styles).forEach(([key, value]) => {
    if (typeof value === 'string' && value.startsWith('var(--')) {
      result[key] = value;
    } else if (typeof value === 'string' && value.startsWith('--')) {
      result[key] = `var(${value})`;
    } else {
      result[key] = value;
    }
  });

  return result;
};

/**
 * common styles
 */
export const commonStyles = {
  // primary button style
  primaryButton: {
    backgroundColor: 'var(--primary-color)',
    borderColor: 'var(--primary-color)',
    color: '#ffffff',
    borderRadius: 'var(--border-radius)',
    padding: 'var(--spacing-sm) var(--spacing-md)',
    transition: 'all var(--transition-duration) var(--transition-timing)',
    cursor: 'pointer',
    border: 'none',
    outline: 'none',
  },

  // primary button hover style
  primaryButtonHover: {
    backgroundColor: 'var(--primary-color-hover)',
    borderColor: 'var(--primary-color-hover)',
  },

  // card style
  card: {
    backgroundColor: 'var(--bg-color)',
    border: '1px solid var(--border-color)',
    borderRadius: 'var(--border-radius-lg)',
    padding: 'var(--spacing-lg)',
    boxShadow: 'var(--box-shadow-light)',
  },

  // input style
  input: {
    border: '1px solid var(--border-color)',
    borderRadius: 'var(--border-radius)',
    padding: 'var(--spacing-sm) var(--spacing-md)',
    fontSize: 'var(--font-size-md)',
    transition: 'all var(--transition-duration) var(--transition-timing)',
    outline: 'none',
  },

  // input focus style
  inputFocus: {
    borderColor: 'var(--primary-color)',
    boxShadow: 'var(--ant-input-focus-box-shadow)',
  },

  // text style
  text: {
    color: 'var(--text-color)',
    fontSize: 'var(--font-size-md)',
    lineHeight: 'var(--line-height)',
  },

  // secondary text style
  textSecondary: {
    color: 'var(--text-color-secondary)',
    fontSize: 'var(--font-size-sm)',
    lineHeight: 'var(--line-height)',
  },

  // heading style
  heading: {
    color: 'var(--text-color)',
    fontSize: 'var(--font-size-xl)',
    fontWeight: 600,
    lineHeight: 'var(--line-height-sm)',
    marginBottom: 'var(--spacing-md)',
  },
};
