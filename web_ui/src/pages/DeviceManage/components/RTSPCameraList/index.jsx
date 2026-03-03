/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { Button, Empty, Spin } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import RTSPCameraCard from '../RTSPCameraCard';
import styles from './index.module.less';

/**
 * RTSPCameraList Component - RTSP Camera List with Card Layout
 * RTSP摄像头列表 - 卡片形式展示
 *
 * @param {Object} props
 * @param {Array} props.cameras - RTSP camera list
 * @param {boolean} props.loading - Loading state
 * @param {Function} props.onEdit - Edit handler
 * @param {Function} props.onDelete - Delete handler
 * @param {Function} props.onAdd - Add handler
 * @param {Function} props.onToggleEnable - Toggle enable status handler
 */
export const RTSPCameraList = ({ 
  cameras, 
  loading, 
  onEdit, 
  onDelete, 
  onAdd,
  onToggleEnable 
}) => {
  const { t } = useTranslation();

  if (loading) {
    return (
      <div className={styles.loadingContainer}>
        <Spin size="large" />
        <span className={styles.loadingText}>{t('common.loading')}</span>
      </div>
    );
  }

  if (!cameras || cameras.length === 0) {
    return (
      <div className={styles.emptyContainer}>
        <Empty
          description={t('deviceManage.rtsp.noCameras')}
          imageStyle={{ width: 72, height: 72 }}
        >
          <Button type="primary" icon={<PlusOutlined />} onClick={onAdd}>
            {t('deviceManage.rtsp.addCamera')}
          </Button>
        </Empty>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <Button type="primary" icon={<PlusOutlined />} onClick={onAdd}>
          {t('deviceManage.rtsp.addCamera')}
        </Button>
      </div>
      <div className={styles.cameraGrid}>
        {cameras.map((camera) => (
          <RTSPCameraCard
            key={camera.did}
            camera={camera}
            onEdit={onEdit}
            onDelete={onDelete}
            onToggleEnable={onToggleEnable}
          />
        ))}
      </div>
    </div>
  );
};
