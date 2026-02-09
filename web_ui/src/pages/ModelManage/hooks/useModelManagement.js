/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useState, useEffect } from 'react';
import { message } from 'antd';
import { useTranslation } from 'react-i18next';
import { getAllModels, deleteModel, createModel, updateModel, getCudaInfo, setModelLoad } from '@/api';

/**
 * useModelManagement - Model management hooks
 * 模型管理钩子
 */
export const useModelManagement = () => {
  const { t } = useTranslation();
  const [models, setModels] = useState([]);
  const [selectedModelId, setSelectedModelId] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingModel, setEditingModel] = useState(null);
  const [llmOptions, setLLMOptions] = useState([]);
  const [llmLoading, setLLMLoading] = useState(false);
  const [cudaInfo, setCudaInfo] = useState(null);
  const [modelLoadingStates, setModelLoadingStates] = useState({});
  const [loading, setLoading] = useState(true);

  const refreshModels = async () => {
    setLoading(true);
    await fetchModels();
    await fetchCudaInfo();
    setLoading(false);
  };

  // fetch CUDA info
  const fetchCudaInfo = async () => {
    try {
      const res = await getCudaInfo();
      if (res && res.code === 0) {
        setCudaInfo(res.data);
      } else {
        message.error(res?.message || t('modelModal.fetchCudaInfoFailed'));
      }
    } catch (error) {
      console.error('fetch CUDA info failed:', error);
      message.error(t('modelModal.fetchCudaInfoFailed'));
    }
  };

  // set model loaded state
  const handleSetModelLoaded = async (modelId, loaded) => {
    try {
      setModelLoadingStates(prev => ({ ...prev, [modelId]: true }));
      const model = models.find(m => m.id === modelId);
      if (!model) {
        message.error(t('modelModal.modelNotFound'));
        return;
      }
      const res = await setModelLoad({ local_model_name: model.name, load:loaded });
      if (res && res.code === 0) {
        message.success(loaded ? t('modelModal.modelLoadSuccess') : t('modelModal.modelUnloadSuccess'));
        await refreshModels();
      } else {
        message.error(res?.message || t('modelModal.operationFailed'));
      }
    } catch (error) {
      console.error('handleSetModelLoaded failed:', error);
      message.error(t('modelModal.operationFailed'));
    } finally {
      setModelLoadingStates(prev => ({ ...prev, [modelId]: false }));
    }
  };

  // fetch models
  const fetchModels = async () => {
    try {
      const res = await getAllModels();
      if (res && res.code === 0) {
        const models = res?.data?.models || [];
        const id = res?.data?.current_model_id;
        const modelsFromApi = models.map((item) => ({
          id: item.id,
          name: item.model_name,
          apiKey: item.api_key,
          baseUrl: item.base_url,
          local: item.local,
          estimate_vram_usage: item.estimate_vram_usage,
          loaded: item.loaded,
        }));
        setModels(modelsFromApi);
        setSelectedModelId(id);
      } else {
        message.error(res?.message || t('modelModal.fetchModelCheckListFailed'));
      }
    } catch (error) {
      console.error('fetchModels failed:', error);
    }
  };

  // open modal (add/edit)
  const openModal = (model = null) => {
    setEditingModel(model);
    setModalOpen(true);
  };

  // close modal
  const closeModal = () => {
    setModalOpen(false);
    setEditingModel(null);
  };

  // submit form
  const handleSubmit = async (form, values) => {
    try {
      if (editingModel) {
        // edit model - single select logic
        const res = await updateModel(editingModel.id, {
          model_name: values.name,
          base_url: values.baseUrl,
          api_key: values.apiKey,
        });
        if (res && res.code === 0) {
          await refreshModels();
          message.success(t('common.editSuccess'));
          closeModal();
        } else {
          message.error(res?.message || t('common.editFail'));
        }
      } else {
        // add model - multi select logic
        const modelNames = Array.isArray(values.name) ? values.name : [values.name];
        const res = await createModel({
          model_names: modelNames,
          base_url: values.baseUrl,
          api_key: values.apiKey,
        });

        if (res && res.code === 0) {
          await refreshModels();
          message.success(t('common.addSuccess'));
          closeModal();
        } else {
          message.error(res?.message || t('common.addFail'));
        }
      }
    } catch {
      message.error(editingModel ? t('common.editFail') : t('common.addFail'));
    }
  };

  // delete model
  const handleDelete = async (id) => {
    if (id !== 'local') {
      try {
        const res = await deleteModel(id);
        if (res && res.code === 0) {
          message.success(t('common.deleteSuccess'));
          await refreshModels();
        } else {
          message.error(res?.message || t('common.deleteFail'));
        }
      } catch {
        message.error(t('common.deleteFail'));
      }
    }
  };

  useEffect(() => {
    refreshModels();
  }, []);

  return {
    models,
    selectedModelId,
    modalOpen,
    editingModel,
    llmOptions,
    llmLoading,
    loading,
    setLLMLoading,
    setLLMOptions,
    cudaInfo,
    modelLoadingStates,
    fetchModels,
    fetchCudaInfo,
    handleSetModelLoaded,
    openModal,
    closeModal,
    handleSubmit,
    handleDelete,
  };
};
