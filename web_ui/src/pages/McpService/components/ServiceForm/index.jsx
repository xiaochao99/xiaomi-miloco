/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { Modal, Form, Input, Select, Row, Col } from 'antd';
import { useTranslation } from 'react-i18next';
import styles from './index.module.less';

const { Option } = Select;

/**
 * ServiceForm Component - Service form component
 * 服务表单组件
 *
 * @param {Object} props - Component props
 * @returns {JSX.Element} ServiceForm component
 */
const ServiceForm = ({
  modalOpen,
  editId,
  formType,
  form,
  submitLoading,
  TYPE_OPTIONS,
  onCancel,
  onOk,
  onValuesChange,
}) => {
  const { t } = useTranslation();

  return (
    <Modal
      open={modalOpen}
      title={editId ? t('mcpService.editService') : t('mcpService.addService')}
      onCancel={onCancel}
      onOk={onOk}
      okText={editId ? t('common.save') : t('common.add')}
      cancelText={t('common.cancel')}
      confirmLoading={submitLoading}
      destroyOnClose
      width={600}
    >
      <Form
        form={form}
        layout="vertical"
        className={styles.modalForm}
        initialValues={{ type: 'http_sse', timeout: 60, enable: true }}
        onValuesChange={onValuesChange}
      >
        <Form.Item
          name="type"
          required
          label={<span>{t('mcpService.accessType')}</span>}
          rules={[{ required: true, message: t('mcpService.selectAccessType')}]}
        >
          <Select style={{ width: '100%' }}>
            {TYPE_OPTIONS.map(opt => (
              <Option value={opt.value} key={opt.value}>{opt.label}</Option>
            ))}
          </Select>
        </Form.Item>
        <Form.Item
          name="name"
          required
          label={<span>{t('mcpService.name')}</span>}
          rules={[{ required: true, message: t('mcpService.enterServiceName') }]}
        >
          <Input maxLength={32} placeholder={t('mcpService.enterServiceName')} />
        </Form.Item>

        <Form.Item
          name="desc"
          label={t('mcpService.description')}
        >
          <Input.TextArea maxLength={128} autoSize={{ minRows: 2, maxRows: 4 }} placeholder={t('mcpService.enterDescription')} />
        </Form.Item>

        <Row gutter={12}>
          <Col span={12}>
            <Form.Item name="provider" label={t('mcpService.provider')}>
              <Input placeholder={t('mcpService.providerPlaceholder')} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="providerUrl" label={t('mcpService.providerWebsite')}>
              <Input placeholder={t('mcpService.providerWebsitePlaceholder')} />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item name="timeout" label={t('mcpService.timeout')}>
          <Input type="number" min={1} max={600} placeholder="60" />
        </Form.Item>

        {formType === 'http_sse' || formType === 'streamable_http' ? (
          <>
            <Form.Item
              name="url"
              required
              label={<span>URL</span>}
              rules={[{ required: true, message: t('mcpService.pleaseEnterUrl') }]}
            >
              <Input placeholder={t('mcpService.pleaseEnterUrl')} />
            </Form.Item>
            <Form.Item name="token" label={t('mcpService.requestHeaderToken')}>
              <Input placeholder={t('mcpService.tokenTip')} />
            </Form.Item>
          </>
        ) : (
          <>
            <Form.Item
              name="command"
              required
              label={<span>{t('mcpService.command')}</span>}
              rules={[{ required: true, message: t('mcpService.pleaseEnterCommand') }]}
            >
              <Input placeholder={t('mcpService.exampleCommand')} />
            </Form.Item>
            <Form.Item name="args" label={t('mcpService.args')}>
              <Input placeholder={t('mcpService.exampleArgs')} />
            </Form.Item>
            <Form.Item name="workingDirectory" label={t('mcpService.workingDirectory')}>
              <Input placeholder={t('mcpService.workingDirectoryPlaceholder')} />
            </Form.Item>
            <Form.Item name="env" label={t('mcpService.envVars')}>
              <Input.TextArea
                placeholder={t('mcpService.exampleEnv')}
                autoSize={{ minRows: 3, maxRows: 6 }}
              />
            </Form.Item>
          </>
        )}
      </Form>
    </Modal>
  );
};

export default ServiceForm;
