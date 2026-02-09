/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { Form } from 'antd';
import { useTranslation } from 'react-i18next';
import { ModelModal, Header, PageContent } from '@/components';
import { ModelServiceCard, ModelConfigCard } from './components';
import { useModelManagement } from './hooks';

/**
 * ModelManage Page - Model management page for managing AI models and configurations
 * 模型管理页面 - 用于管理AI模型和配置的页面
 *
 * @returns {JSX.Element} Model management page component
 */
const ModelManage = () => {
  const { t } = useTranslation();
  const [form] = Form.useForm();

  const {
    models,
    modalOpen,
    editingModel,
    llmOptions,
    llmLoading,
    loading,
    setLLMLoading,
    setLLMOptions,
    cudaInfo,
    modelLoadingStates,
    handleSetModelLoaded,
    openModal,
    closeModal,
    handleSubmit,
    handleDelete,
  } = useModelManagement();


  const handleModalOk = async () => {
    try {
      const values = await form.validateFields();
      await handleSubmit(form, values);
    } catch {
      // form validation failed
    }
  };

  // handle modal cancel
  const handleModalCancel = () => {
    closeModal();
    // reset form, set different initial values based on whether it is in edit mode
    form.setFieldsValue({
      name: editingModel ? '' : [],
      apiKey: '',
      baseUrl: '',
    });
  };

  // handle edit model
  const handleEditModel = (model) => {
    openModal(model);
    if (model) {
      form.setFieldsValue({
        name: model.name,
        apiKey: model.apiKey,
        baseUrl: model.baseUrl,
      });
    } else {
      form.setFieldsValue({
        name: [],
        apiKey: '',
        baseUrl: '',
      });
    }
  };

  // handle add model
  const handleAddModel = () => {
    handleEditModel(null);
  };

  return (
    <>
      <PageContent
        Header={<Header title={t('home.menu.modalManage')} />}
        // loading={loading}
      >
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          <ModelConfigCard models={models} />
          <ModelServiceCard
            models={models}
            onAddModel={handleAddModel}
            onEditModel={handleEditModel}
            onDeleteModel={handleDelete}
            cudaInfo={cudaInfo}
            onSetModelLoaded={handleSetModelLoaded}
            modelLoadingStates={modelLoadingStates}
          // onRefreshModels={fetchModels}
          />
        </div>
      </PageContent>

      {/* model edit modal */}
      <ModelModal
        open={modalOpen}
        onOk={handleModalOk}
        onCancel={handleModalCancel}
        form={form}
        editingModel={editingModel}
        llmOptions={llmOptions}
        llmLoading={llmLoading}
        setLLMLoading={setLLMLoading}
        setLLMOptions={setLLMOptions}
      />
    </>
  );
};

export default ModelManage;
