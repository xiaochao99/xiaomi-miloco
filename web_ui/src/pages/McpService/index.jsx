/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { useTranslation } from 'react-i18next';
import { Header, PageContent } from '@/components';
import EmptyRule from '@/assets/images/empty-rule.png';
import { ServiceList, ServiceForm } from './components';
import { useMcpServices, useMcpServiceForm, useTypeOptions } from './hooks';

/**
 * McpService Page - MCP service management page for managing Model Context Protocol services
 * MCP服务管理页面 - 用于管理模型上下文协议服务的页面
 *
 * @returns {JSX.Element} MCP service management page component
 */
const McpService = () => {
  const { t } = useTranslation();

  const {
    services,
    loading,
    handleSwitch,
    handleDelete,
    createService,
    updateService,
  } = useMcpServices();

  const {
    modalOpen,
    editId,
    formType,
    form,
    submitLoading,
    openAddForm,
    openEditForm,
    closeForm,
    handleFormValuesChange,
    transformFormData,
    setLoading,
  } = useMcpServiceForm();

  const TYPE_OPTIONS = useTypeOptions();

  const handleFormSubmit = async () => {
    try {
      setLoading(true);
      const values = await form.validateFields();
      const apiData = transformFormData(values);

      if (editId) {
        const result = await updateService(editId, apiData);
        if (result.success) {
          closeForm();
        }
      } else {
        const result = await createService(apiData);
        if (result.success) {
          closeForm();
        }
      }
    } catch (error) {
      console.error('Failed to save service:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <PageContent
        Header={(
          <Header
            title={t('home.menu.mcpService')}
            buttonText={t('mcpService.addService')}
            buttonHandleCallback={openAddForm}
          />
        )}
        loading={loading}
        showEmptyContent={!loading && services.length === 0}
        emptyContentProps={{
          description: t('mcpService.noServices'),
          imageStyle: { width: 72, height: 72 },
          image: EmptyRule,
        }}
      >
        <ServiceList
          services={services}
          onSwitch={handleSwitch}
          onEdit={openEditForm}
          onDelete={handleDelete}
        />

      </PageContent>

      <ServiceForm
        modalOpen={modalOpen}
        editId={editId}
        formType={formType}
        form={form}
        submitLoading={submitLoading}
        TYPE_OPTIONS={TYPE_OPTIONS}
        onCancel={closeForm}
        onOk={handleFormSubmit}
        onValuesChange={handleFormValuesChange}
      />
    </>
  )

};

export default McpService;
