/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Icon } from '@/components';
import styles from './index.module.less';

/**
 * HADeviceCard Component - Home Assistant Device Card
 * HA设备卡片组件 - 按设备显示，包含设备名称、区域、实体数量等信息
 *
 * @param {Object} props
 * @param {Object} props.device - Device data {id, name, area, entities}
 * @param {Function} props.onClick - Click handler to show entities
 * @returns {JSX.Element} Device card component
 */
const HADeviceCard = ({ device, onClick }) => {
  const { t } = useTranslation();
  const { id, name, area, entities = [] } = device;
  const entityCount = entities.length;

  const handleClick = () => {
    onClick(id);
  };

  return (
    <Card
      className={styles.deviceCard}
      contentClassName={styles.deviceCardContent}
      onClick={handleClick}
    >
      <div className={styles.cardHeader}>
        <div className={styles.deviceIcon}>
          <Icon name="menuDevice" size={24} />
        </div>
        <div className={styles.deviceInfo}>
          <div className={styles.deviceName} title={name}>{name}</div>
          <div className={styles.deviceArea}>
            {area || t('deviceManage.defaultArea')}
          </div>
        </div>
      </div>
      <div className={styles.cardFooter}>
        <div className={styles.entityCount}>
          <span className={styles.count}>{entityCount}</span>
          <span className={styles.label}>{t('deviceManage.entities')}</span>
        </div>
        <div className={styles.arrowIcon}>
          <Icon name="arrowRight" size={16} />
        </div>
      </div>
    </Card>
  );
};

export default HADeviceCard;
