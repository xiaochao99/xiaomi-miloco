/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useState, useEffect, useRef } from 'react';
import { message } from 'antd';
import { useTranslation } from 'react-i18next';
import { getModelPurposes, getAllModels, setCurrentModel } from '@/api';

/**
 * useModelConfig - Model configuration hooks
 * 模型配置钩子
 */
export const useModelConfig = () => {
  const { t } = useTranslation();
  const [modelCheckList, setModelCheckList] = useState([]);
  const [allModels, setAllModels] = useState([]);
  const [currentModelConfig, setCurrentModelConfig] = useState({});
  const [modelLoading, setModelLoading] = useState(false);
  const isProcessingRef = useRef(false);

  const fetchModelCheckList = async () => {
    try {
      const res = await getModelPurposes();
      if (res && res?.code === 0) {
        setModelCheckList(res?.data || []);
      } else {
        message.error(res?.message || t('modelModal.fetchModelCheckListFailed'));
      }
    } catch (error) {
      console.error('fetchModelCheckList failed:', error);
    }
  };

  // fetch all models and current configuration
  const fetchAllModels = async () => {
    try {
      setModelLoading(true);
      const res = await getAllModels();
      if (res && res?.code === 0) {
        const models = res?.data?.models || [];
        const currentConfig = res?.data?.current_model || {};

        setAllModels(models);
        setCurrentModelConfig(currentConfig);
      } else {
        message.error(res?.message || t('modelModal.fetchAllModelsFailed'));
      }
    } catch (error) {
      console.error('fetchAllModels failed:', error);
    } finally {
      setModelLoading(false);
    }
  };

  // handle model selection change
  const handleModelChange = async (modelId, purpose) => {
    if (isProcessingRef.current) {
      return;
    }

    isProcessingRef.current = true;
    try {
      const res = await setCurrentModel(modelId, purpose);
      if (res && res?.code === 0) {
        message.success(t('modelModal.modelConfigUpdateSuccess'));
        await fetchAllModels();
      } else {
        message.error(res?.message || t('modelModal.modelConfigUpdateFailed'));
      }
    } finally {
      isProcessingRef.current = false;
    }
  };

  // generate model options
  const generateModelOptions = () => {
    return [
      ...allModels.map(model => ({
        value: model.id,
        label: `${model.local ? t('modelModal.localModel') : t('modelModal.cloudModel')} : ${model.model_name}`,
        loaded: model.loaded,
      }))
    ];
  };

  useEffect(() => {
    fetchModelCheckList();
    fetchAllModels();
  }, []);

  return {
    modelCheckList,
    allModels,
    currentModelConfig,
    modelLoading,
    handleModelChange,
    generateModelOptions,
    fetchAllModels,
  };
};
