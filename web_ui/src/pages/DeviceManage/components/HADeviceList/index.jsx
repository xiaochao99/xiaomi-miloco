/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState, useMemo, useCallback, memo } from 'react';
import { Empty, Spin, Tag, Drawer } from 'antd';
import { useTranslation } from 'react-i18next';
import HADeviceCard from '../HADeviceCard';
import { Icon } from '@/components';
import styles from './index.module.less';

/**
 * HAEntityItem Component - Single entity item display
 * 使用 memo 包裹，避免不必要的重新渲染
 */
const HAEntityItem = memo(({ entity }) => {
  const { t } = useTranslation();
  const { entity_id, state, attributes = {} } = entity;
  const friendlyName = attributes.friendly_name || entity_id;
  const domain = entity_id.split('.')[0];

  // Get state color based on entity state
  const getStateColor = (stateValue) => {
    if (stateValue === 'on' || stateValue === 'open' || stateValue === 'playing') return 'green';
    if (stateValue === 'off' || stateValue === 'closed' || stateValue === 'idle') return 'default';
    if (stateValue === 'unavailable' || stateValue === 'unknown') return 'red';
    return 'blue';
  };

  // Format state display
  const formatState = (stateValue) => {
    if (stateValue === 'unavailable') return t('deviceManage.unavailable');
    if (stateValue === 'unknown') return t('deviceManage.unknown');
    return stateValue;
  };

  // Get domain icon
  const getDomainIcon = (domainName) => {
    const iconMap = {
      light: 'light',
      switch: 'switch',
      sensor: 'sensor',
      climate: 'climate',
      cover: 'cover',
      fan: 'fan',
      lock: 'lock',
      media_player: 'media',
      camera: 'camera',
    };
    return iconMap[domainName] || 'menuDevice';
  };

  return (
    <div className={styles.entityItem}>
      <div className={styles.entityIcon}>
        <Icon name={getDomainIcon(domain)} size={20} />
      </div>
      <div className={styles.entityInfo}>
        <div className={styles.entityName} title={friendlyName}>
          {friendlyName}
        </div>
        <div className={styles.entityId}>{entity_id}</div>
      </div>
      <div className={styles.entityState}>
        <Tag color={getStateColor(state)}>{formatState(state)}</Tag>
      </div>
    </div>
  );
});

/**
 * HADeviceList Component - Home Assistant Device List with Card Layout
 * 设备管理HA设备列表 - 按设备卡片展示，点击卡片展开实体列表
 *
 * @param {Object} props
 * @param {Array} props.devices - HA devices data from hook (已按设备分组，形如 { id, name, area, entities })
 * @param {boolean} props.loading - Loading state
 * @returns {JSX.Element} Device list component
 */
const HADeviceList = ({ devices, loading }) => {
  const { t } = useTranslation();
  const [selectedDeviceId, setSelectedDeviceId] = useState(null);

  // 使用 useCallback 缓存回调，避免子组件不必要的重新渲染
  const handleDeviceClick = useCallback((deviceId) => {
    setSelectedDeviceId(deviceId);
  }, []);

  const handleCloseDrawer = useCallback(() => {
    setSelectedDeviceId(null);
  }, []);

  // devices 已经是“按设备分组”的数组结构，这里仅做一次防御性拷贝/排序
  const groupedDevices = useMemo(() => {
    if (!devices || devices.length === 0) return [];
    return [...devices].sort((a, b) => {
      if (a.area && !b.area) return -1;
      if (!a.area && b.area) return 1;
      return (a.area || '').localeCompare(b.area || '') ||
             (a.name || '').localeCompare(b.name || '');
    });
  }, [devices]);

  const selectedDevice = useMemo(() => {
    return groupedDevices.find(d => d.id === selectedDeviceId);
  }, [groupedDevices, selectedDeviceId]);

  if (loading) {
    return (
      <div className={styles.loadingContainer}>
        <Spin size="large" />
        <span className={styles.loadingText}>{t('common.loading')}</span>
      </div>
    );
  }

  if (!groupedDevices || groupedDevices.length === 0) {
    return (
      <div className={styles.emptyContainer}>
        <Empty
          description={t('deviceManage.noHADevice')}
          imageStyle={{ width: 72, height: 72 }}
        />
      </div>
    );
  }

  return (
    <div className={styles.container}>
      {/* Device Cards Grid */}
      <div className={styles.deviceGrid}>
        {groupedDevices.map((device) => (
          <HADeviceCard
            key={device.id}
            device={device}
            onClick={handleDeviceClick}
          />
        ))}
      </div>

      {/* Entity Drawer - Shows when a device is selected */}
      <Drawer
        title={
          <div className={styles.drawerTitle}>
            <Icon name="menuDevice" size={20} />
            <span className={styles.deviceName} title={selectedDevice?.name}>
              {selectedDevice?.name}
            </span>
            {selectedDevice && (
              <Tag color="blue">{selectedDevice.entities.length} {t('deviceManage.entities')}</Tag>
            )}
          </div>
        }
        placement="right"
        width={480}
        onClose={handleCloseDrawer}
        open={!!selectedDeviceId}
        className={styles.entityDrawer}
        destroyOnClose={true}
        maskClosable={true}
      >
        {selectedDevice && (
          <div className={styles.drawerContent}>
            {/* Device Info Section */}
            <div className={styles.deviceInfoSection}>
              <div className={styles.infoRow}>
                <span className={styles.infoLabel}>{t('deviceManage.deviceId')}:</span>
                <span className={styles.infoValue} title={selectedDevice.id}>{selectedDevice.id}</span>
              </div>
              {selectedDevice.area && (
                <div className={styles.infoRow}>
                  <span className={styles.infoLabel}>{t('deviceManage.area')}:</span>
                  <span className={styles.infoValue}>{selectedDevice.area}</span>
                </div>
              )}
            </div>

            {/* Entity List Section - 如果实体数量过多(>100)，建议使用虚拟滚动 */}
            <div className={styles.entityListSection}>
              <div className={styles.sectionTitle}>
                {t('deviceManage.entityList')}
                <span className={styles.entityCount}> ({selectedDevice.entities.length})</span>
              </div>
              <div className={styles.entityList}>
                {selectedDevice.entities.map((entity, index) => (
                  <HAEntityItem
                    key={entity.did || entity.entity_id || index}
                    entity={entity}
                  />
                ))}
              </div>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default HADeviceList;
