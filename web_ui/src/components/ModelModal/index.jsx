/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { Modal, Form, Input, Select, message } from 'antd';
import { getVendorModels } from "@/api";
import { useTranslation } from 'react-i18next';
import { useState, useMemo } from 'react';

/**
 * ModelModal Component - Modal for adding/editing cloud model configurations
 * 模型模态框组件 - 用于添加/编辑云模型配置的模态框
 *
 * @param {Object} props - Component props
 * @param {boolean} props.open - Modal open state
 * @param {Function} props.onOk - OK button callback
 * @param {Function} props.onCancel - Cancel button callback
 * @param {Object} props.form - Antd form instance
 * @param {Object} [props.editingModel] - Currently editing model data
 * @param {Array} props.llmOptions - Available LLM model options
 * @param {boolean} props.llmLoading - LLM options loading state
 * @param {Function} props.setLLMLoading - Set LLM loading state
 * @param {Function} props.setLLMOptions - Set LLM options
 * @returns {JSX.Element} Model modal component
 */
const ModelModal = ({
  open,
  onOk,
  onCancel,
  form,
  editingModel,
  llmOptions,
  llmLoading,
  setLLMLoading,
  setLLMOptions,
}) => {
  const { t } = useTranslation();
  const [customModelNames, setCustomModelNames] = useState([]);

  const groupedOptions = useMemo(() => {
    const options = [];

    if (llmOptions && llmOptions.length > 0) {
      options.push({
        label: t('modelModal.presetModels'),
        options: llmOptions
      });
    }

    if (customModelNames && customModelNames.length > 0) {
      options.push({
        label: t('modelModal.customModels'),
        options: customModelNames.map(name => ({ label: name, value: name }))
      });
    }

    return options;
  }, [llmOptions, customModelNames, t]);

  const getSelectedCustomNames = () => {
    const currentSelected = form.getFieldValue('name');
    const selectedValues = Array.isArray(currentSelected) ? currentSelected : (currentSelected ? [currentSelected] : []);

    return selectedValues.filter(val =>
      val && !llmOptions?.some(option => option.value === val)
    );
  };

  const handleSearch = (value) => {
    if (value && value.trim()) {
      const trimmedValue = value.trim();
      const isInPresetModels = llmOptions?.some(option => option.value === trimmedValue);

      if (!isInPresetModels) {
        setCustomModelNames(prev => {
          const selectedCustomNames = getSelectedCustomNames();
          const newCustomNames = [...selectedCustomNames];

          if (!newCustomNames.includes(trimmedValue)) {
            newCustomNames.push(trimmedValue);
          }

          return newCustomNames;
        });
      }
    } else {
      setCustomModelNames(getSelectedCustomNames());
    }
  };

  return (
    <Modal
      title={editingModel ? t('modelModal.editCloudModel') : t('modelModal.addCloudModel')}
      open={open}
      onOk={onOk}
      onCancel={onCancel}
      okText={t('common.confirm')}
      cancelText={t('common.cancel')}
      destroyOnClose
      centered
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          name: editingModel ? '' : [],
          apiKey: '',
          baseUrl: ''
        }}
      >
        <Form.Item
          label="Base URL"
          name="baseUrl"
          rules={[{ required: true, message: t('modelModal.pleaseEnterBaseUrl') }]}
        >
          <Input placeholder={t('modelModal.baseUrlPlaceholder')} />
        </Form.Item>
        <Form.Item
          label="API Key"
          name="apiKey"
          rules={[{ required: true, message: t('modelModal.pleaseEnterApiKey') }]}
        >
          <Input placeholder={t('modelModal.apiKeyPlaceholder')} />
        </Form.Item>
        <Form.Item
          label={t('modelModal.modelName')}
          name="name"
          rules={[{ required: true, message: t('modelModal.pleaseSelectModelName') }]}
        >
          <Select
            placeholder={t('modelModal.selectModelName')}
            showSearch
            notFoundContent={null}
            mode={editingModel ? undefined : 'multiple'}
            options={groupedOptions}
            onSearch={handleSearch}
            allowClear
            onDropdownVisibleChange={async (openDropdown) => {
              if (openDropdown) {
                setLLMOptions([])
                setLLMLoading(true);
                const baseUrl = form.getFieldValue('baseUrl');
                const apiKey = form.getFieldValue('apiKey');
                if (!baseUrl || !apiKey) {
                  message.warning(t('modelModal.fillBaseUrlAndApiKey'));
                  setLLMLoading(false);
                  return;
                }
                let list = [];
                try {
                  const res = await getVendorModels({ base_url: baseUrl, api_key: apiKey });
                  const { code, data } = res || {}
                  if (code === 0) {
                    list = data?.models?.data || [];
                  }
                } catch {
                  list = [];
                }
                if (!list || list.length === 0) {
                  message.info(t('modelModal.modelListNotFound'));
                } else {
                  setLLMOptions(list
                    .map(item => ({ label: item.id, value: item.id }))
                    .sort((a, b) => a.label.localeCompare(b.label))
                  );
                }
                setLLMLoading(false);
              }
            }}
            loading={llmLoading}
            filterOption={(input, option) => (option?.label ?? '').toLowerCase().includes(input.toLowerCase())}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default ModelModal;
