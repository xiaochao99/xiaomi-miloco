/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { Button, Popconfirm } from 'antd';
import { useTranslation } from 'react-i18next';
import { EditOutlined, DeleteOutlined, ReloadOutlined, LoadingOutlined } from '@ant-design/icons';
import { Icon } from '@/components';
import llmIcon from '@/assets/images/llmIcon.png';
import styles from '../index.module.less';

/**
 * ModelItem Component - Model item component
 * 模型项组件
 *
 * @returns {JSX.Element} ModelItem component
 */
const ModelItem = ({
  model,
  canEdit = true,
  canDelete = true,
  onEdit,
  onDelete,
  // onRefresh
  cudaInfo,
  onSetModelLoaded,
  modelLoadingStates,
}) => {
  const { t } = useTranslation();

  const getVramUsageText = () => {
    if (!model.local || !model.estimate_vram_usage || !cudaInfo?.total || !cudaInfo?.free) {
      return '';
    }
    const estimated = (model.estimate_vram_usage || 0).toFixed(2);
    const free = (cudaInfo?.free || 0).toFixed(2);
    const total = (cudaInfo?.total || 0).toFixed(2);
    return `(${t('modelModal.estimated')} ${estimated}GB | ${t('modelModal.available')} ${free}GB | ${t('modelModal.total')} ${total}GB)`;
  };

  const handleModelLoadToggle = () => {
    if (onSetModelLoaded) {
      onSetModelLoaded(model.id, !model.loaded);
    }
  };

  const isLoading = modelLoadingStates?.[model.id] || false;

  return (
    <div className={styles.modelItem}>
      <div className={styles.modelInfo}>
        <img src={llmIcon} className={styles.modelIcon} />
        <div className={styles.modelNameContainer}>
          <span className={styles.modelName}>{model.name}</span>
          {model.local && (
            <span className={styles.vramUsage}>
              {getVramUsageText()}
            </span>
          )}
        </div>
      </div>
      <div className={styles.modelActions}>
        {model.local && onSetModelLoaded && (
          <Button
            type={model.loaded ? "default" : "primary"}
            size="small"
            loading={isLoading}
            icon={isLoading ? <LoadingOutlined /> : null}
            onClick={handleModelLoadToggle}
            disabled={isLoading}
          >
            {model.loaded ? t('common.unload') : t('common.load')}
          </Button>
        )}
        {canEdit && (
          <Button
            type="text"
            icon={<EditOutlined />}
            size="small"
            onClick={() => onEdit(model)}
          />
        )}
        {canDelete && (
          <Popconfirm
            title={t('common.confirmDelete')}
            onConfirm={() => onDelete(model.id)}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
            // okType="danger"
          >
            <Button
              type="text"
              icon={<DeleteOutlined />}
              size="small"
              // danger
            />
          </Popconfirm>
        )}
      </div>
    </div>
  );
};

export default ModelItem;
