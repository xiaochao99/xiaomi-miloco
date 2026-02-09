/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useState, useEffect, useCallback } from 'react';
import { message } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  getMiotSceneActions,
  getHaAutomationActions,
  refreshMiotScenes,
  refreshHaAutomation,
  executeSceneActions
} from '@/api';

export const useExecutionManage = () => {
  const { t } = useTranslation();
  const [haList, setHaList] = useState([]);
  const [scenesList, setScenesList] = useState([]);
  const [loadingStates, setLoadingStates] = useState({});
  const [loading, setLoading] = useState(false);

  // fetch mi home automation data
  const fetchScenesList = useCallback(async () => {
    try {
      const scenes = await getMiotSceneActions();
      setScenesList(scenes?.data || []);
    } catch (error) {
      console.error('fetchScenesList error', error);
      message.error(t('executionManage.getMiHomeAutomationDataFailed'));
    }
  }, []);

  // fetch ha automation data
  const fetchHaList = useCallback(async () => {
    try {
      const haListRes = await getHaAutomationActions();
      setHaList(haListRes?.data || []);
    } catch (error) {
      console.error('fetchHaList error', error);
      message.error(t('executionManage.getHaAutomationDataFailed'));
    }
  }, []);

  // refresh mi home automation data
  const refreshScenesData = useCallback(async () => {
    setLoading(true);
    try {
      const refreshRes = await refreshMiotScenes();
      if (refreshRes?.code === 0) {
        await fetchScenesList();
        message.success(t('executionManage.miHomeAutomationDataRefreshedSuccess'));
      } else {
        message.error(refreshRes?.message || t('executionManage.miHomeAutomationDataRefreshedFailed'));
      }
    } catch (error) {
      console.error('refreshScenesData error', error);
      message.error(t('executionManage.miHomeAutomationDataRefreshedFailed'));
    } finally {
      setLoading(false);
    }
  }, [fetchScenesList]);

  // refresh ha automation data
  const refreshHaData = useCallback(async () => {
    setLoading(true);
    try {
      const refreshRes = await refreshHaAutomation();
      if (refreshRes?.code === 0) {
        await fetchHaList();
        message.success(t('executionManage.haAutomationDataRefreshedSuccess'));
      } else {
        message.error(refreshRes?.message || t('executionManage.haAutomationDataRefreshedFailed'));
      }
    } catch (error) {
      console.error('refreshHaData error', error);
      message.error(t('executionManage.haAutomationDataRefreshedFailed'));
    } finally {
      setLoading(false);
    }
  }, [fetchHaList]);


  const refreshDataByTab = useCallback(async (tabKey) => {
    switch (tabKey) {
      case 'scenes':
        await refreshScenesData();
        break;
      case 'ha':
        await refreshHaData();
        break;
      default:
        setLoading(true);
        await Promise.all([fetchScenesList(), fetchHaList()]);
        setLoading(false);
        break;
    }
  }, [refreshScenesData, refreshHaData, fetchScenesList, fetchHaList]);

  // execute scene action
  const handleExecuteAction = useCallback(async (item) => {
    const itemId = item.id || item.introduction;
    setLoadingStates(prev => ({ ...prev, [itemId]: true }));

    try {
      const res = await executeSceneActions([item]);
      const data = res?.data || [];

      if (res?.code === 0 && data?.[0]) {
        message.success(res?.message);
      } else {
        message.error(res?.message);
      }
    } catch (error) {
      console.error('handleExecuteAction error', error);
      message.error(t('executionManage.executeActionFailed'));
    } finally {
      setLoadingStates(prev => ({ ...prev, [itemId]: false }));
    }
  }, []);

  useEffect(() => {
    const initData = async () => {
      setLoading(true);
      await Promise.all([fetchScenesList(), fetchHaList()]);
      setLoading(false);
    };
    initData();
  }, [fetchScenesList, fetchHaList]);

  return {
    haList,
    scenesList,
    loadingStates,
    loading,
    refreshDataByTab,
    handleExecuteAction,
    fetchScenesList,
    fetchHaList
  };
};
