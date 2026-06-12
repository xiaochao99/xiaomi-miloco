/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Tag, Switch, Popconfirm, Space, message } from 'antd';
import { EditOutlined, DeleteOutlined, CopyOutlined, VideoCameraOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { Card, Icon } from '@/components';
import { getRTSPServerConfig } from '@/api';
import styles from './index.module.less';

const RTSPCameraCard = ({ camera, onEdit, onDelete, onToggleEnable }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [serverConfig, setServerConfig] = useState({ port: 8554, lan_ip: window.location.hostname });
  const {
    did,
    name,
    rtsp_url,
    enable_audio,
    transport,
    home_name,
    room_name,
    online,
    source,
    enabled = true,
    _isMiot
  } = camera;

  const isMiot = _isMiot || source === 'miot';

  useEffect(() => {
    getRTSPServerConfig().then(res => {
      if (res && res.code === 0 && res.data) {
        setServerConfig(prev => ({
          ...prev,
          port: res.data.port || 8554,
          lan_ip: res.data.lan_ip || window.location.hostname,
        }));
      }
    }).catch(() => {});
  }, []);

  const streamUrl = `rtsp://${serverConfig.lan_ip}:${serverConfig.port}/${did}`;

  const handleCopyStream = () => {
    navigator.clipboard.writeText(streamUrl).then(() => {
      message.success(t('deviceManage.rtsp.streamCopied', '转流地址已复制'));
    }).catch(() => {
      const textarea = document.createElement('textarea');
      textarea.value = streamUrl;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      message.success(t('deviceManage.rtsp.streamCopied', '转流地址已复制'));
    });
  };

  const handleRecordingConfig = () => {
    navigate(`/home/recordingConfig?camera=${did}`);
  };

  const handlePlayback = () => {
    navigate(`/home/recordingPlayback?camera=${did}`);
  };

  return (
    <Card className={styles.cameraCard} contentClassName={styles.cameraCardContent}>
      {/* Card Header */}
      <div className={styles.cardHeader}>
        <div className={`${styles.cameraIcon} ${isMiot ? styles.cameraIconMiot : ''}`}>
          <Icon name="camera" size={28} />
        </div>
        <div className={styles.cameraInfo}>
          <div className={styles.cameraName} title={name}>{name}</div>
          <div className={styles.cameraLocation}>
            {home_name} | {room_name}
          </div>
        </div>
        <div className={styles.headerRight}>
          {isMiot && (
            <Tag color={online !== false ? 'green' : 'default'} style={{ marginRight: 8 }}>
              {online !== false ? t('deviceManage.rtsp.online', '在线') : t('deviceManage.rtsp.offline', '离线')}
            </Tag>
          )}
          {!isMiot && (
            <div className={styles.enableSwitch}>
              <Switch
                size="small"
                checked={enabled}
                onChange={(checked) => onToggleEnable && onToggleEnable(did, checked)}
              />
            </div>
          )}
        </div>
      </div>

      {/* Card Body */}
      <div className={styles.cardBody}>
        <div className={styles.infoRow}>
          <span className={styles.label}>{t('deviceManage.rtsp.did')}:</span>
          <span className={styles.value} title={did}>{did}</span>
        </div>
        {!isMiot && rtsp_url && (
          <div className={styles.infoRow}>
            <span className={styles.label}>{t('deviceManage.rtsp.rtspUrl')}:</span>
            <span className={styles.value} title={rtsp_url}>{rtsp_url}</span>
          </div>
        )}
        <div className={styles.infoRow}>
          <span className={styles.label}>{t('deviceManage.rtsp.streamUrl', '转流地址')}:</span>
          <span className={styles.value} title={streamUrl}>{streamUrl}</span>
        </div>
        <div className={styles.tagsRow}>
          {isMiot ? (
            <Tag color="blue">{t('deviceManage.rtsp.miotCamera', '米家摄像头')}</Tag>
          ) : (
            <>
              <Tag color={transport === 'tcp' ? 'blue' : 'green'}>
                {transport?.toUpperCase() || 'UDP'}
              </Tag>
              <Tag color={enable_audio ? 'green' : 'default'}>
                {enable_audio ? t('deviceManage.rtsp.audioEnabled') : t('deviceManage.rtsp.audioDisabled')}
              </Tag>
            </>
          )}
        </div>
      </div>

      {/* Card Footer */}
      <div className={styles.cardFooter}>
        <Space>
          <button
            className={styles.actionButton}
            onClick={handleCopyStream}
          >
            <CopyOutlined />
            <span>{t('deviceManage.rtsp.copyStream', '复制转流地址')}</span>
          </button>
          <button
            className={styles.actionButton}
            onClick={handleRecordingConfig}
          >
            <VideoCameraOutlined />
            <span>{t('deviceManage.rtsp.recordingConfig', '录像配置')}</span>
          </button>
          <button
            className={styles.actionButton}
            onClick={handlePlayback}
          >
            <PlayCircleOutlined />
            <span>{t('deviceManage.rtsp.playback', '录像回看')}</span>
          </button>
          {!isMiot && (
            <>
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
            </>
          )}
        </Space>
      </div>
    </Card>
  );
};

export default RTSPCameraCard;
