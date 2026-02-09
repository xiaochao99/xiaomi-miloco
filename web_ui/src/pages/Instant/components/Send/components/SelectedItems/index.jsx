/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { useTranslation } from 'react-i18next';
import styles from './SelectedItems.module.less';
import Icon from '@/components/Icon';

/**
 * SelectedItems Component - Display selected items (cameras or MCP services)
 * 已选择项目组件 - 显示已选择的项目（摄像头或MCP服务）
 *
 * @param {Object} props - Component props
 * @param {Array} props.selectedItems - List of selected items
 * @param {Function} props.onRemoveItem - Function to remove an item
 * @returns {JSX.Element} SelectedItems component
 */
const SelectedItems = ({
  selectedItems,
  onRemoveItem,
  itemConfig = {
    idField: 'id',
    nameField: 'name',
    descField: 'description'
  },
  type = 'default' // 'camera' | 'mcp' | 'default'
}) => {
  const { t } = useTranslation();

  if (!selectedItems || selectedItems.length === 0) {
    return null;
  }

  const getItemName = (item) => {
    return item[itemConfig.nameField] || item[itemConfig.idField] || 'Unknown';
  };

  const getItemIcon = () => {
    switch (type) {
      case 'camera':
        return null;
      case 'mcp':
        return <Icon name="instantFooterMcp" size={13} />;
      default:
        return null;
    }
  };

  return (
    <div className={styles.selectedItems}>
      {selectedItems.map((item) => (
        <div key={item[itemConfig.idField]} className={styles.itemTag}>
          {getItemIcon() && (
            <span className={styles.itemIcon}>
              {getItemIcon()}
            </span>
          )}
          <span className={styles.itemName}>
            {getItemName(item)}
          </span>
          <button
            className={styles.removeButton}
            onClick={() => onRemoveItem(item[itemConfig.idField])}
            title={t('common.remove')}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
};

export default SelectedItems;
