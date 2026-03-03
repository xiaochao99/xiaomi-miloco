/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { useTranslation } from 'react-i18next';
import { Tag, Switch, Popconfirm, Space } from 'antd';
import { EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { Card, Icon } from '@/components';
import styles from './index.module.less';

/**
 * RTSPCameraCard Component - RTSP Camera Card
 * RTSP摄像头卡片组件 - 卡片形式展示摄像头信息
 *
 * @param {Object} props
 * @param {Object} props.camera - Camera data
 * @param {Function} props.onEdit - Edit handler
 * @param {Function} props.onDelete - Delete handler
 * @param {Function} props.onToggleEnable - Toggle enable status handler
 * @returns {JSX.Element} Camera card component
 */
const RTSPCameraCard = ({ camera, onEdit, onDelete, onToggleEnable }) => {
  const { t } = useTranslation();
  const { 
    did, 
    name, 
    rtsp_url, 
    enable_audio, 
    transport, 
    home_name, 
    room_name,
    enabled = true 
  } = camera;

  return (
    <Card className={styles.cameraCard} contentClassName={styles.cameraCardContent}>
      {/* Card Header */}
      <div className={styles.cardHeader}>
        <div className={styles.cameraIcon}>
          <Icon name="camera" size={28} />
        </div>
        <div className={styles.cameraInfo}>
          <div className={styles.cameraName} title={name}>{name}</div>
          <div className={styles.cameraLocation}>
            {home_name} | {room_name}
          </div>
        </div>
        <div className={styles.enableSwitch}>
          <Switch 
            size="small" 
            checked={enabled}
            onChange={(checked) => onToggleEnable && onToggleEnable(did, checked)}
          />
        </div>
      </div>

      {/* Card Body */}
      <div className={styles.cardBody}>
        <div className={styles.infoRow}>
          <span className={styles.label}>{t('deviceManage.rtsp.did')}:</span>
          <span className={styles.value} title={did}>{did}</span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.label}>{t('deviceManage.rtsp.rtspUrl')}:</span>
          <span className={styles.value} title={rtsp_url}>{rtsp_url}</span>
        </div>
        <div className={styles.tagsRow}>
          <Tag color={transport === 'tcp' ? 'blue' : 'green'}>
            {transport?.toUpperCase() || 'UDP'}
          </Tag>
          <Tag color={enable_audio ? 'green' : 'default'}>
            {enable_audio ? t('deviceManage.rtsp.audioEnabled') : t('deviceManage.rtsp.audioDisabled')}
          </Tag>
        </div>
      </div>

      {/* Card Footer */}
      <div className={styles.cardFooter}>
        <Space>
          <button 
            className={styles.actionButton}
            onClick={() => onEdit && onEdit(camera)}
          >
            <EditOutlined />
            <span>{t('common.edit')}</span>
          </button>
          <Popconfirm
            title={t('deviceManage.rtsp.deleteConfirm')}
            description={t('deviceManage.rtsp.deleteConfirmDesc')}
            onConfirm={() => onDelete && onDelete(did)}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
          >
            <button className={`${styles.actionButton} ${styles.deleteButton}`}>
              <DeleteOutlined />
              <span>{t('common.delete')}</span>
            </button>
          </Popconfirm>
        </Space>
      </div>
    </Card>
  );
};

export default RTSPCameraCard;
