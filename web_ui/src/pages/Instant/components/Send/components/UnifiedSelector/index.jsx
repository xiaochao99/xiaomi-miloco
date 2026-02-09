/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useRef, useEffect, useState } from 'react';
import { Checkbox, Spin, Empty, Divider, Button } from 'antd';
import { useTranslation } from 'react-i18next';
import { ReloadOutlined } from '@ant-design/icons';
import styles from './UnifiedSelector.module.less';

/**
 * UnifiedSelector Component - Unified selector for cameras and MCP services
 * 统一选择器组件 - 用于摄像头和MCP服务的统一选择器
 *
 * @param {Object} props - Component props
 * @param {boolean} props.visible - Whether the selector is visible
 * @param {Array} props.items - List of items to select from
 * @returns {JSX.Element} UnifiedSelector component
 */
const UnifiedSelector = ({
  visible,
  items = [],
  selectedIds = [],
  loading = false,
  showSelectAll = false,
  showAutoSelect = false,
  emptyText = 'instant.chat.noProject',
  loadingText = 'common.loading',
  onToggleItem,
  onSelectAll,
  onClose,
  onReconnect,
  itemConfig = {
    idField: 'id',
    nameField: 'name',
    descField: 'description',
    disabledField: 'disabled'
  }
}) => {
  const { t } = useTranslation();
  const [reconnectingItems, setReconnectingItems] = useState(new Set());

  const selectorRef = useRef(null);
  const handleReconnect = async (itemId) => {
    setReconnectingItems(prev => new Set(prev).add(itemId));

    try {
      if (onReconnect) {
        await onReconnect(itemId);
      }
    } catch (error) {
      console.error('reconnect failed:', error);
    } finally {
      setReconnectingItems(prev => {
        const newSet = new Set(prev);
        newSet.delete(itemId);
        return newSet;
      });
    }
  };

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (selectorRef.current && !selectorRef.current.contains(event.target)) {
        if (onClose) {
          onClose();
        }
      }
    };

    if (visible) {

      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [visible, onClose]);

  if (!visible) { return null }
  const onlineItems = items.filter(item => item?.[itemConfig?.disabledField] || false);
  const onlineItemsEmpty = onlineItems.length === 0;

  const isAllSelected = onlineItems.length > 0 && selectedIds.length === onlineItems.length;
  const hasPartialSelection = selectedIds.length > 0 && selectedIds.length < onlineItems.length;

  return (
    <div className={styles.selector} ref={selectorRef}>
      <div className={styles.content}>
        {loading ? (
          <div className={styles.loading}>
            <Spin size="small" />
            <span>{t(loadingText)}</span>
          </div>
        ) : !Array.isArray(items) || items.length === 0 ? (
          <div className={styles.empty}>
            <Empty
              description={t(emptyText)}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          </div>
        ) : (
          <div className={styles.itemListContainer}>
            {showSelectAll && (
              <div className={styles.item}>
                <Checkbox
                  checked={isAllSelected}
                  indeterminate={hasPartialSelection}
                  onChange={(e) => onSelectAll && onSelectAll(e.target.checked)}
                  disabled={onlineItemsEmpty}
                >
                  <div className={styles.itemInfo}>
                    <div className={styles.itemName}>{t('common.selectAll')}</div>
                  </div>
                </Checkbox>
              </div>
            )}

            {showAutoSelect && (
              <div className={styles.item}>
                <Checkbox
                  checked={selectedIds.length === 0 && !onlineItemsEmpty}
                  indeterminate={false}
                  disabled={onlineItemsEmpty}
                  onChange={() => {
                    if (onSelectAll) {
                      onSelectAll(false);
                    }
                  }}
                >
                  <div className={styles.itemInfo}>
                    <div className={styles.itemName}>{t('common.autoSelect')}</div>
                  </div>
                </Checkbox>
              </div>
            )}
            <Divider style={{ margin: '0' }} />

            <div className={styles.itemList}>
              {items.map((item) => {
                const itemId = item[itemConfig.idField];
                const itemName = item[itemConfig.nameField] || itemId;

                const itemDisabled = itemConfig?.disabledField ? !item[itemConfig.disabledField] : false;
                const isReconnecting = reconnectingItems.has(itemId);
                return (
                  <div key={itemId} className={styles.item}>
                    <Checkbox
                      checked={Array.isArray(selectedIds) && selectedIds.includes(itemId)}
                      onChange={() => onToggleItem && onToggleItem(itemId)}
                      disabled={itemDisabled}
                    >
                      <div className={styles.itemInfo}>
                        <div className={styles.itemName}>
                          {itemName}
                        </div>
                        {itemDisabled && onReconnect && (
                          <Button
                            type="text"
                            size="small"
                            icon={<ReloadOutlined />}
                            onClick={(e) => {
                              e.stopPropagation();
                              onReconnect(itemId);
                            }}
                            className={styles.reconnectButton}
                          >
                            {t('common.reconnect')}
                          </Button>
                        )}
                      </div>
                    </Checkbox>
                  </div>
                );
              })}
            </div>

          </div>
        )}
      </div>
    </div>
  );
};

export default UnifiedSelector;
