/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { MENU_ITEMS } from '@/constants/homeConfigTypes';



/**
 * Layout related custom hook
 * Handle menu selected state, route listening functions
 * @returns {Object} Layout related status and methods
 */
export const useLayout = () => {
  const location = useLocation();

  // state management
  const [selectedMenuKey, setSelectedMenuKey] = useState('0');

  /**
   * Update selected menu item
   * @param {string} key menu item key
   */
  const updateSelectedMenuKey = (key) => {
    setSelectedMenuKey(key);
  };

  /**
 * Get menu key by current path
 * @param {string} pathname - current path
 * @returns {string} menu key
 */
  const getMenuKeyByPath = (pathname) => {
    const menuItem = MENU_ITEMS.find(item => item.path.includes(pathname));
    if (menuItem) {
      return menuItem.key;
    }
    return '1';
  };

  /**
   * Get menu key by path
   * @param {string} pathname path
   * @returns {string} menu key
   */
  const getMenuKeyFromPath = (pathname) => {
    return getMenuKeyByPath(pathname);
  };

  // listen to path change, update menu selected state
  useEffect(() => {
    const menuKey = getMenuKeyFromPath(location.pathname);
    setSelectedMenuKey(menuKey);
  }, [location.pathname]);

  return {
    selectedMenuKey,
    currentPath: location.pathname,
    updateSelectedMenuKey,
    getMenuKeyFromPath,
  };
};
