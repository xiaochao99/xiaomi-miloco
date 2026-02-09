/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { memo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { LogoutOutlined } from '@ant-design/icons';
import defaultAvatar from '@/assets/images/avatar.png';
import styles from './UserAvatar.module.less';

/**
 * UserAvatar Component - User avatar component with logout functionality
 * 用户头像组件 - 显示用户头像、昵称和登出按钮的用户头像组件
 *
 * @param {Object} props - Component props
 * @param {Object} [props.userInfo={}] - User information object
 * @param {string} [props.userInfo.icon] - User avatar URL
 * @param {string} [props.userInfo.nickname] - User nickname
 * @param {boolean} [props.collapsed=false] - Whether component is in collapsed state
 * @param {boolean} [props.isDragging=false] - Whether component is being dragged
 * @param {Function} props.onLogout - Logout callback function
 * @returns {JSX.Element} User avatar component
 */
const UserAvatar = memo(({
  userInfo = {},
  collapsed = false,
  isDragging = false,
  onLogout
}) => {
  const { icon, nickname } = userInfo;
  const navigate = useNavigate();
  const { t } = useTranslation();

  const handleLogout = useCallback((e) => {
    e.stopPropagation();
    if (onLogout && typeof onLogout === 'function') {
      onLogout();
    }
  }, [onLogout]);

  return (
    <div
      className={`${styles.userAvatar} ${collapsed ? styles.collapsed : ''} ${isDragging ? styles.dragging : ''}`}
      onClick={() => {
        navigate('/home/setting');
      }}
    >
      <img
        src={icon || defaultAvatar}
        alt="User Avatar"
        className={styles.avatar}
        onError={(e) => {
          e.target.src = defaultAvatar;
        }}
      />
      {!collapsed && (
        <div className={styles.userInfo}>
          <div className={styles.nickname} title={nickname}>
            {nickname || t('home.userPopover.notLoggedIn')}
          </div>
        </div>
      )}
      <LogoutOutlined
        className={styles.logoutIcon}
        onClick={handleLogout}
        title={t('home.userPopover.logout')}
      />
    </div>
  );
});

export default UserAvatar;
