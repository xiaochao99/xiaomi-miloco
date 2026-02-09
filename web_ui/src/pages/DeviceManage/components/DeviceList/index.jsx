/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { Empty, Spin } from 'antd';
import { useTranslation } from 'react-i18next';
import DeviceCard from '../DeviceCard';
import styles from './index.module.less';

/**
 * DeviceList Component - Device list component
 * 设备列表组件
 *
 * @param {Object} devices - The devices data to display
 * @returns {JSX.Element} Device list component
 */
const DeviceList = ({ devices }) => {
  const { t } = useTranslation();

  return (
    <div className={styles.deviceGrid}>
      {devices.map((device) => (
        <DeviceCard key={device.did} device={device} />
      ))}
    </div>
  );
};

export default DeviceList;
