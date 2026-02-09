/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { Empty, Spin, Button } from 'antd';
import { useTranslation } from 'react-i18next';
import { LoadingOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Card, ListItem, Loading, EmptyContent } from '@/components';
import styles from './index.module.less';


/**
 * AutomationListView Component - Automation list view component
 * 自动化列表视图组件
 *
 * @param {Object} dataList - The data list to display
 * @param {boolean} loading - Whether the data list is loading
 * @returns {JSX.Element} Automation list view component
 */
const AutomationListView = ({
  dataList,
  loading,
  onExecuteAction,
  loadingStates,
  emptyTextKey = 'executionManage.noAutomation'
}) => {
  const { t } = useTranslation();

  const getLoadingState = (item) => {
    const itemId = item.id || item.introduction;
    return loadingStates[itemId] || false;
  };

  const renderAutomationItem = (item) => {
    const isLoading = getLoadingState(item);

    return (
      <Card
        key={item.id || item.introduction}
        className={styles.automationCard}
        contentClassName={styles.automationItem}
      >
        <ListItem
          title={item.introduction || 'Unnamed automation'}
          titleClassName={styles.title}
          rightContent={
            <div>
              <Button
                type="link"
                style={{ width: '25px', height: '25px' }}
                icon={
                  isLoading ? (
                    <LoadingOutlined style={{ color: 'var(--text-color)' }} />
                  ) : (
                    <ThunderboltOutlined style={{ color: 'var(--text-color)' }} />
                  )
                }
                onClick={() => onExecuteAction(item)}
                loading={isLoading}
                disabled={isLoading}
              />
            </div>
          }
        />
      </Card>
    );
  };


  if (loading) {
    return (
      <div className={styles.loadingContainer}>
        <Loading size="default" />
      </div>
    );
  }

  if (!loading && dataList.length === 0) {
    return (
      <div className={styles.emptyContainer}>
        <EmptyContent description={t(emptyTextKey)} />
      </div>
    );
  }

  return (
    <div className={styles.automationList}>
      {dataList.map(item => renderAutomationItem(item))}
    </div>
  );
};

export default AutomationListView;
