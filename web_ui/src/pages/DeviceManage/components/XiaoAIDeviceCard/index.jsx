/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Input, Button, Tooltip } from 'antd';
import { EditOutlined, CheckOutlined, XOutlined } from '@ant-design/icons';
import { updateXiaomiBridgeDevice } from '@/api';
import styles from './index.module.less';

const XiaoAIDeviceCard = ({ device, onUpdate }) => {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState(device.device_name || '');
  const [saving, setSaving] = useState(false);

  const formatDuration = (seconds) => {
    if (seconds < 60) return `${seconds}秒`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟`;
    return `${Math.floor(seconds / 3600)}小时${Math.floor((seconds % 3600) / 60)}分钟`;
  };

  const handleSave = async () => {
    if (!editName.trim()) {
      setEditName(device.device_name || '');
      setIsEditing(false);
      return;
    }
    
    setSaving(true);
    try {
      const response = await updateXiaomiBridgeDevice(device.client_id, { device_name: editName.trim() });
      if (response?.code === 0) {
        if (onUpdate) {
          onUpdate(device.client_id, editName.trim());
        }
        setIsEditing(false);
      } else {
        console.error('Failed to update device name:', response?.message);
      }
    } catch (error) {
      console.error('Failed to update device name:', error);
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setEditName(device.device_name || '');
    setIsEditing(false);
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
        <div className={styles.nameRow}>
          {isEditing ? (
            <div className={styles.editContainer}>
              <Input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className={styles.editInput}
                autoFocus
                onPressEnter={handleSave}
              />
              <Button
                type="primary"
                size="small"
                icon={<CheckOutlined />}
                onClick={handleSave}
                loading={saving}
                className={styles.saveBtn}
              />
              <Button
                size="small"
                icon={<XOutlined />}
                onClick={handleCancel}
                className={styles.cancelBtn}
              />
            </div>
          ) : (
            <div className={styles.name}>
              <span>{device.device_name || '未知设备'}</span>
              <span className={styles.onlineBadge}>{t('deviceManage.online')}</span>
              <Tooltip title={t('deviceManage.editDeviceName')}>
                <button
                  className={styles.editButton}
                  onClick={() => setIsEditing(true)}
                >
                  <EditOutlined size={14} />
                </button>
              </Tooltip>
            </div>
          )}
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