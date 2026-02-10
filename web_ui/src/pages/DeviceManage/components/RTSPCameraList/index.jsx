/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { Table, Button, Popconfirm, Tag, Space, Empty } from 'antd';
import { EditOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styles from './index.module.less';

/**
 * RTSP Camera List Component
 * @param {Object} props
 * @param {Array} props.cameras - RTSP camera list
 * @param {boolean} props.loading - Loading state
 * @param {Function} props.onEdit - Edit handler
 * @param {Function} props.onDelete - Delete handler
 * @param {Function} props.onAdd - Add handler
 */
export const RTSPCameraList = ({ cameras, loading, onEdit, onDelete, onAdd }) => {
  const { t } = useTranslation();

  const columns = [
    {
      title: t('deviceManage.rtsp.name'),
      dataIndex: 'name',
      key: 'name',
      width: 150,
    },
    {
      title: t('deviceManage.rtsp.did'),
      dataIndex: 'did',
      key: 'did',
      width: 150,
    },
    {
      title: t('deviceManage.rtsp.rtspUrl'),
      dataIndex: 'rtsp_url',
      key: 'rtsp_url',
      ellipsis: true,
    },
    {
      title: t('deviceManage.rtsp.transport'),
      dataIndex: 'transport',
      key: 'transport',
      width: 100,
      render: (transport) => (
        <Tag color={transport === 'tcp' ? 'blue' : 'green'}>
          {transport?.toUpperCase() || 'UDP'}
        </Tag>
      ),
    },
    {
      title: t('deviceManage.rtsp.audio'),
      dataIndex: 'enable_audio',
      key: 'enable_audio',
      width: 100,
      render: (enable) => (
        <Tag color={enable ? 'green' : 'default'}>
          {enable ? t('common.enabled') : t('common.disabled')}
        </Tag>
      ),
    },
    {
      title: t('deviceManage.rtsp.location'),
      key: 'location',
      width: 150,
      render: (_, record) => (
        <span>{record.home_name} / {record.room_name}</span>
      ),
    },
    {
      title: t('common.operation'),
      key: 'action',
      width: 150,
      render: (_, record) => (
        <Space>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => onEdit(record)}
          >
            {t('common.edit')}
          </Button>
          <Popconfirm
            title={t('deviceManage.rtsp.deleteConfirm')}
            description={t('deviceManage.rtsp.deleteConfirmDesc')}
            onConfirm={() => onDelete(record.did)}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              {t('common.delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  if (!loading && cameras.length === 0) {
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
      <Table
        columns={columns}
        dataSource={cameras}
        rowKey="did"
        loading={loading}
        pagination={false}
        size="small"
        scroll={{ x: 'max-content' }}
      />
    </div>
  );
};
