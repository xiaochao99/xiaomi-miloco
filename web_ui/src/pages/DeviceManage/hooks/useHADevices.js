/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { getHADeviceList, getHaDevicesGrouped } from '@/api';

/**
 * useHADevices hook
 * 从后端获取 HA 实体列表与按设备分组信息，并在前端组合成“设备 -> 实体列表”的结构：
 * [
 *   {
 *     id: string;        // 设备ID（HA device_id）
 *     name: string;      // 设备名称
 *     area: string;      // 区域名称
 *     entities: [        // 该设备下的实体详情列表
 *       {
 *         entity_id: string;
 *         state: string;
 *         attributes: object;
 *         did?: string;
 *         name?: string;
 *       }
 *     ]
 *   }
 * ]
 */
export const useHADevices = () => {
  const { t } = useTranslation();
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchDevices = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      // 同时拉取实体列表与按设备分组数据
      const [entityResp, groupedResp] = await Promise.all([
        getHADeviceList(),
        getHaDevicesGrouped()
      ]);

      if (entityResp.code !== 0) {
        throw new Error(entityResp.message || 'Failed to fetch HA entities');
      }

      if (groupedResp.code !== 0) {
        throw new Error(groupedResp.message || 'Failed to fetch grouped HA devices');
      }

      const entities = entityResp.data || [];
      const grouped = groupedResp.data || {};

      // 建立 entity_id -> 实体详情 的索引，便于后续根据 entity_id 找详情
      const entityMap = new Map();
      entities.forEach((item) => {
        const entityId = item.entity_id || item.did;
        if (entityId) {
          entityMap.set(entityId, item);
        }
      });

      // 将后端按 device_id 分组的结果转为前端需要的数组结构
      const deviceList = Object.entries(grouped).map(([deviceId, info]) => {
        const {
          name,
          area,
          entities: entityIds = []
        } = info || {};

        const entityDetails = entityIds.map((eid) => {
          const entity = entityMap.get(eid);
          if (entity) {
            return entity;
          }
          // 兜底，防止模板返回了某些在 /ha/devices 中不存在的实体
          return {
            entity_id: eid,
            state: 'unknown',
            attributes: { friendly_name: eid }
          };
        });

        return {
          id: deviceId,
          name: name || deviceId,
          area: area || '',
          entities: entityDetails
        };
      });

      setDevices(deviceList);
    } catch (err) {
      console.error('fetchHADevicesFailed:', err);
      setError(t('deviceManage.fetchDeviceListFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  const refreshDevices = useCallback(async () => {
    await fetchDevices();
  }, [fetchDevices]);

  useEffect(() => {
    fetchDevices();
  }, [fetchDevices]);

  return {
    devices,
    loading,
    error,
    refreshDevices
  };
};
