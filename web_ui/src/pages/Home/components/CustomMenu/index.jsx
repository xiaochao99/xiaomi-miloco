/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { Icon } from '@/components';
import styles from './index.module.less';

/**
 * CustomMenu Component - Custom menu component with icon support and tooltip
 * 自定义菜单组件 - 支持图标和提示框的自定义菜单组件
 *
 * @param {Object} props - Component props
 * @param {Array} [props.items=[]] - Menu items to display
 * @param {Array<string>} [props.selectedKeys=[]] - Selected menu item keys
 * @param {Function} props.onClick - Click handler function
 * @param {boolean} [props.collapsed=false] - Whether the menu is collapsed
 * @param {string} [props.className] - Additional CSS class name
 * @returns {JSX.Element} Custom menu component
 */
const CustomMenu = ({
  items = [],
  selectedKeys = [],
  onClick,
  collapsed = false,
  className
}) => {
  const { t } = useTranslation();
  const handleItemClick = (item) => {
    if (onClick) {
      onClick({ item: { props: item } });
    }
  };

  return (
    <div className={`${styles.customMenu} ${collapsed ? styles.collapsed : ''} ${className || ''}`}>
      {items.map((item) => {
        const isSelected = selectedKeys.includes(item.key);

        const menuItemContent = (
          <div
            key={item.key}
            className={`${styles.menuItem} ${isSelected ? styles.selected : ''}`}
            onClick={() => handleItemClick(item)}
          >
            <div className={styles.menuIcon}>
              <Icon name={isSelected ? item.selectedIcon : item.icon} size={22} />
            </div>
            {!collapsed && (
              <div className={styles.menuLabel}>
                {t(item.label)}
              </div>
            )}
          </div>
        );

        return collapsed ? (
          <Tooltip
            key={item.key}
            title={t(item.label)}
            placement="right"
            mouseEnterDelay={0.3}
            mouseLeaveDelay={0}
            overlayClassName={styles.menuTooltip}
          >
            {menuItemContent}
          </Tooltip>
        ) : (
          menuItemContent
        );
      })}
    </div>
  );
};

export default CustomMenu;
