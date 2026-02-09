/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { createContext, useContext, useState, useEffect } from 'react';
import { ConfigProvider } from 'antd';
import { globalTheme, darkTheme } from '../theme';

const ThemeContext = createContext();

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

export const ThemeProvider = ({ children }) => {
  const [themeMode, setThemeMode] = useState(() => {
    const savedMode = localStorage.getItem('themeMode') || 'light';
    if (savedMode === 'system') {
      const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      document.documentElement.setAttribute('data-theme', systemTheme);
    } else {
      document.documentElement.setAttribute('data-theme', savedMode);
    }

    return savedMode;
  });

  // get theme config by theme mode
  const getThemeConfig = (mode) => {
    switch (mode) {
      case 'dark':
        return darkTheme;
      case 'light':
      default:
        return globalTheme;
    }
  };

  // handle system theme change
  const handleSystemThemeChange = () => {
    if (themeMode === 'system') {
      const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      document.documentElement.setAttribute('data-theme', systemTheme);
    }
  };

  // listen system theme change
  useEffect(() => {
    if (themeMode === 'system') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      mediaQuery.addEventListener('change', handleSystemThemeChange);
      handleSystemThemeChange();

      return () => {
        mediaQuery.removeEventListener('change', handleSystemThemeChange);
      };
    }
  }, [themeMode]);

  // change theme mode
  const changeTheme = (mode) => {
    setThemeMode(mode);
    localStorage.setItem('themeMode', mode);

    // set HTML attribute for CSS variables
    if (mode === 'system') {
      const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      document.documentElement.setAttribute('data-theme', systemTheme);
    } else {
      document.documentElement.setAttribute('data-theme', mode);
    }
  };

  // get current actual theme config
  const getCurrentTheme = () => {
    if (themeMode === 'system') {
      const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      return getThemeConfig(systemTheme);
    }
    return getThemeConfig(themeMode);
  };

  const value = {
    themeMode,
    changeTheme,
    getCurrentTheme,
  };

  return (
    <ThemeContext.Provider value={value}>
      <ConfigProvider theme={getCurrentTheme()}>
        {children}
      </ConfigProvider>
    </ThemeContext.Provider>
  );
};
