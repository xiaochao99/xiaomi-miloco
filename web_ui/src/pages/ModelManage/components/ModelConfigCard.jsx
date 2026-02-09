/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useMemo } from 'react';
import { Select, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components';
import { useModelConfig } from '../hooks';
import styles from '../index.module.less';

const { Option } = Select;
const { Title } = Typography;

/**
 * ModelConfigCard Component - Model configuration card component
 * 模型配置卡片组件
 *
 * @param {Array} models - all models data
 * @returns {JSX.Element} ModelConfigCard component
 */
const ModelConfigCard = ({ models }) => {
  const { t } = useTranslation();

  const descriptionMap = {
    planning: {
      name: t('modelModal.planning'),
      description: t('modelModal.planningDesc'),
    },
    vision_understanding: {
      name: t('modelModal.visionUnderstanding'),
      description: t('modelModal.visionUnderstandingDesc'),
    },
  };

  const {
    modelCheckList,
    currentModelConfig,
    modelLoading,
    handleModelChange,
  } = useModelConfig();

  const generateModelOptions = () => {
    return models.map(model => ({
      value: model.id,
      label: `${model.local ? t('modelModal.localModel') : t('modelModal.cloudModel')} : ${model.name}`,
      loaded: model.loaded,
    }));
  };

  const modelStateHash = useMemo(() => {
    return models.map(m => `${m.id}-${m.loaded}`).join('|');
  }, [models]);

  return (
    <Card className={styles.modelConfigCard} contentClassName={styles.modelConfigCardContent}>
      <div className={styles.modelConfigCardTitle}>
        <Title style={{ marginBottom: 0 }} level={5}>{t('modelModal.advancedConfig')}</Title>
      </div>

      <div className={styles.modelConfigList}>
        {modelCheckList.map((item) => (
          <div key={descriptionMap[item.type]?.description || item.type} className={styles.configItem}>
            <Tooltip
              title={descriptionMap[item.type]?.description || item.type}
            >
              <div className={styles.configLabel}>{descriptionMap[item.type]?.name || item.type}</div>
            </Tooltip>

            <Select
              key={`${item.type}-${modelStateHash}`}
              value={currentModelConfig[item.type]}
              onChange={(value) => handleModelChange(value, item.type)}
              style={{ width: 382 }}
              placeholder={t('modelModal.pleaseSelectModel')}
              loading={modelLoading}
              allowClear
              onClear={() => handleModelChange(null, item.type)}
            >
              {generateModelOptions().map(option => {
                return (
                  <Option
                    key={option.value}
                    value={option.value}
                    disabled={!option.loaded}
                    style={{
                      color: option.loaded ? 'inherit' : '#bfbfbf',
                      cursor: option.loaded ? 'pointer' : 'not-allowed'
                    }}
                  >
                    {option.label}
                  </Option>
                );
              })}
            </Select>
          </div>
        ))}
      </div>
    </Card>
  );
};


export default ModelConfigCard;
