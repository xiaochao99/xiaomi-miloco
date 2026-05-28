import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  Select,
  Button,
  message,
  Space,
  Popconfirm,
  DatePicker,
  Spin,
  Tooltip,
  Checkbox,
  Empty,
  Drawer,
} from 'antd';
import { useTranslation } from 'react-i18next';
import {
  ReloadOutlined,
  ClearOutlined,
  DeleteOutlined,
  CalendarOutlined,
  DashboardOutlined,
  VideoCameraOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  FullscreenOutlined,
  SoundOutlined,
  StepBackwardOutlined,
  StepForwardOutlined,
  UnorderedListOutlined,
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
  getRecordingPlaybackUrl,
  getRecordingThumbnailUrl,
  getRecordingHlsUrl,
} from '@/api';
import TimelineBar from './components/TimelineBar';
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

  // 播放器状态
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(0.8);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [zoomLevel, setZoomLevel] = useState(0);
  const [segmentDrawerVisible, setSegmentDrawerVisible] = useState(false);

  const videoRef = useRef(null);
  const hlsRef = useRef(null);

  // hls.js 播放器：TS 文件通过 m3u8 播放，其他格式原生播放
  useEffect(() => {
    if (!activeSegment) return;

    let cancelled = false;
    const video = videoRef.current;
    if (!video) return;

    // 清理上一次的 hls 实例
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }

    const playbackUrl = getRecordingPlaybackUrl(activeSegment.id);
    const isTs = (activeSegment.file_path || '').toLowerCase().endsWith('.ts');

    if (!isTs) {
      video.src = playbackUrl;
      if (isPlaying) video.play().catch(() => {});
      return () => { video.src = ''; };
    }

    // TS 文件：使用 hls.js
    const setupHls = async () => {
      try {
        const Hls = (await import('hls.js')).default;
        if (cancelled) return;

        const hls = new Hls({ enableWorker: false });
        hls.attachMedia(video);

        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          if (cancelled) return;
          setDuration(hls.levels?.[0]?.details?.totalduration || activeSegment.duration_seconds || 0);
          if (isPlaying) video.play().catch(() => {});
        });

        hls.on(Hls.Events.ERROR, (_event, data) => {
          if (cancelled || !data.fatal) return;
          console.warn('[HLS] Fatal error:', data.details);
          hls.destroy();
          hlsRef.current = null;
          // 回退到服务端转码
          video.src = `/api/recording/transcode/${activeSegment.id}`;
          video.play().catch(() => {});
        });

        hls.loadSource(getRecordingHlsUrl(activeSegment.id));
        hlsRef.current = hls;
      } catch (e) {
        console.error('[HLS] Init error:', e);
        if (!cancelled) {
          video.src = `/api/recording/transcode/${activeSegment.id}`;
          video.play().catch(() => {});
        }
      }
    };

    setupHls();

    return () => {
      cancelled = true;
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
    };
  }, [activeSegment?.id, isPlaying]);

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

  const handleToggleSelectSegment = useCallback((segmentId, checked) => {
    setSelectedSegmentIds((prev) => {
      const next = new Set(prev);
      if (checked) {
        next.add(segmentId);
      } else {
        next.delete(segmentId);
      }
      return next;
    });
  }, []);

  const handleSelectAllSegments = useCallback((checked) => {
    if (checked) {
      setSelectedSegmentIds(new Set(segments.map((s) => s.id)));
    } else {
      setSelectedSegmentIds(new Set());
    }
  }, [segments]);

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
    setIsPlaying(true);
    setCurrentTime(0);
  }, []);

  const handlePlayNext = useCallback(() => {
    const idx = segments.findIndex((s) => s.id === activeSegment?.id);
    if (idx >= 0 && idx < segments.length - 1) {
      setActiveSegment(segments[idx + 1]);
      setCurrentTime(0);
    }
  }, [segments, activeSegment]);

  const handlePlayPrev = useCallback(() => {
    const idx = segments.findIndex((s) => s.id === activeSegment?.id);
    if (idx > 0) {
      setActiveSegment(segments[idx - 1]);
      setCurrentTime(0);
    }
  }, [segments, activeSegment]);

  const handleTogglePlay = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
      video.play().catch(() => {});
      setIsPlaying(true);
    } else {
      video.pause();
      setIsPlaying(false);
    }
  }, []);

  const handleSpeedChange = useCallback(() => {
    const speeds = [0.5, 1, 1.5, 2, 4];
    const currentIndex = speeds.indexOf(playbackRate);
    const nextIndex = (currentIndex + 1) % speeds.length;
    setPlaybackRate(speeds[nextIndex]);
  }, [playbackRate]);

  const formatFileSize = (bytes) => {
    if (!bytes) return '0 B';
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`;
  };

  const formatDuration = (seconds) => {
    if (!seconds) return '0s';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}h ${m}m ${s}s`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  };

  const formatTime = (seconds) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const activeSegmentIndex = useMemo(() => {
    return segments.findIndex((s) => s.id === activeSegment?.id);
  }, [segments, activeSegment]);

  const getCameraStatus = useCallback((cameraId) => {
    const status = recordingStatuses[cameraId];
    if (!status) return 'disabled';
    if (status.recording_active) return 'recording';
    if (status.recording_enabled) return 'enabled';
    return 'disabled';
  }, [recordingStatuses]);

  const getModeClassName = (mode) => {
    switch (mode) {
      case 'continuous':
        return styles.modeContinuous;
      case 'person':
        return styles.modePerson;
      case 'motion':
        return styles.modeMotion;
      default:
        return '';
    }
  };

  const getModeLabel = (mode) => {
    switch (mode) {
      case 'continuous':
        return t('recording.playback.triggerContinuous');
      case 'person':
        return t('recording.playback.triggerPerson');
      case 'motion':
        return t('recording.playback.triggerMotion');
      default:
        return mode;
    }
  };



  const renderPlayer = () => {
    if (!activeSegment) {
      return (
        <div className={styles.emptyState}>
          <PlayCircleOutlined className={styles.emptyIcon} />
          <span className={styles.emptyText}>
            {t('recording.playback.selectSegment')}
          </span>
        </div>
      );
    }

    const playbackUrl = getRecordingPlaybackUrl(activeSegment.id);
    const isTs = (activeSegment.file_path || '').toLowerCase().endsWith('.ts');

    return (
      <div className={styles.playerContainer}>
        <video
          ref={videoRef}
          className={styles.playerVideo}
          src={isTs ? undefined : playbackUrl}
          autoPlay={isPlaying}
          loop={false}
          volume={volume}
          playbackRate={playbackRate}
          onTimeUpdate={(e) => setCurrentTime(e.target.currentTime)}
          onLoadedMetadata={(e) => setDuration(e.target.duration)}
          onEnded={handlePlayNext}
        />
        <div className={styles.playerControls}>
          <div className={styles.progressBar}>
            <div
              className={styles.progressFill}
              style={{ width: `${(currentTime / duration) * 100}%` }}
            />
          </div>
          <div className={styles.controlButtons}>
            <div className={styles.controlLeft}>
              <Tooltip title={isPlaying ? t('common.pause') : t('common.play')}>
                <span className={styles.controlBtn} onClick={handleTogglePlay}>
                  {isPlaying ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                </span>
              </Tooltip>
              <Tooltip title={t('recording.playback.prevSegment')}>
                <span
                  className={styles.controlBtn}
                  onClick={handlePlayPrev}
                  style={{ opacity: activeSegmentIndex > 0 ? 1 : 0.3 }}
                >
                  <StepBackwardOutlined />
                </span>
              </Tooltip>
              <Tooltip title={t('recording.playback.nextSegment')}>
                <span
                  className={styles.controlBtn}
                  onClick={handlePlayNext}
                  style={{ opacity: activeSegmentIndex < segments.length - 1 ? 1 : 0.3 }}
                >
                  <StepForwardOutlined />
                </span>
              </Tooltip>
              <span className={styles.timeDisplay}>
                {formatTime(currentTime)} / {formatTime(duration)}
              </span>
            </div>
            <div className={styles.controlRight}>
              <Tooltip title={t('recording.playback.speed')}>
                <span className={styles.speedSelector} onClick={handleSpeedChange}>
                  {playbackRate}x
                </span>
              </Tooltip>
              <Tooltip title={t('recording.playback.volume')}>
                <span className={styles.controlBtn}>
                  <SoundOutlined />
                </span>
              </Tooltip>
              <Tooltip title={t('recording.playback.fullscreen')}>
                <span className={styles.controlBtn}>
                  <FullscreenOutlined />
                </span>
              </Tooltip>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderSegmentCard = (segment) => {
    const isActive = activeSegment?.id === segment.id;
    const isSelected = selectedSegmentIds.has(segment.id);
    const thumbnailUrl = getRecordingThumbnailUrl(segment.id, 1.0);

    return (
      <div
        key={segment.id}
        className={`${styles.segmentCard} ${isActive ? styles.segmentCardActive : ''}`}
      >
        <div className={styles.segmentThumbnail}>
          <img
            src={thumbnailUrl}
            alt={segment.id}
            onError={(e) => {
              e.target.style.display = 'none';
              e.target.parentElement.innerHTML = '<span style="font-size: 24px; color: var(--text-color-149);"><svg viewBox="64 64 896 896" focusable="false" data-icon="video-camera" width="1em" height="1em" fill="currentColor" aria-hidden="true"><path d="M912 302.3L784 376V224c0-35.3-28.7-64-64-64H128c-35.3 0-64 28.7-64 64v576c0 35.3 28.7 64 64 64h592c35.3 0 64-28.7 64-64V648l128 73.7c21.3 12.3 48-3.1 48-27.6V330c0-24.6-26.7-40-48-27.7zM712 792H128V224h584v568z"></path></svg></span>';
            }}
          />
        </div>
        <div className={styles.segmentInfo} onClick={() => handleSegmentClick(segment)}>
          <div className={styles.segmentTime}>
            {dayjs(segment.start_time).format('HH:mm:ss')} - {dayjs(segment.end_time).format('HH:mm:ss')}
          </div>
          <div className={styles.segmentMeta}>
            <span className={styles.segmentDuration}>
              {formatDuration(segment.duration_seconds)}
            </span>
            <span>·</span>
            <span className={styles.segmentSize}>
              {formatFileSize(segment.file_size_bytes)}
            </span>
            <span className={`${styles.segmentMode} ${getModeClassName(segment.recording_mode)}`}>
              {getModeLabel(segment.recording_mode)}
            </span>
          </div>
        </div>
        <div className={styles.segmentActions}>
          <div className={styles.segmentCheckbox}>
            <Checkbox
              checked={isSelected}
              onChange={(e) => handleToggleSelectSegment(segment.id, e.target.checked)}
            />
          </div>
          <Popconfirm
            title={t('recording.playback.confirmDelete')}
            onConfirm={() => handleDeleteSegment(segment.id)}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
          >
            <span className={styles.segmentDeleteBtn}>
              <DeleteOutlined />
            </span>
          </Popconfirm>
        </div>
      </div>
    );
  };

  return (
    <div className={styles.playbackContainer}>
      {/* 左侧摄像头面板 */}
      <div className={styles.cameraSidebar}>
        <div className={styles.sidebarHeader}>
          <div className={styles.sidebarTitle}>
            <VideoCameraOutlined />
            <span>{t('recording.playback.cameras')}</span>
            <span className={styles.sidebarCount}>({cameras.length})</span>
          </div>
        </div>
        <div className={styles.cameraList}>
          {cameras.map((camera) => {
            const status = getCameraStatus(camera.did);
            const isActive = selectedCamera === camera.did;
            const segmentCount = cameraSegmentCounts[camera.did] || 0;

            return (
              <div
                key={camera.did}
                className={`${styles.cameraItem} ${isActive ? styles.cameraItemActive : ''}`}
                onClick={() => handleCameraChange(camera.did)}
              >
                <div className={styles.cameraIcon}>
                  <VideoCameraOutlined />
                </div>
                <div className={styles.cameraInfo}>
                  <div className={styles.cameraName}>{camera.name}</div>
                  <div className={styles.cameraSegmentCount}>
                    {segmentCount} {t('recording.playback.segments')}
                  </div>
                </div>
                <div
                  className={`${styles.cameraStatus} ${
                    status === 'recording'
                      ? styles.statusRecording
                      : status === 'enabled'
                      ? styles.statusEnabled
                      : styles.statusDisabled
                  }`}
                />
              </div>
            );
          })}
        </div>
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

      {/* 主内容区 */}
      <div className={styles.mainContent}>
        {/* 工具栏 */}
        <div className={styles.toolbar}>
          <div className={styles.toolbarLeft}>
            <Space size={12}>
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
                onChange={(val) => setModeFilter(val)}
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
            <Tooltip title={t('recording.playback.segmentList')}>
              <Button
                icon={<UnorderedListOutlined />}
                onClick={() => setSegmentDrawerVisible(true)}
              >
                {t('recording.playback.segmentList')}
              </Button>
            </Tooltip>
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
            <Popconfirm
              title={t('recording.playback.confirmCleanup')}
              onConfirm={handleCleanup}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
            >
              <Button icon={<ClearOutlined />} loading={loading}>
                {t('recording.playback.cleanup')}
              </Button>
            </Popconfirm>
          </div>
        </div>

        {/* 播放器区域 */}
        <div className={styles.playerArea}>
          <Spin spinning={loading && !activeSegment}>
            {renderPlayer()}
          </Spin>
        </div>

        {/* 时间轴 */}
        <div className={styles.timelineArea}>
          <TimelineBar
            segments={allSegments}
            activeSegmentId={activeSegment?.id}
            currentTime={currentTime}
            zoom={zoomLevel}
            onZoomChange={setZoomLevel}
            onSegmentClick={handleSegmentClick}
          />
        </div>

      </div>

      {/* 片段列表抽屉 */}
      <Drawer
        title={
          <div className={styles.drawerTitle}>
            <UnorderedListOutlined />
            <span>{t('recording.playback.segmentList')}</span>
            <span className={styles.drawerCount}>({total})</span>
          </div>
        }
        placement="right"
        width={400}
        open={segmentDrawerVisible}
        onClose={() => setSegmentDrawerVisible(false)}
        className={styles.segmentDrawer}
      >
        <Spin spinning={loading}>
          {segments.length > 0 ? (
            <>
              <div className={styles.drawerToolbar}>
                <Checkbox
                  checked={selectedSegmentIds.size === segments.length}
                  indeterminate={selectedSegmentIds.size > 0 && selectedSegmentIds.size < segments.length}
                  onChange={(e) => handleSelectAllSegments(e.target.checked)}
                >
                  <span style={{ fontSize: 12, color: 'var(--text-color-149)' }}>
                    {t('recording.playback.selectAll')}
                  </span>
                </Checkbox>
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
              <div className={styles.drawerSegmentList}>
                {segments.map(renderSegmentCard)}
              </div>
            </>
          ) : (
            <Empty
              description={t('recording.playback.noSegments')}
              style={{ padding: '80px 0' }}
            />
          )}
        </Spin>
      </Drawer>
    </div>
  );
};

export default RecordingPlayback;
