/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { Splitter } from 'antd';
import { Outlet } from 'react-router-dom';
import Sidebar from '../Sidebar';
import { useSidebar } from '../../hooks';
import styles from './index.module.less';

/**
 * Layout Component - Main layout component with resizable sidebar and content area
 * 主布局组件 - 包含可调整大小的侧边栏和主内容区域
 *
 * @param {Object} props - Component props
 * @param {Array<string>} props.selectedMenuKeys - Selected menu keys
 * @param {Object} props.userInfo - User information object
 * @param {Function} props.onLogout - Logout callback function
 * @returns {JSX.Element} Main layout component
 */
const Layout = ({ selectedMenuKeys, userInfo, onLogout }) => {
  const {
    siderWidth,
    isCollapsed,
    toggleSidebar,
    handleResizeStart,
    handleResize,
    handleResizeEnd,
    SIDEBAR_WIDTH
  } = useSidebar();

  return (
    <div className={styles.layout}>
      <Splitter
        style={{ height: '100%' }}
        resizerStyle={{
          backgroundColor: 'var(--border-color, #e8e8e8)',
          width: '2px'
        }}
        onResizeStart={handleResizeStart}
        onResize={handleResize}
        onResizeEnd={handleResizeEnd}
      >
        <Splitter.Panel
          size={siderWidth}
          defaultSize={SIDEBAR_WIDTH.EXPANDED}
          min={SIDEBAR_WIDTH.MIN}
          max={SIDEBAR_WIDTH.MAX}
          className={styles.sidebarPanel}
        >
          <Sidebar
            width={siderWidth}
            collapsed={isCollapsed}
            // isDragging={isDragging}
            selectedKeys={selectedMenuKeys}
            userInfo={userInfo}
            onToggle={toggleSidebar}
            onLogout={onLogout}
          />
        </Splitter.Panel>

        <Splitter.Panel className={styles.contentPanel}>
          <div className={styles.mainContent}>
            <Outlet />
          </div>
        </Splitter.Panel>
      </Splitter>
    </div>
  );
}

Layout.displayName = 'Layout';

export default Layout;
