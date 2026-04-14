/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Tabs, Spin, Empty } from 'antd';
import { Header, Icon } from '@/components';
import { DeviceList, HADeviceList, RTSPCameraList, RTSPCameraModal, XiaoAIDeviceList } from './components';
import { useDevices } from './hooks/useDevices';
import { useHADevices } from './hooks/useHADevices';
import { useRTSPCameras } from './hooks/useRTSPCameras';
import styles from './index.module.less';

/**
 * DeviceManage Page - Device management page for viewing and managing connected devices
 * 设备管理页面 - 用于查看和管理已连接设备的页面
 *
 * @returns {JSX.Element} Device management page component
 */
const DeviceManage = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('miot');

  const { devices: miotDevices, loading: miotLoading, refreshDevices: refreshMiot } = useDevices();
  const { devices: haDevices, loading: haLoading, refreshDevices: refreshHa } = useHADevices();
  const {
    cameras: rtspCameras,
    loading: rtspLoading,
    modalVisible,
    editingCamera,
    fetchCameras,
    deleteCamera,
    openCreateModal,
    openEditModal,
    closeModal,
    handleSave,
    toggleCameraEnable
  } = useRTSPCameras();

  const handleRefresh = () => {
    if (activeTab === 'miot') {
      refreshMiot();
    } else if (activeTab === 'ha') {
      refreshHa();
    } else if (activeTab === 'rtsp') {
      fetchCameras();
    }
  };

  const renderMiotContent = () => {
    if (miotLoading) {
      return (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '50px 0' }}>
          <Spin />
        </div>
      );
    }
    if (!miotDevices || miotDevices.length === 0) {
      return (
        <Empty
          description={t('deviceManage.noDevice')}
          imageStyle={{ width: 72, height: 72 }}
        />
      );
    }
    return <DeviceList devices={miotDevices} />;
  };

  const tabItems = [
    {
      key: 'miot',
      label: t('deviceManage.miotDevices'),
      children: renderMiotContent()
    },
    {
      key: 'ha',
      label: t('deviceManage.haDevices'),
      children: (
        <HADeviceList
          devices={haDevices}
          loading={haLoading}
          onRefresh={refreshHa}
        />
      )
    },
    {
      key: 'rtsp',
      label: t('deviceManage.rtspCameras'),
      children: (
        <RTSPCameraList
          cameras={rtspCameras}
          loading={rtspLoading}
          onEdit={openEditModal}
          onDelete={deleteCamera}
          onAdd={openCreateModal}
          onToggleEnable={toggleCameraEnable}
        />
      )
    },
    {
      key: 'xiaoai',
      label: t('deviceManage.xiaoaiDevices'),
      children: <XiaoAIDeviceList />
    }
  ];

  return (
    <div className={styles.container}>
      <div className={styles.wrapper}>
        <Header title={t('home.menu.deviceManage')} />
        <div className={styles.tabContainer}>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={tabItems}
            className={styles.tabs}
            tabBarExtraContent={{
              right: (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    cursor: 'pointer'
                  }}
                  onClick={handleRefresh}
                >
                  <Icon
                    name="refresh"
                    size={15}
                    style={{ color: 'var(--text-color)' }}
                  />
                  <span style={{ fontSize: '14px', color: 'var(--text-color)', marginLeft: '6px' }}>{t('common.refresh')}</span>
                </div>
              )
            }}
          />
        </div>
      </div>

      <RTSPCameraModal
        visible={modalVisible}
        camera={editingCamera}
        onCancel={closeModal}
        onSave={handleSave}
      />
    </div>
  );
};

export default DeviceManage;