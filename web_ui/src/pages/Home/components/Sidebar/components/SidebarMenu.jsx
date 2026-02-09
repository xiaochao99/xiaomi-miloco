/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { memo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import CustomMenu from '../../CustomMenu';
import { MENU_ITEMS } from '@/constants/homeConfigTypes';
import styles from './SidebarMenu.module.less';

/**
 * SidebarMenu Component - Sidebar navigation menu component
 * 侧边栏菜单组件 - 渲染导航菜单项的侧边栏菜单组件
 *
 * @param {Object} props - Component props
 * @param {Array<string>} [props.selectedKeys=[]] - Currently selected menu item keys
 * @param {boolean} [props.collapsed=false] - Whether menu is in collapsed state
 * @returns {JSX.Element} Sidebar menu component
 */
const SidebarMenu = memo(({ selectedKeys = [], collapsed = false }) => {
  const navigate = useNavigate();

  const handleMenuClick = useCallback(({ item }) => {
    const path = item?.props?.path;
    if (path) {
      navigate(path);
    }
  }, [navigate]);

  return (
    <div className={styles.sidebarMenu}>
      <CustomMenu
        className={styles.customMenu}
        selectedKeys={selectedKeys}
        items={MENU_ITEMS}
        onClick={handleMenuClick}
        collapsed={collapsed}
        mode="inline"
      />
    </div>
  );
});

export default SidebarMenu;
