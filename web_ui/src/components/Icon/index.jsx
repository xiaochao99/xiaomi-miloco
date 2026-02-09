/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */


import React from 'react';
// import { useTheme } from 'antd-style';
import { iconLibrary } from './icons';
import { useTheme } from '@/contexts/ThemeContext';

/**
 * Icon component
 * @param {string} name - icon name
 * @param {string} size - icon size (sm, md, lg, xl) or specific value
 * @param {string} color - custom color
 * @param {string} className - custom class name
 * @param {object} style - custom style object
 * @param {object} props - other SVG attributes
 */
const Icon = ({
  name,
  size = 'sm',
  width = '',
  height = '',
  color,
  className = '',
  style = {},
  viewBox = '',
  ...props
}) => {
  const { themeMode } = useTheme();

  const iconData = iconLibrary[name];
  if (!iconData) {
    console.warn(`Icon "${name}" not found`);
    return null;
  }

  const getIconPath = () => {
    if(typeof iconData === 'function') {
      return iconData();
    }
    if(iconData.dark && iconData.light) {
      return themeMode === 'dark' ? iconData.dark : iconData.light;
    }
    return iconData.dark || iconData.light || '';
  }

  const iconPath = getIconPath();

  const getSize = () => {
    const sizeMap = {
      sm: 16,
      md: 20,
      lg: 24,
      xl: 32
    };
    return typeof size === 'string' ? sizeMap[size] || 20 : size;
  };

  const iconSize = getSize();

  return (
    <svg
      width={width || iconSize}
      height={height || iconSize}
      viewBox={ viewBox || `0 0 ${width || iconSize} ${height || iconSize}`}
      className={`icon icon-${name} ${className}`}
      style={{
        color: color || 'currentColor',
        ...style
      }}
      {...props}
      dangerouslySetInnerHTML={{ __html: iconPath }}
      shapeRendering="geometricPrecision"
      textRendering="optimizeLegibility"
    />
  );
};

export default Icon;
