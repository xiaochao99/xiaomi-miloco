/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useEffect } from 'react';
import { Modal, Form, Input, Switch, Select, message } from 'antd';
import { useTranslation } from 'react-i18next';

const { Option } = Select;

/**
 * RTSP Camera Modal Component
 * @param {Object} props
 * @param {boolean} props.visible - Modal visibility
 * @param {Object} props.camera - Camera data for editing (null for creating)
 * @param {Function} props.onCancel - Cancel handler
 * @param {Function} props.onSave - Save handler
 */
export const RTSPCameraModal = ({ visible, camera, onCancel, onSave }) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const isEditing = !!camera;

  // Reset form when modal opens/closes or camera changes
  useEffect(() => {
    if (visible) {
      if (camera) {
        form.setFieldsValue({
          did: camera.did,
          name: camera.name,
          rtsp_url: camera.rtsp_url,
          enable_audio: camera.enable_audio,
          transport: camera.transport || 'udp',
          home_name: camera.home_name || '家',
          room_name: camera.room_name || '客厅',
        });
      } else {
        form.resetFields();
        form.setFieldsValue({
          enable_audio: false,
          transport: 'udp',
          home_name: '家',
          room_name: '客厅',
        });
      }
    }
  }, [visible, camera, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      const success = await onSave(values);
      if (success) {
        form.resetFields();
      }
    } catch (error) {
      console.error('Form validation failed:', error);
    }
  };

  const handleCancel = () => {
    form.resetFields();
    onCancel();
  };

  return (
    <Modal
      title={isEditing ? t('deviceManage.rtsp.editCamera') : t('deviceManage.rtsp.addCamera')}
      open={visible}
      onOk={handleOk}
      onCancel={handleCancel}
      okText={t('common.save')}
      cancelText={t('common.cancel')}
      width={560}
    >
      <Form
        form={form}
        layout="vertical"
        autoComplete="off"
      >
        <Form.Item
          name="did"
          label={t('deviceManage.rtsp.did')}
          rules={[
            { required: true, message: t('deviceManage.rtsp.pleaseEnterDid') },
            { pattern: /^[a-zA-Z0-9_-]+$/, message: t('deviceManage.rtsp.didFormatError') }
          ]}
        >
          <Input
            placeholder={t('deviceManage.rtsp.didPlaceholder')}
            disabled={isEditing}
          />
        </Form.Item>

        <Form.Item
          name="name"
          label={t('deviceManage.rtsp.name')}
          rules={[{ required: true, message: t('deviceManage.rtsp.pleaseEnterName') }]}
        >
          <Input placeholder={t('deviceManage.rtsp.namePlaceholder')} />
        </Form.Item>

        <Form.Item
          name="rtsp_url"
          label={t('deviceManage.rtsp.rtspUrl')}
          rules={[
            { required: true, message: t('deviceManage.rtsp.pleaseEnterUrl') },
            { pattern: /^rtsp:\/\//, message: t('deviceManage.rtsp.urlFormatError') }
          ]}
        >
          <Input placeholder="rtsp://192.168.1.100:554/stream" />
        </Form.Item>

        <Form.Item
          name="transport"
          label={t('deviceManage.rtsp.transport')}
          rules={[{ required: true }]}
        >
          <Select>
            <Option value="udp">UDP</Option>
            <Option value="tcp">TCP</Option>
          </Select>
        </Form.Item>

        <Form.Item
          name="enable_audio"
          label={t('deviceManage.rtsp.enableAudio')}
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>

        <Form.Item
          name="home_name"
          label={t('deviceManage.rtsp.homeName')}
          rules={[{ required: true }]}
        >
          <Input placeholder={t('deviceManage.rtsp.homeNamePlaceholder')} />
        </Form.Item>

        <Form.Item
          name="room_name"
          label={t('deviceManage.rtsp.roomName')}
          rules={[{ required: true }]}
        >
          <Input placeholder={t('deviceManage.rtsp.roomNamePlaceholder')} />
        </Form.Item>
      </Form>
    </Modal>
  );
};
