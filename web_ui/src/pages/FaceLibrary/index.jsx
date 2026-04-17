/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useMemo, useState, useEffect } from 'react';
import { Button, Card as AntCard, Form, Input, message, Modal, Space, Table, Tabs, Upload } from 'antd';
import { PlusOutlined, DeleteOutlined, SearchOutlined, UploadOutlined } from '@ant-design/icons';
import { Header } from '@/components';
import { enrollFace, listFaceProfiles, deleteFaceProfile, searchFaces } from '@/api';

const fileToBase64 = (file) => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(reader.result);
  reader.onerror = reject;
  reader.readAsDataURL(file);
});

const FaceLibrary = () => {
  const [profiles, setProfiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [enrollOpen, setEnrollOpen] = useState(false);
  const [enrollForm] = Form.useForm();
  const [enrollImageBase64, setEnrollImageBase64] = useState(null);

  const [searchForm] = Form.useForm();
  const [searchImageBase64, setSearchImageBase64] = useState(null);
  const [searching, setSearching] = useState(false);
  const [matches, setMatches] = useState([]);

  const refresh = async () => {
    setLoading(true);
    try {
      const res = await listFaceProfiles();
      // Backend endpoints may return either:
      // 1) { code, message, data }
      // 2) raw array payload (FastAPI response_model list)
      if (Array.isArray(res)) {
        setProfiles(res);
      } else if (res?.code === 0) {
        setProfiles(Array.isArray(res.data) ? res.data : []);
      } else if (res?.success && Array.isArray(res.data)) {
        setProfiles(res.data);
      } else {
        message.error(res?.message || '加载人脸库失败');
      }
    } catch (e) {
      console.error(e);
      message.error('加载人脸库失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const profileColumns = useMemo(() => ([
    { title: '姓名', dataIndex: 'name', key: 'name' },
    { title: 'ID', dataIndex: 'id', key: 'id', ellipsis: true },
    {
      title: '操作',
      key: 'op',
      render: (_, record) => (
        <Button
          danger
          size="small"
          icon={<DeleteOutlined />}
          onClick={async () => {
            try {
              const res = await deleteFaceProfile(record.id);
              if (res?.code === 0 || res?.success) {
                message.success('已删除');
                refresh();
              } else {
                message.error(res?.message || '删除失败');
              }
            } catch (e) {
              console.error(e);
              message.error('删除失败');
            }
          }}
        >
          删除
        </Button>
      )
    }
  ]), []);

  const matchColumns = useMemo(() => ([
    { title: '姓名', dataIndex: 'name', key: 'name' },
    { title: '相似度', dataIndex: 'score', key: 'score' },
    { title: 'ID', dataIndex: 'id', key: 'id', ellipsis: true },
  ]), []);

  const enrollUploadProps = {
    maxCount: 1,
    beforeUpload: async (file) => {
      const base64 = await fileToBase64(file);
      setEnrollImageBase64(base64);
      return false;
    },
    onRemove: () => setEnrollImageBase64(null),
  };

  const searchUploadProps = {
    maxCount: 1,
    beforeUpload: async (file) => {
      const base64 = await fileToBase64(file);
      setSearchImageBase64(base64);
      return false;
    },
    onRemove: () => setSearchImageBase64(null),
  };

  const handleEnroll = async () => {
    try {
      const values = await enrollForm.validateFields();
      if (!enrollImageBase64) {
        message.error('请先上传图片');
        return;
      }
      const res = await enrollFace({ name: values.name, image_base64: enrollImageBase64 });
      if (res?.code === 0 || res?.success) {
        message.success('录入成功');
        setEnrollOpen(false);
        enrollForm.resetFields();
        setEnrollImageBase64(null);
        refresh();
      } else {
        message.error(res?.message || '录入失败');
      }
    } catch (e) {
      // validate fields error
    }
  };

  const handleSearch = async () => {
    try {
      const values = await searchForm.validateFields();
      if (!searchImageBase64) {
        message.error('请先上传图片');
        return;
      }
      setSearching(true);
      const res = await searchFaces({
        image_base64: searchImageBase64,
        top_k: values.top_k,
        accept_threshold: values.accept_threshold,
      });
      if (res?.code === 0) {
        setMatches(res.data?.matches || res.data || []);
      } else if (res?.success) {
        setMatches(res.matches || res.data?.matches || []);
      } else {
        message.error(res?.message || '检索失败');
      }
    } catch (e) {
      // ignore
    } finally {
      setSearching(false);
    }
  };

  return (
    <div style={{ padding: 16 }}>
      <Header title="人脸识别" />
      <AntCard>
        <Tabs
          items={[
            {
              key: 'library',
              label: '人脸库管理',
              children: (
                <>
                  <Space style={{ marginBottom: 12 }}>
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => setEnrollOpen(true)}>
                      录入人脸
                    </Button>
                    <Button icon={<UploadOutlined />} onClick={refresh} loading={loading}>
                      刷新
                    </Button>
                  </Space>
                  <Table
                    rowKey="id"
                    columns={profileColumns}
                    dataSource={profiles}
                    loading={loading}
                    pagination={false}
                    size="small"
                  />
                </>
              )
            },
            {
              key: 'search',
              label: '检索测试',
              children: (
                <>
                  <Form
                    form={searchForm}
                    layout="inline"
                    initialValues={{ top_k: 5, accept_threshold: 0.35 }}
                    style={{ marginBottom: 12 }}
                  >
                    <Form.Item name="top_k" label="TopK" rules={[{ required: true }]}>
                      <Input type="number" min={1} max={20} style={{ width: 120 }} />
                    </Form.Item>
                    <Form.Item name="accept_threshold" label="阈值" rules={[{ required: true }]}>
                      <Input type="number" min={-1} max={1} step="0.01" style={{ width: 160 }} />
                    </Form.Item>
                    <Form.Item>
                      <Upload {...searchUploadProps}>
                        <Button icon={<UploadOutlined />}>上传图片</Button>
                      </Upload>
                    </Form.Item>
                    <Form.Item>
                      <Button
                        type="primary"
                        icon={<SearchOutlined />}
                        onClick={handleSearch}
                        loading={searching}
                      >
                        检索
                      </Button>
                    </Form.Item>
                  </Form>

                  <Table
                    rowKey={(r) => `${r.id}-${r.score}`}
                    columns={matchColumns}
                    dataSource={matches}
                    pagination={false}
                    size="small"
                  />
                </>
              )
            }
          ]}
        />
      </AntCard>

      <Modal
        title="录入人脸"
        open={enrollOpen}
        onOk={handleEnroll}
        onCancel={() => {
          setEnrollOpen(false);
          enrollForm.resetFields();
          setEnrollImageBase64(null);
        }}
        okText="确认录入"
        cancelText="取消"
      >
        <Form form={enrollForm} layout="vertical">
          <Form.Item name="name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]}>
            <Input placeholder="例如：Alice" />
          </Form.Item>
          <Form.Item label="人脸图片">
            <Upload {...enrollUploadProps}>
              <Button icon={<UploadOutlined />}>上传图片</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default FaceLibrary;

