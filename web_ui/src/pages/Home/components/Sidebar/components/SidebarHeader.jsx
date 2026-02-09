/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { memo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Divider } from 'antd';
import { useGlobalSocket } from '@/hooks/useGlobalSocket';
import { useSessionChatStore } from '@/stores/chatStore';
import { Icon } from '@/components';
import styles from './SidebarHeader.module.less';

/**
 * SidebarHeader Component - Sidebar header with new chat button and toggle functionality
 * 侧边栏头部组件 - 包含新建对话按钮和收起/展开按钮的侧边栏头部
 *
 * @param {Object} props - Component props
 * @param {boolean} props.collapsed - Whether sidebar is collapsed
 * @param {boolean} [props.isDragging=false] - Whether sidebar is being dragged
 * @param {Function} props.onToggle - Toggle collapse/expand callback function
 * @returns {JSX.Element} Sidebar header component
 */
const SidebarHeader = memo(({ collapsed, isDragging = false, onToggle }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const socketActions = useGlobalSocket()
  const {
    clearTempChatState
  } = useSessionChatStore()

  const handleNewChatClick = useCallback(() => {
    clearTempChatState()
    socketActions.globalNewChat();
    navigate('/home/instant');
  }, [navigate, socketActions]);

  const handleToggleClick = useCallback(() => {
    if (onToggle && typeof onToggle === 'function') {
      onToggle();
    }
  }, [onToggle]);

  return (
    <>
      <div className={`${styles.sidebarHeader} ${isDragging ? styles.dragging : ''}`}>
        <div className={`${styles.expandedHeader} ${collapsed ? styles.collapsedHeader : ''}`}>
          <button
            onClick={handleNewChatClick}
            className={`${styles.newChatButton} ${collapsed ? styles.collapsedNewChatButton : ''}`}
          >
            <Icon
              name="instantNewChatIcon"
              size={18}
              className={styles.newChatIcon}
            />
            {!collapsed && (
              <span className={styles.newChatText}>{t('home.sidebar.newChat')}</span>
            )}
          </button>

          <Icon
            name="collapsed"
            size={14}
            className={styles.toggleIcon}
            onClick={handleToggleClick}
            title={t('home.sidebar.collapse')}
            style={{ transform: collapsed ? 'rotate(180deg)' : 'rotate(0deg)' }}
          />
        </div>
      </div>
      <Divider style={{ margin: '18px 0px', padding: '0px 4px' }} />
    </>

  );
});

export default SidebarHeader;
