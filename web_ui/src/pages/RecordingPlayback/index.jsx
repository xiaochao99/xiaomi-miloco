import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Select,
  Button,
  message,
  Space,
  Popconfirm,
  DatePicker,
  Spin,
  Tooltip,
} from 'antd';
import { useTranslation } from 'react-i18next';
import {
  ReloadOutlined,
  ClearOutlined,
  DeleteOutlined,
  CalendarOutlined,
  DashboardOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  getCameraList,
  getRecordingSegments,
  getRecordingStorage,
  cleanupRecordingExpired,
  deleteRecordingSegment,
  deleteRecordingSegmentsBatch,
  getRecordingStatus,
} from '@/api';
import { Header } from '@/components';
import ProfessionalPlayer from './components/ProfessionalPlayer';
import SegmentScroller from './components/SegmentScroller';
import TimelineBar from './components/TimelineBar';
import CameraPanel from './components/CameraPanel';
import styles from './index.module.less';

const RecordingPlayback = () => {
  const { t } = useTranslation();

  const [cameras, setCameras] = useState([]);
  const [selectedCamera, setSelectedCamera] = useState(null);
  const [selectedDate, setSelectedDate] = useState(() => dayjs());
  const [loading, setLoading] = useState(false);
  const [segments, setSegments] = useState([]);
  const [allSegments, setAllSegments] = useState([]);
  const [storageStats, setStorageStats] = useState(null);
  const [total, setTotal] = useState(0);
  const [activeSegment, setActiveSegment] = useState(null);
  const [recordingStatuses, setRecordingStatuses] = useState({});
  const [cameraSegmentCounts, setCameraSegmentCounts] = useState({});
  const [modeFilter, setModeFilter] = useState(null);
  const [selectedSegmentIds, setSelectedSegmentIds] = useState(new Set());
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetchCameras();
    fetchStorageStats();
    fetchRecordingStatuses();
  }, []);

  useEffect(() => {
    if (selectedCamera) {
      fetchSegments();
      setSelectedSegmentIds(new Set());
    }
  }, [selectedCamera, selectedDate, modeFilter]);

  const fetchCameras = async () => {
    try {
      const res = await getCameraList();
      if (res && res.code === 0) {
        setCameras(res.data || []);
        if (res.data && res.data.length > 0) {
          setSelectedCamera(res.data[0].did);
        }
      }
    } catch (error) {
      console.error('Failed to fetch cameras:', error);
    }
  };

  const fetchSegments = async () => {
    setLoading(true);
    try {
      const dateStr = selectedDate.format('YYYY-MM-DD');
      const params = {
        camera_id: selectedCamera,
        start_time: `${dateStr}T00:00:00`,
        end_time: `${dateStr}T23:59:59`,
        page: 1,
        page_size: 100,
      };
      if (modeFilter) params.mode = modeFilter;

      const res = await getRecordingSegments(params);
      if (res && res.code === 0) {
        const segs = res.data?.segments || [];
        setSegments(segs);
        setTotal(res.data?.total || segs.length);
        setCameraSegmentCounts((prev) => ({ ...prev, [selectedCamera]: res.data?.total || segs.length }));
      } else {
        setSegments([]);
        setTotal(0);
      }
    } catch (error) {
      console.error('Failed to fetch segments:', error);
      message.error(t('recording.common.error'));
    } finally {
      setLoading(false);
    }
  };

  const fetchAllDaySegments = useCallback(async () => {
    if (!selectedCamera) return;
    try {
      const dateStr = selectedDate.format('YYYY-MM-DD');
      const res = await getRecordingSegments({
        camera_id: selectedCamera,
        start_time: `${dateStr}T00:00:00`,
        end_time: `${dateStr}T23:59:59`,
        page: 1,
        page_size: 100,
      });
      if (res && res.code === 0) {
        setAllSegments(res.data?.segments || []);
      }
    } catch (error) {
      console.error('Failed to fetch all segments:', error);
    }
  }, [selectedCamera, selectedDate]);

  useEffect(() => {
    fetchAllDaySegments();
  }, [fetchAllDaySegments]);

  const fetchStorageStats = async () => {
    try {
      const res = await getRecordingStorage();
      if (res && res.code === 0) {
        setStorageStats(res.data);
      }
    } catch (error) {
      console.error('Failed to fetch storage stats:', error);
    }
  };

  const fetchRecordingStatuses = async () => {
    try {
      const res = await getRecordingStatus();
      if (res && res.code === 0 && res.data) {
        const statusMap = {};
        (Array.isArray(res.data) ? res.data : []).forEach((s) => {
          statusMap[s.camera_id] = s;
        });
        setRecordingStatuses(statusMap);
      }
    } catch (error) {
      console.error('Failed to fetch recording statuses:', error);
    }
  };

  const handleDeleteSegment = async (segmentId) => {
    try {
      const res = await deleteRecordingSegment(segmentId);
      if (res && res.code === 0) {
        message.success(t('recording.playback.deleted'));
        if (activeSegment?.id === segmentId) {
          setActiveSegment(null);
        }
        fetchSegments();
        fetchAllDaySegments();
        fetchStorageStats();
      } else {
        message.error(t('recording.playback.deleteFailed'));
      }
    } catch (error) {
      console.error('Failed to delete segment:', error);
      message.error(t('recording.playback.deleteFailed'));
    }
  };

  const handleBatchDelete = async () => {
    if (selectedSegmentIds.size === 0) return;
    setDeleting(true);
    try {
      const ids = Array.from(selectedSegmentIds);
      const res = await deleteRecordingSegmentsBatch(ids);
      if (res && res.code === 0) {
        message.success(t('recording.playback.batchDeleted', { count: ids.length }));
        setSelectedSegmentIds(new Set());
        if (ids.includes(activeSegment?.id)) {
          setActiveSegment(null);
        }
        fetchSegments();
        fetchAllDaySegments();
        fetchStorageStats();
      } else {
        message.error(t('recording.playback.deleteFailed'));
      }
    } catch (error) {
      console.error('Failed to batch delete:', error);
      message.error(t('recording.playback.deleteFailed'));
    } finally {
      setDeleting(false);
    }
  };

  const handleToggleSelectSegment = useCallback((segmentId) => {
    setSelectedSegmentIds((prev) => {
      const next = new Set(prev);
      if (next.has(segmentId)) {
        next.delete(segmentId);
      } else {
        next.add(segmentId);
      }
      return next;
    });
  }, []);

  const handleSelectAllSegments = useCallback(() => {
    if (selectedSegmentIds.size === segments.length) {
      setSelectedSegmentIds(new Set());
    } else {
      setSelectedSegmentIds(new Set(segments.map((s) => s.id)));
    }
  }, [segments, selectedSegmentIds.size]);

  const handleCleanup = async () => {
    setLoading(true);
    try {
      const res = await cleanupRecordingExpired();
      if (res && res.code === 0) {
        message.success(t('recording.playback.cleanupSuccess'));
        fetchSegments();
        fetchAllDaySegments();
        fetchStorageStats();
      } else {
        message.error(t('recording.playback.cleanupFailed'));
      }
    } catch (error) {
      console.error('Failed to cleanup:', error);
      message.error(t('recording.playback.cleanupFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleCameraChange = (cameraId) => {
    setSelectedCamera(cameraId);
    setActiveSegment(null);
  };

  const handleSegmentClick = useCallback((segment) => {
    setActiveSegment(segment);
  }, []);

  const handlePlayNext = useCallback(() => {
    const idx = segments.findIndex((s) => s.id === activeSegment?.id);
    if (idx >= 0 && idx < segments.length - 1) {
      setActiveSegment(segments[idx + 1]);
    }
  }, [segments, activeSegment]);

  const handlePlayPrev = useCallback(() => {
    const idx = segments.findIndex((s) => s.id === activeSegment?.id);
    if (idx > 0) {
      setActiveSegment(segments[idx - 1]);
    }
  }, [segments, activeSegment]);

  const formatFileSize = (bytes) => {
    if (!bytes) return '0 B';
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`;
  };

  const currentCameraName = useMemo(() => {
    const cam = cameras.find((c) => c.did === selectedCamera);
    return cam ? cam.name : '';
  }, [cameras, selectedCamera]);

  const activeSegmentIndex = useMemo(() => {
    return segments.findIndex((s) => s.id === activeSegment?.id);
  }, [segments, activeSegment]);

  return (
    <div className={styles.playbackContainer}>
      <div className={styles.playbackContent}>
        <Header
          title={t('recording.playback.title')}
          rightContent={
            <Space>
              <Popconfirm
                title={t('recording.playback.confirmCleanup')}
                onConfirm={handleCleanup}
                okText={t('common.confirm')}
                cancelText={t('common.cancel')}
              >
                <Button
                  icon={<ClearOutlined />}
                  loading={loading}
                >
                  {t('recording.playback.cleanup')}
                </Button>
              </Popconfirm>
            </Space>
          }
        />

        <div className={styles.mainLayout}>
          <div className={styles.leftPanel}>
            <CameraPanel
              cameras={cameras}
              selectedCameraId={selectedCamera}
              recordingStatuses={recordingStatuses}
              segmentCounts={cameraSegmentCounts}
              onCameraSelect={handleCameraChange}
            />

            {storageStats && (
              <div className={styles.storageCard}>
                <div className={styles.storageHeader}>
                  <DashboardOutlined />
                  <span>{t('recording.playback.storageStats')}</span>
                </div>
                <div className={styles.storageContent}>
                  <div className={styles.storageItem}>
                    <span className={styles.storageLabel}>{t('recording.config.usedSpace')}</span>
                    <span className={styles.storageValue}>{formatFileSize(storageStats.total_size_bytes || 0)}</span>
                  </div>
                  <div className={styles.storageItem}>
                    <span className={styles.storageLabel}>{t('recording.config.segmentCount')}</span>
                    <span className={styles.storageValue}>{storageStats.total_segments || 0}</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className={styles.centerPanel}>
            <div className={styles.toolbar}>
              <div className={styles.toolbarLeft}>
                <Space size={8}>
                  <CalendarOutlined className={styles.toolIcon} />
                  <DatePicker
                    value={selectedDate}
                    onChange={(date) => {
                      if (date) {
                        setSelectedDate(date);
                        setActiveSegment(null);
                      }
                    }}
                    allowClear={false}
                    className={styles.datePicker}
                  />

                  <Select
                    value={modeFilter}
                    onChange={(val) => {
                      setModeFilter(val);
                    }}
                    allowClear
                    placeholder={t('recording.playback.allModes')}
                    className={styles.modeFilter}
                    size="middle"
                  >
                    <Select.Option value="continuous">{t('recording.playback.triggerContinuous')}</Select.Option>
                    <Select.Option value="person">{t('recording.playback.triggerPerson')}</Select.Option>
                    <Select.Option value="motion">{t('recording.playback.triggerMotion')}</Select.Option>
                  </Select>

                  <Tooltip title={t('common.refresh')}>
                    <Button
                      icon={<ReloadOutlined />}
                      onClick={() => {
                        fetchSegments();
                        fetchAllDaySegments();
                        fetchStorageStats();
                      }}
                      loading={loading}
                    />
                  </Tooltip>
                </Space>
              </div>

              <div className={styles.toolbarRight}>
                <span className={styles.segmentCount}>
                  {t('recording.playback.totalSegments')}: {total}
                </span>
                {selectedSegmentIds.size > 0 && (
                  <Popconfirm
                    title={t('recording.playback.batchDeleteConfirm', { count: selectedSegmentIds.size })}
                    onConfirm={handleBatchDelete}
                    okText={t('common.confirm')}
                    cancelText={t('common.cancel')}
                  >
                    <Button
                      danger
                      size="small"
                      icon={<DeleteOutlined />}
                      loading={deleting}
                    >
                      {t('recording.playback.batchDelete')} ({selectedSegmentIds.size})
                    </Button>
                  </Popconfirm>
                )}
              </div>
            </div>

            <div className={styles.playerArea}>
              <Spin spinning={loading && !activeSegment}>
                <ProfessionalPlayer
                  segment={activeSegment}
                  cameraName={currentCameraName}
                  autoPlay={true}
                  onPlayNext={handlePlayNext}
                  onPlayPrev={handlePlayPrev}
                  hasNext={activeSegmentIndex < segments.length - 1}
                  hasPrev={activeSegmentIndex > 0}
                />
              </Spin>
            </div>

            {/* 时间轴 - 放在播放器下方、片段上方 */}
            <div className={styles.timelineArea}>
              <TimelineBar
                segments={allSegments}
                selectedDate={selectedDate.format('YYYY-MM-DD')}
                activeSegmentId={activeSegment?.id}
                onSegmentClick={handleSegmentClick}
              />
            </div>

            <div className={styles.contentArea}>
              <Spin spinning={loading}>
                <SegmentScroller
                  segments={segments}
                  activeSegmentId={activeSegment?.id}
                  selectedSegmentIds={selectedSegmentIds}
                  onSegmentClick={handleSegmentClick}
                  onToggleSelect={handleToggleSelectSegment}
                  onSelectAll={handleSelectAllSegments}
                  onDeleteSingle={handleDeleteSegment}
                />
              </Spin>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

function formatDuration(seconds) {
  if (!seconds) return '0s';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export default RecordingPlayback;
