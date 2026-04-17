/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Spin, Empty, message } from 'antd';
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

  const handleDeviceUpdate = (clientId, newName) => {
    setDevices(prevDevices => 
      prevDevices.map(device => 
        device.client_id === clientId 
          ? { ...device, device_name: newName }
          : device
      )
    );
    message.success(t('deviceManage.deviceNameUpdated'));
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
      {devices.length === 0 ? (
        <Empty
          description={t('deviceManage.noXiaoaiDevice')}
          imageStyle={{ width: 72, height: 72 }}
        />
      ) : (
        <div className={styles.deviceGrid}>
          {devices.map((device) => (
            <XiaoAIDeviceCard 
              key={device.client_id} 
              device={device} 
              onUpdate={handleDeviceUpdate}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default XiaoAIDeviceList;