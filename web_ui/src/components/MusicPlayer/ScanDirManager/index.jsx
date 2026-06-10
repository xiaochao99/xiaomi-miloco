import React, { useState, useEffect } from 'react'
import { List, Button, Input, Switch, Modal, message, Empty, Tag, Space, Popconfirm, Typography } from 'antd'
import {
  FolderOutlined, PlusOutlined, DeleteOutlined,
  EditOutlined, ReloadOutlined, ScanOutlined,
  FolderOpenOutlined
} from '@ant-design/icons'
import { useMusicPlayerStore } from '@/stores/musicPlayerStore'
import styles from './index.module.less'

const { Text } = Typography

const ScanDirManager = () => {
  const {
    scanDirs, scanDirsLoading,
    loadScanDirs, addScanDir, removeScanDir, updateScanDir,
    watcherStatus, loadWatcherStatus,
    startWatcher, stopWatcher, watcherLoading,
    scanLocalMusicPath, isScanning,
  } = useMusicPlayerStore()

  const [showAddModal, setShowAddModal] = useState(false)
  const [editingDir, setEditingDir] = useState(null)
  const [newDirPath, setNewDirPath] = useState('')
  const [newDirRecursive, setNewDirRecursive] = useState(true)
  const [newDirName, setNewDirName] = useState('')

  useEffect(() => {
    loadScanDirs()
    loadWatcherStatus()
  }, [loadScanDirs, loadWatcherStatus])

  const handleAddDir = async () => {
    if (!newDirPath.trim()) {
      message.warning('请输入目录路径')
      return
    }
    const result = await addScanDir({
      path: newDirPath.trim(),
      name: newDirName.trim() || newDirPath.trim().split(/[/\\]/).pop() || '未命名目录',
      recursive: newDirRecursive,
    })
    if (result.success) {
      setShowAddModal(false)
      setNewDirPath('')
      setNewDirName('')
      setNewDirRecursive(true)
    } else {
      message.error(result.error || '添加失败')
    }
  }

  const handleRemoveDir = async (dirId) => {
    const result = await removeScanDir(dirId)
    if (!result.success) {message.error(result.error || '删除失败')}
  }

  const handleUpdateDir = async (dirId, updates) => {
    const result = await updateScanDir(dirId, updates)
    if (result.success) {
      setEditingDir(null)
    } else {
      message.error(result.error || '更新失败')
    }
  }

  const handleScanDir = async (dir) => {
    const result = await scanLocalMusicPath(dir.path, dir.recursive)
    if (result.success) {
      message.success(`扫描完成，发现 ${result.total} 首，新增 ${result.newSongs} 首`)
    } else {
      message.error(result.error || '扫描失败')
    }
  }

  const handleToggleWatcher = async () => {
    if (watcherStatus?.is_running) {
      const result = await stopWatcher()
      if (!result.success) {message.error(result.error || '停止失败')}
    } else {
      const result = await startWatcher()
      if (!result.success) {message.error(result.error || '启动失败')}
    }
  }

  return (
    <div className={styles.manager}>
      <div className={styles.watcherBar}>
        <div className={styles.watcherInfo}>
          <span className={styles.watcherDot} style={{
            background: watcherStatus?.is_running ? '#52c41a' : '#8c8c8c',
          }} />
          <span className={styles.watcherLabel}>
            文件监控
          </span>
          <Tag color={watcherStatus?.is_running ? 'success' : 'default'} className={styles.watcherTag}>
            {watcherStatus?.is_running ? '运行中' : '已停止'}
          </Tag>
        </div>
        <Button
          size="small"
          onClick={handleToggleWatcher}
          loading={watcherLoading}
          className={styles.watcherBtn}
          type={watcherStatus?.is_running ? 'default' : 'primary'}
          style={!watcherStatus?.is_running ? { background: '#00bdc3', borderColor: '#00bdc3' } : {}}
        >
          {watcherStatus?.is_running ? '停止' : '启动'}
        </Button>
      </div>

      <div className={styles.actions}>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setShowAddModal(true)}
          size="small"
          className={styles.addBtn}
          style={{ background: '#ec4141', borderColor: '#ec4141' }}
        >
          添加目录
        </Button>
        <Button
          icon={<ReloadOutlined />}
          onClick={loadScanDirs}
          loading={scanDirsLoading}
          size="small"
          className={styles.refreshBtn}
        >
          刷新
        </Button>
      </div>

      {scanDirs.length > 0 ? (
        <List
          className={styles.dirList}
          dataSource={scanDirs}
          renderItem={(dir) => (
            <List.Item
              className={styles.dirItem}
              actions={[
                <Button
                  type="text"
                  icon={<ScanOutlined />}
                  onClick={() => handleScanDir(dir)}
                  loading={isScanning}
                  size="small"
                  className={styles.actionBtn}
                />,
                <Button
                  type="text"
                  icon={<EditOutlined />}
                  onClick={() => setEditingDir(dir)}
                  size="small"
                  className={styles.actionBtn}
                />,
                <Popconfirm
                  title="确认删除此扫描目录？"
                  onConfirm={() => handleRemoveDir(dir.id)}
                  okText="确认"
                  cancelText="取消"
                >
                  <Button
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    size="small"
                    className={styles.actionBtn}
                  />
                </Popconfirm>
              ]}
            >
              <List.Item.Meta
                avatar={<FolderOpenOutlined className={styles.dirIcon} />}
                title={
                  <div className={styles.dirTitle}>
                    <span>{dir.name || dir.path}</span>
                    {dir.recursive && <Tag color="cyan" className={styles.recursiveTag}>递归</Tag>}
                  </div>
                }
                description={
                  <div className={styles.dirPath}>
                    {dir.path}
                    {dir.last_scan && (
                      <span className={styles.lastScan}>
                        上次扫描: {new Date(dir.last_scan).toLocaleString()}
                      </span>
                    )}
                  </div>
                }
              />
            </List.Item>
          )}
        />
      ) : (
        <Empty
          description="暂无扫描目录"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          className={styles.empty}
        >
          <Button
            type="primary"
            onClick={() => setShowAddModal(true)}
            style={{ background: '#ec4141', borderColor: '#ec4141' }}
          >
            添加第一个扫描目录
          </Button>
        </Empty>
      )}

      <Modal
        title="添加扫描目录"
        open={showAddModal}
        onOk={handleAddDir}
        onCancel={() => {
          setShowAddModal(false)
          setNewDirPath('')
          setNewDirName('')
          setNewDirRecursive(true)
        }}
        okText="添加"
        cancelText="取消"
        className={styles.modal}
      >
        <div className={styles.form}>
          <div className={styles.formItem}>
            <label>目录名称</label>
            <Input
              placeholder="可选，默认使用目录名"
              value={newDirName}
              onChange={(e) => setNewDirName(e.target.value)}
            />
          </div>
          <div className={styles.formItem}>
            <label>目录路径</label>
            <Input
              placeholder="绝对路径，如 /home/user/Music"
              value={newDirPath}
              onChange={(e) => setNewDirPath(e.target.value)}
            />
          </div>
          <div className={styles.formItem}>
            <label>递归扫描</label>
            <Switch
              checked={newDirRecursive}
              onChange={setNewDirRecursive}
              checkedChildren="是"
              unCheckedChildren="否"
            />
          </div>
        </div>
      </Modal>

      <Modal
        title="编辑扫描目录"
        open={!!editingDir}
        onOk={() => {
          if (editingDir) {
            handleUpdateDir(editingDir.id, {
              name: editingDir.name,
              recursive: editingDir.recursive,
            })
          }
        }}
        onCancel={() => setEditingDir(null)}
        okText="保存"
        cancelText="取消"
        className={styles.modal}
      >
        {editingDir && (
          <div className={styles.form}>
            <div className={styles.formItem}>
              <label>目录名称</label>
              <Input
                value={editingDir.name}
                onChange={(e) => setEditingDir({ ...editingDir, name: e.target.value })}
              />
            </div>
            <div className={styles.formItem}>
              <label>目录路径</label>
              <Input value={editingDir.path} disabled />
            </div>
            <div className={styles.formItem}>
              <label>递归扫描</label>
              <Switch
                checked={editingDir.recursive}
                onChange={(checked) => setEditingDir({ ...editingDir, recursive: checked })}
                checkedChildren="是"
                unCheckedChildren="否"
              />
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}

export default ScanDirManager
