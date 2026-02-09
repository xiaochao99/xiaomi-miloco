/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { memo } from 'react';
import { SidebarHeader, SidebarMenu, UserAvatar } from './components/index';
import styles from './index.module.less';

/**
 * Sidebar Component - Main sidebar component with header, menu and user info
 * 侧边栏主组件 - 包含头部、菜单和用户信息的侧边栏组件
 *
 * @param {Object} props - Component props
 * @param {number} props.width - Sidebar width
 * @param {boolean} props.collapsed - Whether sidebar is collapsed
 * @param {boolean} [props.isDragging=false] - Whether sidebar is being dragged
 * @param {Array<string>} props.selectedKeys - Selected menu keys
 * @param {Object} props.userInfo - User information object
 * @param {Function} props.onToggle - Toggle collapse/expand callback
 * @param {Function} props.onLogout - Logout callback function
 * @returns {JSX.Element} Sidebar component
 */
const Sidebar = ({
  width,
  collapsed,
  isDragging = false,
  selectedKeys,
  userInfo,
  onToggle,
  onLogout
}) => {
  return (
    <div
      className={`${styles.sidebar} ${isDragging ? styles.dragging : ''}`}
      style={{ width }}
    >
      <div className={styles.sidebarContent}>
        {/* header area */}
        <SidebarHeader
          collapsed={collapsed}
          isDragging={isDragging}
          onToggle={onToggle}
        />

        {/* menu area */}
        <SidebarMenu
          selectedKeys={selectedKeys}
          collapsed={collapsed}
        />

        {/* user info area */}
        <UserAvatar
          userInfo={userInfo}
          collapsed={collapsed}
          isDragging={isDragging}
          onLogout={onLogout}
        />
      </div>
    </div>
  );
}


export default Sidebar;
