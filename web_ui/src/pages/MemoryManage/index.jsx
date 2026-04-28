/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Slider,
  Tag,
  Space,
  message,
  Popconfirm,
  Typography,
  Tooltip,
  Empty,
  InputNumber,
  Descriptions,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  SearchOutlined,
  ReloadOutlined,
  EditOutlined,
  BarChartOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { addMemory, searchMemory, listMemories, updateMemory, deleteMemory, getMemoryStats } from '@/api';
import styles from './index.module.less';

const MEMORY_TYPES = [
  { value: 'conversation', color: 'blue', labelKey: 'memory.type.conversation' },
  { value: 'user_preference', color: 'green', labelKey: 'memory.type.user_preference' },
  { value: 'object_location', color: 'orange', labelKey: 'memory.type.object_location' },
  { value: 'pet_behavior', color: 'purple', labelKey: 'memory.type.pet_behavior' },
  { value: 'schedule', color: 'cyan', labelKey: 'memory.type.schedule' },
  { value: 'personal', color: 'magenta', labelKey: 'memory.type.personal' },
  { value: 'custom', color: 'default', labelKey: 'memory.type.custom' },
];

export default function MemoryManage() {
  const { t } = useTranslation();
  const [memories, setMemories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState(null);
  const [addModalVisible, setAddModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [searchModalVisible, setSearchModalVisible] = useState(false);
  const [currentMemory, setCurrentMemory] = useState(null);
  const [searchResults, setSearchResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });
  const [addForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [searchForm] = Form.useForm();

  const fetchMemories = useCallback(async (page = 1, pageSize = 10) => {
    setLoading(true);
    try {
      const res = await listMemories({ limit: 1000 });
      if (res.success) {
        const allMemories = res.memories || [];
        setMemories(allMemories);
        setPagination((prev) => ({
          ...prev,
          current: page,
          pageSize,
          total: allMemories.length,
        }));
      }
    } catch (error) {
      console.error('获取记忆列表失败:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const res = await getMemoryStats();
      if (res.success) {
        setStats(res.stats);
      }
    } catch (error) {
      console.error('获取统计信息失败:', error);
    }
  }, []);

  useEffect(() => {
    fetchMemories();
    fetchStats();
  }, [fetchMemories, fetchStats]);

  const handleAdd = async (values) => {
    try {
      const res = await addMemory({
        content: values.content,
        memory_type: values.memory_type,
        importance: values.importance / 100,
      });
      if (res.success) {
        message.success(t('memory.addSuccess'));
        setAddModalVisible(false);
        addForm.resetFields();
        fetchMemories();
        fetchStats();
      }
    } catch (error) {
      message.error(t('memory.addFailed'));
    }
  };

  const handleEdit = async (values) => {
    if (!currentMemory) return;
    try {
      const res = await updateMemory(currentMemory.id, {
        content: values.content,
        memory_type: values.memory_type,
        importance: values.importance / 100,
      });
      if (res.success) {
        message.success(t('memory.editSuccess'));
        setEditModalVisible(false);
        setCurrentMemory(null);
        editForm.resetFields();
        fetchMemories();
        fetchStats();
      }
    } catch (error) {
      message.error(t('memory.editFailed'));
    }
  };

  const handleDelete = async (memoryId) => {
    try {
      const res = await deleteMemory(memoryId);
      if (res.success) {
        message.success(t('memory.deleteSuccess'));
        fetchMemories();
        fetchStats();
      }
    } catch (error) {
      message.error(t('memory.deleteFailed'));
    }
  };

  const handleSearch = async (values) => {
    setSearchLoading(true);
    try {
      const res = await searchMemory({
        query: values.query,
        limit: values.limit || 10,
        memory_type: values.memory_type || undefined,
      });
      if (res.success) {
        setSearchResults(res.results || []);
      }
    } catch (error) {
      message.error(t('memory.searchFailed'));
    } finally {
      setSearchLoading(false);
    }
  };

  const openEditModal = (record) => {
    setCurrentMemory(record);
    editForm.setFieldsValue({
      content: record.content,
      memory_type: record.memory_type,
      importance: Math.round((record.importance || 0.5) * 100),
    });
    setEditModalVisible(true);
  };

  const openDetailModal = (record) => {
    setCurrentMemory(record);
    setDetailModalVisible(true);
  };

  const getMemoryTypeTag = (type) => {
    const typeConfig = MEMORY_TYPES.find((mt) => mt.value === type);
    return (
      <Tag color={typeConfig?.color || 'default'}>
        {t(typeConfig?.labelKey || `memory.type.${type}`)}
      </Tag>
    );
  };

  const getImportanceColor = (importance) => {
    if (importance >= 0.7) return '#f5222d';
    if (importance >= 0.4) return '#faad14';
    return '#52c41a';
  };

  const columns = [
    {
      title: t('memory.content'),
      dataIndex: 'content',
      key: 'content',
      ellipsis: true,
      width: '40%',
      render: (text, record) => (
        <Tooltip title={text}>
          <span
            className={styles.contentCell}
            onClick={() => openDetailModal(record)}
          >
            {text}
          </span>
        </Tooltip>
      ),
    },
    {
      title: t('memory.type'),
      dataIndex: 'memory_type',
      key: 'memory_type',
      width: 120,
      render: (type) => getMemoryTypeTag(type),
    },
    {
      title: t('memory.importance'),
      dataIndex: 'importance',
      key: 'importance',
      width: 120,
      sorter: (a, b) => (a.importance || 0) - (b.importance || 0),
      render: (importance) => (
        <span style={{ color: getImportanceColor(importance) }}>
          {importance != null ? `${Math.round(importance * 100)}%` : '-'}
        </span>
      ),
    },
    {
      title: t('memory.createdAt'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      sorter: (a, b) => new Date(a.created_at) - new Date(b.created_at),
      render: (text) => (text ? new Date(text).toLocaleString() : '-'),
    },
    {
      title: t('common.operation'),
      key: 'action',
      width: 150,
      render: (_, record) => (
        <Space size="small">
          <Tooltip title={t('common.edit')}>
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => openEditModal(record)}
            />
          </Tooltip>
          <Popconfirm
            title={t('common.confirmDelete')}
            onConfirm={() => handleDelete(record.id)}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
          >
            <Tooltip title={t('common.delete')}>
              <Button type="link" size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const searchResultColumns = [
    {
      title: t('memory.content'),
      dataIndex: ['memory', 'content'],
      key: 'content',
      ellipsis: true,
    },
    {
      title: t('memory.type'),
      dataIndex: ['memory', 'memory_type'],
      key: 'memory_type',
      width: 120,
      render: (type) => getMemoryTypeTag(type),
    },
    {
      title: t('memory.score'),
      dataIndex: 'score',
      key: 'score',
      width: 100,
      render: (score) => (
        <span>{score != null ? (score * 100).toFixed(1) + '%' : '-'}</span>
      ),
    },
  ];

  const paginatedData = memories.slice(
    (pagination.current - 1) * pagination.pageSize,
    pagination.current * pagination.pageSize,
  );

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            {t('memory.title')}
          </Typography.Title>
        </div>
        <Space>
          <Button
            icon={<BarChartOutlined />}
            onClick={() => {
              fetchStats();
              Modal.info({
                title: t('memory.statsTitle'),
                width: 400,
                content: stats ? (
                  <Descriptions column={1} bordered size="small">
                    <Descriptions.Item label={t('memory.totalCount')}>
                      {stats.total_count}
                    </Descriptions.Item>
                    <Descriptions.Item label={t('memory.avgImportance')}>
                      {stats.avg_importance != null
                        ? `${Math.round(stats.avg_importance * 100)}%`
                        : '-'}
                    </Descriptions.Item>
                    <Descriptions.Item label={t('memory.typeDistribution')}>
                      {stats.type_counts &&
                        Object.entries(stats.type_counts).map(([type, count]) => (
                          <div key={type}>
                            {getMemoryTypeTag(type)}: {count}
                          </div>
                        ))}
                    </Descriptions.Item>
                  </Descriptions>
                ) : (
                  <Empty description={t('memory.noStatsData')} />
                ),
              });
            }}
          >
            {t('memory.stats')}
          </Button>
          <Button
            icon={<SearchOutlined />}
            onClick={() => setSearchModalVisible(true)}
          >
            {t('memory.search')}
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              fetchMemories();
              fetchStats();
            }}
          >
            {t('common.refresh')}
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setAddModalVisible(true)}
          >
            {t('memory.addMemory')}
          </Button>
        </Space>
      </div>

      <Card className={styles.tableCard}>
        <Table
          columns={columns}
          dataSource={paginatedData}
          rowKey="id"
          loading={loading}
          pagination={{
            ...pagination,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => t('memory.total', { total }),
            onChange: (page, pageSize) => fetchMemories(page, pageSize),
          }}
          locale={{ emptyText: <Empty description={t('memory.noMemories')} /> }}
        />
      </Card>

      <Modal
        title={t('memory.addMemory')}
        open={addModalVisible}
        onCancel={() => {
          setAddModalVisible(false);
          addForm.resetFields();
        }}
        footer={null}
        width={600}
      >
        <Form form={addForm} layout="vertical" onFinish={handleAdd}>
          <Form.Item
            name="content"
            label={t('memory.content')}
            rules={[{ required: true, message: t('memory.pleaseEnterContent') }]}
          >
            <Input.TextArea rows={4} placeholder={t('memory.contentPlaceholder')} />
          </Form.Item>
          <Form.Item
            name="memory_type"
            label={t('memory.type')}
            initialValue="personal"
          >
            <Select>
              {MEMORY_TYPES.map((type) => (
                <Select.Option key={type.value} value={type.value}>
                  {t(type.labelKey)}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item
            name="importance"
            label={t('memory.importance')}
            initialValue={70}
          >
            <Slider min={0} max={100} marks={{ 0: '0', 50: '50', 100: '100' }} />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                {t('common.confirm')}
              </Button>
              <Button
                onClick={() => {
                  setAddModalVisible(false);
                  addForm.resetFields();
                }}
              >
                {t('common.cancel')}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t('memory.editMemory')}
        open={editModalVisible}
        onCancel={() => {
          setEditModalVisible(false);
          setCurrentMemory(null);
          editForm.resetFields();
        }}
        footer={null}
        width={600}
      >
        <Form form={editForm} layout="vertical" onFinish={handleEdit}>
          <Form.Item
            name="content"
            label={t('memory.content')}
            rules={[{ required: true, message: t('memory.pleaseEnterContent') }]}
          >
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="memory_type" label={t('memory.type')}>
            <Select>
              {MEMORY_TYPES.map((type) => (
                <Select.Option key={type.value} value={type.value}>
                  {t(type.labelKey)}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="importance" label={t('memory.importance')}>
            <Slider min={0} max={100} marks={{ 0: '0', 50: '50', 100: '100' }} />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                {t('common.confirm')}
              </Button>
              <Button
                onClick={() => {
                  setEditModalVisible(false);
                  setCurrentMemory(null);
                  editForm.resetFields();
                }}
              >
                {t('common.cancel')}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t('memory.memoryDetail')}
        open={detailModalVisible}
        onCancel={() => {
          setDetailModalVisible(false);
          setCurrentMemory(null);
        }}
        footer={null}
        width={600}
      >
        {currentMemory && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label={t('memory.id')}>
              {currentMemory.id}
            </Descriptions.Item>
            <Descriptions.Item label={t('memory.content')}>
              <div className={styles.detailContent}>{currentMemory.content}</div>
            </Descriptions.Item>
            <Descriptions.Item label={t('memory.type')}>
              {getMemoryTypeTag(currentMemory.memory_type)}
            </Descriptions.Item>
            <Descriptions.Item label={t('memory.importance')}>
              <span
                style={{ color: getImportanceColor(currentMemory.importance) }}
              >
                {currentMemory.importance != null
                  ? `${Math.round(currentMemory.importance * 100)}%`
                  : '-'}
              </span>
            </Descriptions.Item>
            <Descriptions.Item label={t('memory.createdAt')}>
              {currentMemory.created_at
                ? new Date(currentMemory.created_at).toLocaleString()
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label={t('memory.updatedAt')}>
              {currentMemory.updated_at
                ? new Date(currentMemory.updated_at).toLocaleString()
                : '-'}
            </Descriptions.Item>
            {currentMemory.session_id && (
              <Descriptions.Item label={t('memory.sessionId')}>
                {currentMemory.session_id}
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Modal>

      <Modal
        title={t('memory.searchMemory')}
        open={searchModalVisible}
        onCancel={() => {
          setSearchModalVisible(false);
          setSearchResults([]);
          searchForm.resetFields();
        }}
        footer={null}
        width={800}
      >
        <Form form={searchForm} layout="inline" onFinish={handleSearch} style={{ marginBottom: 16 }}>
          <Form.Item
            name="query"
            rules={[{ required: true, message: t('memory.pleaseEnterSearchQuery') }]}
          >
            <Input placeholder={t('memory.searchPlaceholder')} style={{ width: 300 }} />
          </Form.Item>
          <Form.Item name="memory_type">
            <Select allowClear placeholder={t('memory.type')} style={{ width: 150 }}>
              {MEMORY_TYPES.map((type) => (
                <Select.Option key={type.value} value={type.value}>
                  {t(type.labelKey)}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="limit" initialValue={10}>
            <InputNumber min={1} max={50} placeholder={t('memory.resultLimit')} style={{ width: 100 }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={searchLoading} icon={<SearchOutlined />}>
              {t('memory.search')}
            </Button>
          </Form.Item>
        </Form>
        <Table
          columns={searchResultColumns}
          dataSource={searchResults}
          rowKey={(r) => r.memory?.id || Math.random()}
          size="small"
          pagination={{ pageSize: 5 }}
          locale={{ emptyText: <Empty description={t('memory.noSearchResults')} /> }}
        />
      </Modal>
    </div>
  );
}
