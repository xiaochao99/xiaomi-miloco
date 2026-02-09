/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { Empty, Spin } from 'antd';
import { useTranslation } from 'react-i18next';
import { Card, ListItem } from '@/components';

import { classNames } from '@/utils/util';
import styles from './index.module.less';

/**
 * ServiceList Component - Service list component
 * 服务列表组件
 *
 * @param {Object} props - Component props
 * @returns {JSX.Element} ServiceList component
 */
const ServiceList = ({
  services,
  onSwitch,
  onEdit,
  onDelete
}) => {
  const { t } = useTranslation();

  return (
    <div className={classNames(styles.gridContainer, styles.columns2)}>
      {services.map((service, index) => (
        <Card key={service.id || index} className={styles.item}>
          <ListItem
            key={service.id}
            title={service.name}
            type={service.access_type}
            description={service.description}
            meta={`${t('mcpService.provider')}: ${service.provider || t('mcpService.unknown')}`}
            showSwitch={true}
            switchValue={service.enable}
            onSwitchChange={checked => onSwitch(service.id, checked)}
            showEdit={true}
            showDelete={true}
            onEdit={() => onEdit(service)}
            onDelete={() => onDelete(service.id)}
          />
        </Card>
      ))}
    </div>
  );
};

export default ServiceList;
