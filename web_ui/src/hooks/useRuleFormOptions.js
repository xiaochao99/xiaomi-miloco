/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useState, useEffect } from 'react';
import { getCameraList, getMiotSceneActions, getHaAutomationActions, refreshMiotCamera, refreshMiotScenes, refreshHaAutomation } from '@/api';

/**
 * Hook for fetching camera and action options for rule form
 * 获取规则表单的摄像头和动作选项的Hook
 *
 * @param {boolean} autoFetch - Whether to fetch automatically on mount
 * @returns {Object} Camera and action options with loading states
 */
export const useRuleFormOptions = (autoFetch = true) => {
  const [cameraOptions, setCameraOptions] = useState([]);
  const [actionOptions, setActionOptions] = useState([]);
  const [cameraLoading, setCameraLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const fetchCameraList = async () => {
    setCameraLoading(true);
    try {
      const cameraListRes = await getCameraList();
      setCameraOptions(cameraListRes?.data || []);
    } catch (error) {
      console.error('fetchCameraList error', error);
    } finally {
      setCameraLoading(false);
    }
  };

  const fetchActionOptions = async () => {
    setActionLoading(true);
    try {
      const [miotRes, haRes] = await Promise.all([
        getMiotSceneActions(),
        getHaAutomationActions(),
      ]);

      const allActions = [
        ...(miotRes?.data || []),
        ...(haRes?.data || []),
      ];

      setActionOptions(allActions);
    } catch (error) {
      console.error('fetchActionOptions error', error);
    } finally {
      setActionLoading(false);
    }
  };


  const refreshCameras = async () => {
    setCameraLoading(true);
    try {
      const res = await refreshMiotCamera();
      if (res?.code === 0) {
        await fetchCameraList();
      }
      return res;
    } catch (error) {
      console.error('refreshCameras error', error);
      throw error;
    } finally {
      setCameraLoading(false);
    }
  };

  const refreshActions = async () => {
    setActionLoading(true);
    try {
      const [miotRes, haRes] = await Promise.all([
        refreshMiotScenes(),
        refreshHaAutomation(),
      ]);

      if (miotRes?.code === 0 && haRes?.code === 0) {
        await fetchActionOptions();
      }
      return { code: miotRes?.code === 0 && haRes?.code === 0 ? 0 : 1 };
    } catch (error) {
      console.error('refreshActions error', error);
      throw error;
    } finally {
      setActionLoading(false);
    }
  };


  useEffect(() => {
    if (autoFetch) {
      fetchCameraList();
      fetchActionOptions();
    }
  }, [autoFetch]);

  return {
    cameraOptions,
    actionOptions,
    cameraLoading,
    actionLoading,
    fetchCameraList,
    fetchActionOptions,
    refreshCameras,
    refreshActions,
  };
};

