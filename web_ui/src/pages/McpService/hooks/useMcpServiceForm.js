/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useState } from 'react';
import { Form } from 'antd';
import { useTranslation } from 'react-i18next';

// use type options
export const useTypeOptions = () => {
  const { t } = useTranslation();

  return [
    { label: t('mcpService.accessTypeOptions.httpSse'), value: 'http_sse' },
    { label: t('mcpService.accessTypeOptions.streamableHttp'), value: 'streamable_http' },
    { label: t('mcpService.accessTypeOptions.stdio'), value: 'stdio' },
  ];
};

export const useMcpServiceForm = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const [editId, setEditId] = useState(null);
  const [formType, setFormType] = useState('http_sse');
  const [submitLoading, setSubmitLoading] = useState(false);
  const [form] = Form.useForm();

  const openAddForm = () => {
    setEditId(null);
    setFormType('http_sse');
    form.resetFields();
    form.setFieldsValue({
      type: 'http_sse',
      timeout: 20,
      description: '',
      provider: '',
      provider_website: '',
    });
    setModalOpen(true);
  };

  // open edit form
  const openEditForm = (service) => {
    setEditId(service.id);
    setFormType(service.access_type || 'http_sse');

    // convert data format to fit form
    const formData = {
      ...service,
      type: service.access_type,
      desc: service.description,
      providerUrl: service.provider_website,
      token: service.request_header_token,
      env: service.env_vars ? JSON.stringify(service.env_vars, null, 2) : '',
      args: service.args ? service.args.join(' ') : '',
      workingDirectory: service.working_directory,
    };

    form.setFieldsValue(formData);
    setModalOpen(true);
  };


  const closeForm = () => {
    setModalOpen(false);
    setSubmitLoading(false);
  };


  const handleFormValuesChange = (_, allValues) => {
    setFormType(allValues.type);
  };


  const setLoading = (loading) => {
    setSubmitLoading(loading);
  };


  const transformFormData = (values) => {
    const apiData = {
      access_type: values.type,
      name: values.name,
      description: values.desc || '',
      provider: values.provider || '',
      provider_website: values.providerUrl || '',
      timeout: values.timeout || 20,
    };

    // enable field processing: set to true when adding, completely exclude when editing
    if (!editId) {
      apiData.enable = true;
    }

    // add specific fields according to type
    if (values.type === 'http_sse' || values.type === 'streamable_http') {
      apiData.url = values.url;
      apiData.request_header_token = values.token || '';
    } else if (values.type === 'stdio') {
      apiData.command = values.command;
      apiData.args = values.args ? values.args.split(' ').filter(arg => arg.trim()) : [];
      apiData.working_directory = values.workingDirectory || '';


      if (values.env) {
        try {
          apiData.env_vars = JSON.parse(values.env);
        } catch {
          const envVars = {};
          values.env.split('\n').forEach(line => {
            const [key, value] = line.split('=');
            if (key && value) {
              envVars[key.trim()] = value.trim();
            }
          });
          apiData.env_vars = envVars;
        }
      }
    }

    return apiData;
  };

  return {
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
  };
};
