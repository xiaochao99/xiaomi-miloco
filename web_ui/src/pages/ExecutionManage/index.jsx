/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */


import { useState } from 'react';
import { Tabs } from 'antd';
import { useTranslation } from 'react-i18next';
import { Header, Icon } from '@/components';
import { AutomationListView, NotificationTestView } from './components';
import { useExecutionManage, useNotificationTest } from './hooks';
import styles from './index.module.less';

/**
 * ExecutionManage Page - Execution management page for managing automation executions and notifications
 * 执行管理页面 - 用于管理自动化执行和通知的页面
 *
 * @returns {JSX.Element} Execution management page component
 */
const ExecutionManage = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('scenes');

  const {
    haList,
    scenesList,
    loadingStates,
    loading,
    refreshDataByTab,
    handleExecuteAction
  } = useExecutionManage();

  const {
    notificationText,
    setNotificationText,
    notificationLoading,
    handleSendNotification
  } = useNotificationTest();


  const handleRefresh = () => {
    refreshDataByTab(activeTab);
  };

  const tabItems = [
    {
      key: 'scenes',
      label: t('executionManage.miHomeAutomationExecution'),
      children: (
        <AutomationListView
          dataList={scenesList}
          loading={loading}
          onExecuteAction={handleExecuteAction}
          loadingStates={loadingStates}
          emptyTextKey="executionManage.noMiHomeAutomation"
        />
      ),
    },
    {
      key: 'ha',
      label: t('executionManage.haAutomationExecution'),
      children: (
        <AutomationListView
          dataList={haList}
          loading={loading}
          onExecuteAction={handleExecuteAction}
          loadingStates={loadingStates}
          emptyTextKey="executionManage.noHaAutomation"
        />
      ),
    },
    {
      key: 'miot_notification',
      label: t('executionManage.miHomeNotification'),
      children: (
        <NotificationTestView
          notificationText={notificationText}
          setNotificationText={setNotificationText}
          onSendNotification={handleSendNotification}
          loading={notificationLoading}
        />
      ),
    },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.wrapper}>
        <Header title={t('home.menu.executionManage')} />

        <div className={styles.tabContainer}>
          <Tabs
            defaultActiveKey="scenes"
            activeKey={activeTab}
            onChange={setActiveTab}
            items={tabItems}
            className={styles.tabs}
            tabBarExtraContent={{
              right: (
                activeTab !== 'miot_notification' && (
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  <Icon
                    name="refresh"
                    size={16}
                    onClick={handleRefresh}
                    style={{
                      color: 'var(--text-color)',
                      cursor: 'pointer'
                    }}
                  />
                </div>
              ))
            }}
          />
        </div>
      </div>
    </div>
  );
}

export default ExecutionManage;
