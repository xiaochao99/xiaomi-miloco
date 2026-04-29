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
  Radio,
  Divider,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  SearchOutlined,
  ReloadOutlined,
  EditOutlined,
  BarChartOutlined,
  MessageOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { addMemory, searchMemory, listMemories, updateMemory, deleteMemory, getMemoryStats, handleMemoryCommand, getMemoryTypes } from '@/api';
import styles from './index.module.less';

const MEMORY_TYPES = [
  { value: 'preference', color: 'green', labelKey: 'memory.types.preference' },
  { value: 'fact', color: 'blue', labelKey: 'memory.types.fact' },
  { value: 'habit', color: 'orange', labelKey: 'memory.types.habit' },
  { value: 'device_setting', color: 'purple', labelKey: 'memory.types.device_setting' },
  { value: 'schedule', color: 'cyan', labelKey: 'memory.types.schedule' },
  { value: 'relationship', color: 'magenta', labelKey: 'memory.types.relationship' },
  { value: 'conversation', color: 'default', labelKey: 'memory.types.conversation' },
  { value: 'user_preference', color: 'green', labelKey: 'memory.types.user_preference' },
  { value: 'object_location', color: 'gold', labelKey: 'memory.types.object_location' },
  { value: 'pet_behavior', color: 'pink', labelKey: 'memory.types.pet_behavior' },
  { value: 'personal', color: 'red', labelKey: 'memory.types.personal' },
  { value: 'custom', color: 'gray', labelKey: 'memory.types.custom' },
];

const SOURCE_LABELS = {
  auto: 'memory.sourceAuto',
  manual: 'memory.sourceManual',
};

export default function MemoryManage() {
  const { t } = useTranslation();
  const [memories, setMemories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState(null);
  const [addModalVisible, setAddModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [searchModalVisible, setSearchModalVisible] = useState(false);
  const [commandModalVisible, setCommandModalVisible] = useState(false);
  const [currentMemory, setCurrentMemory] = useState(null);
  const [searchResults, setSearchResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });
  const [filterType, setFilterType] = useState('');
  const [filterSource, setFilterSource] = useState('');
  const [addForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [searchForm] = Form.useForm();
  const [commandForm] = Form.useForm();

  const fetchMemories = useCallback(async (page = 1, pageSize = 10) => {
    setLoading(true);
    try {
      const res = await listMemories({ page, page_size: pageSize });
      if (res && res.success !== false) {
        const data = res.data || res;
        const allMemories = data.memories || [];
        let filteredMemories = allMemories;
        
        if (filterType) {
          filteredMemories = filteredMemories.filter(m => m.memory_type === filterType);
        }
        if (filterSource) {
          filteredMemories = filteredMemories.filter(m => m.source === filterSource);
        }
        
        setMemories(filteredMemories);
        setPagination((prev) => ({
          ...prev,
          current: page,
          pageSize,
          total: filteredMemories.length,
        }));
      }
    } catch (error) {
      console.error('获取记忆列表失败:', error);
      message.error(t('memory.fetchFailed'));
    } finally {
      setLoading(false);
    }
  }, [filterType, filterSource]);

  const fetchStats = useCallback(async () => {
    try {
      const res = await getMemoryStats();
      if (res && res.success !== false) {
        const data = res.data || res;
        setStats(data.stats || data);
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
      });
      if (res && res.success !== false) {
        message.success(t('memory.addSuccess'));
        setAddModalVisible(false);
        addForm.resetFields();
        fetchMemories();
        fetchStats();
      } else {
        message.error(t('memory.addFailed'));
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
      });
      if (res && res.success !== false) {
        message.success(t('memory.editSuccess'));
        setEditModalVisible(false);
        setCurrentMemory(null);
        editForm.resetFields();
        fetchMemories();
        fetchStats();
      } else {
        message.error(t('memory.editFailed'));
      }
    } catch (error) {
      message.error(t('memory.editFailed'));
    }
  };

  const handleDelete = async (memoryId) => {
    try {
      const res = await deleteMemory(memoryId);
      if (res && res.success !== false) {
        message.success(t('memory.deleteSuccess'));
        fetchMemories();
        fetchStats();
      } else {
        message.error(t('memory.deleteFailed'));
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
      });
      if (res && res.success !== false) {
        const data = res.data || res;
        setSearchResults(data || []);
      }
    } catch (error) {
      message.error(t('memory.searchFailed'));
    } finally {
      setSearchLoading(false);
    }
  };

  const handleCommand = async (values) => {
    try {
      const res = await handleMemoryCommand({
        command: values.command,
      });
      if (res && res.success !== false) {
        const data = res.data || res;
        if (data.success) {
          message.success(data.message || t('memory.commandSuccess'));
          fetchMemories();
          fetchStats();
        } else {
          message.warning(data.message || t('memory.commandFailed'));
        }
      }
    } catch (error) {
      message.error(t('memory.commandFailed'));
    } finally {
      setCommandModalVisible(false);
      commandForm.resetFields();
    }
  };

  const openEditModal = (record) => {
    setCurrentMemory(record);
    editForm.setFieldsValue({
      content: record.content,
      memory_type: record.memory_type,
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
        {t(typeConfig?.labelKey || `memory.types.${type}`)}
      </Tag>
    );
  };

  const getSourceTag = (source) => {
    const color = source === 'auto' ? 'green' : 'blue';
    return (
      <Tag color={color}>
        {t(SOURCE_LABELS[source] || `memory.sourceAuto`)}
      </Tag>
    );
  };

  const getStatusTag = (isActive) => {
    if (isActive === undefined) return null;
    const color = isActive ? 'green' : 'red';
    return (
      <Tag color={color}>
        {isActive ? t('memory.statusActive') : t('memory.statusInactive')}
      </Tag>
    );
  };

  const columns = [
    {
      title: t('memory.content'),
      dataIndex: 'content',
      key: 'content',
      ellipsis: true,
      width: '35%',
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
      title: t('memory.source'),
      dataIndex: 'source',
      key: 'source',
      width: 100,
      render: (source) => getSourceTag(source),
    },
    {
      title: t('memory.status'),
      dataIndex: 'is_active',
      key: 'is_active',
      width: 100,
      render: (isActive) => getStatusTag(isActive),
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
      width: '50%',
      render: (text, record) => (
        <Tooltip title={text}>
          <span onClick={() => openDetailModal(record.memory)} className={styles.contentCell}>
            {text}
          </span>
        </Tooltip>
      ),
    },
    {
      title: t('memory.type'),
      dataIndex: ['memory', 'memory_type'],
      key: 'memory_type',
      width: 120,
      render: (type) => getMemoryTypeTag(type),
    },
    {
      title: t('memory.relevance'),
      dataIndex: 'score',
      key: 'score',
      width: 100,
      render: (score) => (
        <span>
          {score != null ? (score * 100).toFixed(1) + '%' : '-'}
        </span>
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
                width: 500,
                content: stats ? (
                  <div>
                    <Descriptions column={2} bordered size="small" style={{ marginBottom: 16 }}>
                      <Descriptions.Item label={t('memory.totalCount')}>
                        {stats.total_count}
                      </Descriptions.Item>
                      <Descriptions.Item label={t('memory.activeCount')}>
                        {stats.active_count || '-'}
                      </Descriptions.Item>
                      <Descriptions.Item label={t('memory.avgImportance')} span={2}>
                        {stats.avg_importance != null
                          ? `${Math.round(stats.avg_importance * 100)}%`
                          : '-'}
                      </Descriptions.Item>
                    </Descriptions>
                    <Divider style={{ margin: '12px 0' }} />
                    <div>
                      <Typography.Text strong>{t('memory.typeDistribution')}</Typography.Text>
                      <div className={styles.typeDistribution}>
                        {stats.by_type &&
                          Object.entries(stats.by_type).map(([type, count]) => (
                            <div key={type} className={styles.typeItem}>
                              {getMemoryTypeTag(type)}: {count}
                            </div>
                          ))}
                      </div>
                    </div>
                    {stats.by_source && (
                      <>
                        <Divider style={{ margin: '12px 0' }} />
                        <div>
                          <Typography.Text strong>{t('memory.sourceDistribution')}</Typography.Text>
                          <div className={styles.sourceDistribution}>
                            {Object.entries(stats.by_source).map(([source, count]) => (
                              <div key={source} className={styles.sourceItem}>
                                {getSourceTag(source)}: {count}
                              </div>
                            ))}
                          </div>
                        </div>
                      </>
                    )}
                  </div>
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
            icon={<MessageOutlined />}
            onClick={() => setCommandModalVisible(true)}
          >
            {t('memory.command')}
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

      <div className={styles.filterBar}>
        <Select
          placeholder={t('memory.filterType')}
          style={{ width: 150 }}
          allowClear
          value={filterType}
          onChange={(value) => {
            setFilterType(value);
            setPagination({ ...pagination, current: 1 });
          }}
        >
          {MEMORY_TYPES.map((type) => (
            <Select.Option key={type.value} value={type.value}>
              {t(type.labelKey)}
            </Select.Option>
          ))}
        </Select>
        <Select
          placeholder={t('memory.filterSource')}
          style={{ width: 120 }}
          allowClear
          value={filterSource}
          onChange={(value) => {
            setFilterSource(value);
            setPagination({ ...pagination, current: 1 });
          }}
        >
          <Select.Option value="auto">{t('memory.sourceAuto')}</Select.Option>
          <Select.Option value="manual">{t('memory.sourceManual')}</Select.Option>
        </Select>
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
            initialValue="preference"
          >
            <Select>
              {MEMORY_TYPES.map((type) => (
                <Select.Option key={type.value} value={type.value}>
                  {t(type.labelKey)}
                </Select.Option>
              ))}
            </Select>
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
            <Descriptions.Item label={t('memory.source')}>
              {getSourceTag(currentMemory.source)}
            </Descriptions.Item>
            <Descriptions.Item label={t('memory.status')}>
              {getStatusTag(currentMemory.is_active)}
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

      <Modal
        title={t('memory.commandTitle')}
        open={commandModalVisible}
        onCancel={() => {
          setCommandModalVisible(false);
          commandForm.resetFields();
        }}
        footer={null}
        width={600}
      >
        <div className={styles.commandTip}>
          <InfoCircleOutlined style={{ marginRight: 8, color: '#1890ff' }} />
          <Typography.Text type="secondary">
            {t('memory.commandTip')}
          </Typography.Text>
        </div>
        <div className={styles.commandExamples}>
          <Typography.Text strong>{t('memory.commandExamples')}</Typography.Text>
          <ul>
            <li>{t('memory.exampleAdd')}</li>
            <li>{t('memory.exampleUpdate')}</li>
            <li>{t('memory.exampleDelete')}</li>
            <li>{t('memory.exampleQuery')}</li>
          </ul>
        </div>
        <Form form={commandForm} layout="vertical" onFinish={handleCommand}>
          <Form.Item
            name="command"
            rules={[{ required: true, message: t('memory.pleaseEnterCommand') }]}
          >
            <Input.TextArea rows={3} placeholder={t('memory.commandPlaceholder')} />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                {t('common.confirm')}
              </Button>
              <Button
                onClick={() => {
                  setCommandModalVisible(false);
                  commandForm.resetFields();
                }}
              >
                {t('common.cancel')}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}