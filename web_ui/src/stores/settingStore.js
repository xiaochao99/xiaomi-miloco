/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/**
 * Setting Store - 管理应用设置状态（语言、主题等）
 * Setting Store - Manage application settings state (language, theme, etc.)
 */
export const useSettingStore = create(
  persist(
    (set, get) => ({
      language: 'zh',
      themeMode: 'light',

      // set language
      setLanguage: (language) => {
        set({ language });
      },

      // set theme mode
      setThemeMode: (themeMode) => {
        set({ themeMode });
      },

      // get current language
      getLanguage: () => {
        return get().language;
      },

      // get current theme mode
      getThemeMode: () => {
        return get().themeMode;
      },
    }),
    {
      name: 'mico-setting-store',
      // only persist language and theme mode
      partialize: (state) => ({
        language: state.language,
        themeMode: state.themeMode,
      }),
    }
  )
);
