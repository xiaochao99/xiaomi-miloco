/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Spin, Empty, Button, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import XiaoAIDeviceCard from '../XiaoAIDeviceCard';
import { getXiaomiBridgeDevices } from '@/api';
import styles from './index.module.less';

const XiaoAIDeviceList = () => {
  const { t } = useTranslation();
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchDevices = async () => {
    setLoading(true);
    try {
      const response = await getXiaomiBridgeDevices();
      if (response?.code === 0) {
        setDevices(response.data || []);
      } else {
        message.error(response?.message || t('deviceManage.fetchFailed'));
      }
    } catch (error) {
      console.error('Failed to fetch XiaoAI devices:', error);
      message.error(t('deviceManage.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDevices();
    const interval = setInterval(fetchDevices, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleRefresh = () => {
    fetchDevices();
  };

  if (loading) {
    return (
      <div className={styles.loadingContainer}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.title}>
          <span className={styles.icon}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="6" y="1" width="12" height="20" rx="2" />
              <circle cx="12" cy="16" r="3" />
              <path d="M12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" />
            </svg>
          </span>
          <span>{t('deviceManage.xiaoaiDevices')}</span>
        </div>
        <Button
          type="text"
          icon={<ReloadOutlined />}
          onClick={handleRefresh}
          loading={loading}
        >
          {t('common.refresh')}
        </Button>
      </div>

      {devices.length === 0 ? (
        <Empty
          description={t('deviceManage.noXiaoaiDevice')}
          imageStyle={{ width: 72, height: 72 }}
        />
      ) : (
        <div className={styles.deviceGrid}>
          {devices.map((device) => (
            <XiaoAIDeviceCard key={device.client_id} device={device} />
          ))}
        </div>
      )}
    </div>
  );
};

export default XiaoAIDeviceList;