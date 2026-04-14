/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { useTranslation } from 'react-i18next';
import styles from './index.module.less';

const XiaoAIDeviceCard = ({ device }) => {
  const { t } = useTranslation();

  const formatDuration = (seconds) => {
    if (seconds < 60) return `${seconds}秒`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟`;
    return `${Math.floor(seconds / 3600)}小时${Math.floor((seconds % 3600) / 60)}分钟`;
  };

  return (
    <div className={styles.card}>
      <div className={styles.iconWrapper}>
        <div className={styles.icon}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="6" y="1" width="12" height="20" rx="2" />
            <circle cx="12" cy="16" r="3" />
            <path d="M12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" />
          </svg>
        </div>
      </div>
      <div className={styles.content}>
        <div className={styles.name}>
          {device.device_name || '未知设备'}
          <span className={styles.onlineBadge}>{t('deviceManage.online')}</span>
        </div>
        <div className={styles.info}>
          <div className={styles.infoItem}>
            <span className={styles.label}>{t('deviceManage.deviceId')}:</span>
            <span className={styles.value}>{device.client_id?.slice(0, 8)}...</span>
          </div>
          <div className={styles.infoItem}>
            <span className={styles.label}>{t('deviceManage.ipAddress')}:</span>
            <span className={styles.value}>{device.ip_address || '-'}</span>
          </div>
          <div className={styles.infoItem}>
            <span className={styles.label}>{t('deviceManage.connectedTime')}:</span>
            <span className={styles.value}>{formatDuration(device.connected_duration || 0)}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default XiaoAIDeviceCard;