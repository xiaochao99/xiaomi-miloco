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
  Badge,
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
  WifiOutlined,
  VideoCameraFilled,
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
  getRecordingTranscodeUrl,
} from '@/api';
import TimelineBar from './components/TimelineBar';
import VideoPlayer from '@/pages/Instant/components/VideoPlayer';
import styles from './index.module.less';

/**
 * 将 dayjs 时间转换为当天秒数（从 00:00:00 开始）
 */
const dayjsToSeconds = (dt) => {
  return dt.hour() * 3600 + dt.minute() * 60 + dt.second() + dt.millisecond() / 1000;
};

/**
 * 检测浏览器是否真正支持 H265/HEVC 通过 MSE 播放
 * MediaSource.isTypeSupported 在 Windows 上可能误报 true，但实际 MSE buffer append 会失败
 * 需要同时检查 video.canPlayType 确认解码器可用
 */
const isHevcSupported = () => {
  // 先检查 MSE 容器支持
  const ms = window.MediaSource || window.WebKitMediaSource;
  const mseOk = ms && ms.isTypeSupported && (
    ms.isTypeSupported('video/mp4; codecs="hev1.1.6.L93.B0"') ||
    ms.isTypeSupported('video/mp4; codecs="hvc1.1.6.L93.B0"')
  );
  if (!mseOk) return false;

  // 再检查 video 元素是否真正能解码 HEVC（Windows 上 MSE 可能误报）
  const video = document.createElement('video');
  const canPlay = (
    video.canPlayType('video/mp4; codecs="hev1.1.6.L93.B0"') === 'probably' ||
    video.canPlayType('video/mp4; codecs="hvc1.1.6.L93.B0"') === 'probably'
  );
  // 如果 MSE 说支持但 video.canPlayType 返回空字符串或 maybe，说明解码器实际不可用
  if (!canPlay) return false;

  return true;
};

// 运行时 HEVC 失败标记：HLS 路径失败后直接走转码，避免反复 bufferAddCodecError
let hevcRuntimeFailed = false;

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
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(0.8);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [zoomLevel, setZoomLevel] = useState(0);
  const [segmentDrawerVisible, setSegmentDrawerVisible] = useState(false);

  // 全局播放时间（当天秒数，从 00:00:00 开始计算）
  const [globalTime, setGlobalTime] = useState(0);

  // 直播/回看模式状态
  const [playbackMode, setPlaybackMode] = useState('idle'); // 'idle' | 'playback' | 'live' | 'switching'
  const [liveCanvasRef, setLiveCanvasRef] = useState(null);
  const [hoverProgress, setHoverProgress] = useState(null); // { x, time } for hover preview

  const videoRef = useRef(null);
  const hlsRef = useRef(null);
  // 排序后的播放队列
  const playbackQueueRef = useRef([]);
  // 当前播放的片段在队列中的索引
  const currentQueueIndexRef = useRef(-1);
  // 预加载的下一个视频元素
  const preloadVideoRef = useRef(null);

  // ── 按时间排序的播放队列 ─────────────────────────────────────────────
  const sortedQueue = useMemo(() => {
    return [...allSegments].sort(
      (a, b) => dayjs(a.start_time).valueOf() - dayjs(b.start_time).valueOf(),
    );
  }, [allSegments]);

  // 同步到 ref
  useEffect(() => {
    playbackQueueRef.current = sortedQueue;
  }, [sortedQueue]);

  /**
   * 加载指定片段到播放器
   */
  const loadSegmentToPlayer = useCallback((segment, shouldPlay = true) => {
    const video = videoRef.current;
    if (!video || !segment) return;

    // 清理上一次的 hls 实例
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }

    const playbackUrl = getRecordingPlaybackUrl(segment.id);
    const isTs = (segment.file_path || '').toLowerCase().endsWith('.ts');

    if (!isTs) {
      video.src = playbackUrl;
      video.load();
      if (shouldPlay) video.play().catch(() => {});
      return;
    }

    // TS 文件：浏览器不支持 H265 或运行时已失败 → 直接走转码 MP4
    if (!isHevcSupported() || hevcRuntimeFailed) {
      video.src = getRecordingTranscodeUrl(segment.id);
      video.load();
      if (shouldPlay) video.play().catch(() => {});
      return;
    }

    // TS 文件且浏览器支持 H265：尝试 hls.js
    const setupHls = async () => {
      try {
        const Hls = (await import('hls.js')).default;
        const hls = new Hls({ enableWorker: false });
        hls.attachMedia(video);

        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          setDuration(hls.levels?.[0]?.details?.totalduration || segment.duration_seconds || 0);
          if (shouldPlay) video.play().catch(() => {});
        });

        hls.on(Hls.Events.ERROR, (_event, data) => {
          // bufferAddCodecError 是确定性的失败，立即标记并切换转码，不等 hls.js 重试
          if (data.details === 'bufferAddCodecError') {
            console.warn('[HLS] bufferAddCodecError — HEVC MSE 解码不可用，切换转码路径');
            hevcRuntimeFailed = true;
            hls.detachMedia();
            hls.destroy();
            hlsRef.current = null;
            video.src = getRecordingTranscodeUrl(segment.id);
            video.load();
            if (shouldPlay) video.play().catch(() => {});
            return;
          }
          if (!data.fatal) return;
          console.warn('[HLS] Fatal error:', data.details);
          hls.detachMedia();
          hls.destroy();
          hlsRef.current = null;
          video.src = getRecordingTranscodeUrl(segment.id);
          video.load();
          if (shouldPlay) video.play().catch(() => {});
        });

        hls.loadSource(getRecordingHlsUrl(segment.id));
        hlsRef.current = hls;
      } catch (e) {
        console.error('[HLS] Init error:', e);
        video.src = getRecordingTranscodeUrl(segment.id);
        video.load();
        if (shouldPlay) video.play().catch(() => {});
      }
    };

    setupHls();
  }, []);

  /**
   * 预加载下一个片段（在后台创建临时 video 元素触发浏览器缓存）
   */
  const preloadNextSegment = useCallback((nextSegment) => {
    if (!nextSegment) return;
    // 清理旧的预加载
    if (preloadVideoRef.current) {
      preloadVideoRef.current.pause();
      preloadVideoRef.current.removeAttribute('src');
      preloadVideoRef.current = null;
    }
    const isTs = (nextSegment.file_path || '').toLowerCase().endsWith('.ts');
    // 对 TS 片段，若浏览器不支持 H265 或运行时已失败 → 预加载转码后的 MP4
    const needTranscode = isTs && (!isHevcSupported() || hevcRuntimeFailed);
    const url = needTranscode
      ? getRecordingTranscodeUrl(nextSegment.id)
      : getRecordingPlaybackUrl(nextSegment.id);
    if (!isTs || !isHevcSupported() || hevcRuntimeFailed) {
      const v = document.createElement('video');
      v.preload = 'auto';
      v.src = url;
      v.load();
      preloadVideoRef.current = v;
    }
  }, []);

  // ── 播放器加载 activeSegment ──────────────────────────────────────────
  useEffect(() => {
    if (!activeSegment) return;
    // 切换片段时立即用后端 duration_seconds 作为初始值，避免显示 00:00:00
    setDuration(activeSegment.duration_seconds || 0);
    loadSegmentToPlayer(activeSegment, isPlaying);

    // 兜底：如果 1s 后 duration 仍为 0，再次强制使用后端返回的 duration_seconds
    const timer = setTimeout(() => {
      setDuration((prev) => {
        if (prev <= 0 && activeSegment?.duration_seconds > 0) {
          return activeSegment.duration_seconds;
        }
        return prev;
      });
    }, 1000);

    return () => {
      clearTimeout(timer);
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
    };
  }, [activeSegment?.id]);

  // ── 播放速率同步 ─────────────────────────────────────────────────────
  useEffect(() => {
    const video = videoRef.current;
    if (video) video.playbackRate = playbackRate;
  }, [playbackRate]);

  useEffect(() => {
    fetchCameras();
    fetchStorageStats();
    fetchRecordingStatuses();
  }, []);

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

  const fetchSegments = useCallback(async () => {
    if (!selectedCamera) return;
    setLoading(true);
    try {
      const dateStr = selectedDate.format('YYYY-MM-DD');
      const params = {
        camera_id: selectedCamera,
        start_time: `${dateStr}T00:00:00`,
        end_time: `${dateStr}T23:59:59`,
        page: 1,
        page_size: 1000,
        fast: true,  // 跳过 ffprobe，仅文件大小估算时长，大幅加速
      };
      if (modeFilter) params.mode = modeFilter;

      const res = await getRecordingSegments(params);
      if (res && res.code === 0) {
        const segs = res.data?.segments || [];
        // 前端兜底：若后端返回 duration_seconds 为 0，用 file_size_bytes 估算
        const repairedSegs = segs.map((s) => {
          if ((typeof s.duration_seconds !== 'number' || s.duration_seconds <= 0) && s.file_size_bytes > 0) {
            return {
              ...s,
              duration_seconds: Math.max(1, Math.round(s.file_size_bytes / (150 * 1024))),
            };
          }
          return s;
        });
        // 同时更新抽屉列表和时间轴
        setSegments(repairedSegs);
        setAllSegments(repairedSegs);
        setTotal(res.data?.total || repairedSegs.length);
        setCameraSegmentCounts((prev) => ({ ...prev, [selectedCamera]: res.data?.total || repairedSegs.length }));
      } else {
        setSegments([]);
        setAllSegments([]);
        setTotal(0);
      }
    } catch (error) {
      console.error('Failed to fetch segments:', error);
      message.error(t('recording.common.error'));
    } finally {
      setLoading(false);
    }
  }, [selectedCamera, selectedDate, modeFilter]);

  useEffect(() => {
    if (selectedCamera) {
      fetchSegments();
      setSelectedSegmentIds(new Set());
    }
  }, [fetchSegments]);

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

  /**
   * 点击片段：切换到该片段并播放，更新全局时间
   */
  const handleSegmentClick = useCallback((segment) => {
    setActiveSegment(segment);
    setIsPlaying(true);
    setPlaybackMode('playback');
    // 设置全局时间为片段的起始时间
    const startSec = dayjsToSeconds(dayjs(segment.start_time));
    setGlobalTime(startSec);
    // 更新队列索引
    const queue = playbackQueueRef.current;
    const idx = queue.findIndex((s) => s.id === segment.id);
    currentQueueIndexRef.current = idx;
    // 预加载下一个
    if (idx >= 0 && idx < queue.length - 1) {
      preloadNextSegment(queue[idx + 1]);
    }
  }, [preloadNextSegment]);

  /**
   * 播放下一个片段（无缝衔接）
   */
  const handlePlayNext = useCallback(() => {
    const queue = playbackQueueRef.current;
    const currentIdx = currentQueueIndexRef.current;
    const nextIdx = currentIdx + 1;

    if (nextIdx >= 0 && nextIdx < queue.length) {
      const nextSegment = queue[nextIdx];
      currentQueueIndexRef.current = nextIdx;
      setActiveSegment(nextSegment);
      setGlobalTime(dayjsToSeconds(dayjs(nextSegment.start_time)));
      setPlaybackMode('playback');
      // 预加载下下一个
      if (nextIdx + 1 < queue.length) {
        preloadNextSegment(queue[nextIdx + 1]);
      }
    } else {
      // 没有更多片段，切换到直播
      handleSwitchToLive();
    }
  }, [preloadNextSegment]);

  const handleSwitchToLive = useCallback(() => {
    setActiveSegment(null);
    setIsPlaying(false);
    setGlobalTime(0);
    setDuration(0);
    setPlaybackMode('switching');
    setTimeout(() => {
      setPlaybackMode('live');
    }, 800);
  }, []);

  /**
   * 播放上一个片段
   */
  const handlePlayPrev = useCallback(() => {
    const queue = playbackQueueRef.current;
    const currentIdx = currentQueueIndexRef.current;
    const prevIdx = currentIdx - 1;

    if (prevIdx >= 0 && prevIdx < queue.length) {
      const prevSegment = queue[prevIdx];
      currentQueueIndexRef.current = prevIdx;
      setActiveSegment(prevSegment);
      setGlobalTime(dayjsToSeconds(dayjs(prevSegment.start_time)));
      setPlaybackMode('playback');
    }
  }, []);

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

  /**
   * 进度条点击：将点击位置转换为当前片段内的秒数进行 seek
   */
  const handleProgressBarClick = useCallback((e) => {
    const bar = e.currentTarget;
    const rect = bar.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const seekTime = ratio * duration;
    const video = videoRef.current;
    if (video && duration > 0) {
      video.currentTime = seekTime;
      // 更新全局时间
      if (activeSegment) {
        const segmentStartSec = dayjsToSeconds(dayjs(activeSegment.start_time));
        setGlobalTime(segmentStartSec + seekTime);
      }
    }
  }, [duration, activeSegment]);

  const handleProgressBarHover = useCallback((e) => {
    const bar = e.currentTarget;
    const rect = bar.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const hoverTime = ratio * duration;
    const x = e.clientX - rect.left;
    setHoverProgress({ x, time: hoverTime });
  }, [duration]);

  const handleProgressBarLeave = useCallback(() => {
    setHoverProgress(null);
  }, []);

  /**
   * 时间轴 seek：接收全局时间（当天秒数），定位到对应片段并设置 offset
   */
  const handleTimelineSeek = useCallback((globalTimeSec) => {
    const queue = playbackQueueRef.current;
    // 找到包含该全局时间的片段（使用 duration_seconds 计算结束时间，与 segmentBlocks 保持一致）
    const targetSegment = queue.find((seg) => {
      const startSec = dayjsToSeconds(dayjs(seg.start_time));
      const durationSec = typeof seg.duration_seconds === 'number' && seg.duration_seconds > 0
        ? seg.duration_seconds
        : Math.max(0, dayjsToSeconds(dayjs(seg.end_time)) - startSec);
      const endSec = startSec + durationSec;
      return globalTimeSec >= startSec && globalTimeSec <= endSec;
    });

    if (targetSegment) {
      const segmentStartSec = dayjsToSeconds(dayjs(targetSegment.start_time));
      const offset = globalTimeSec - segmentStartSec;

      if (targetSegment.id !== activeSegment?.id) {
        // 需要切换片段
        setActiveSegment(targetSegment);
        const idx = queue.findIndex((s) => s.id === targetSegment.id);
        currentQueueIndexRef.current = idx;
        // 切换后在 useEffect 中加载视频，然后 seek
        // 使用 setTimeout 等视频加载后再 seek
        setTimeout(() => {
          const video = videoRef.current;
          if (video) {
            video.currentTime = offset;
            if (isPlaying) video.play().catch(() => {});
          }
        }, 100);
      } else {
        // 同一片段内 seek
        const video = videoRef.current;
        if (video && duration > 0) {
          const clampedOffset = Math.max(0, Math.min(offset, duration));
          video.currentTime = clampedOffset;
        }
      }
      setGlobalTime(globalTimeSec);
    }
  }, [activeSegment, duration, isPlaying]);

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
    // Mode indicator badge
    const renderModeBadge = () => {
      if (playbackMode === 'playback') {
        return (
          <div className={`${styles.modeBadge} ${styles.modeBadgePlayback}`}>
            <VideoCameraFilled />
            <span>{t('recording.playback.modePlayback')}</span>
          </div>
        );
      }
      if (playbackMode === 'live') {
        return (
          <div className={`${styles.modeBadge} ${styles.modeBadgeLive}`}>
            <WifiOutlined />
            <span>{t('recording.playback.modeLive')}</span>
          </div>
        );
      }
      if (playbackMode === 'switching') {
        return (
          <div className={`${styles.modeBadge} ${styles.modeBadgeSwitching}`}>
            <Spin size="small" />
            <span>{t('recording.playback.switchingToLive')}</span>
          </div>
        );
      }
      return null;
    };

    // Live stream mode
    if (playbackMode === 'live' || playbackMode === 'switching') {
      return (
        <div className={styles.playerContainer}>
          <div className={styles.liveContainer}>
            {playbackMode === 'switching' ? (
              <div className={styles.switchingOverlay}>
                <Spin size="large" />
                <span className={styles.switchingText}>
                  {t('recording.playback.switchingToLive')}
                </span>
              </div>
            ) : (
              selectedCamera && (
                <VideoPlayer
                  cameraId={selectedCamera}
                  channel={0}
                  onCanvasRef={setLiveCanvasRef}
                  style={{ width: '100%', height: '100%' }}
                />
              )
            )}
          </div>
          {renderModeBadge()}
          <div className={styles.liveOverlayControls}>
            <Button
              icon={<PlayCircleOutlined />}
              onClick={() => setPlaybackMode('idle')}
              className={styles.backToPlaybackBtn}
            >
              {t('recording.playback.backToPlayback')}
            </Button>
          </div>
        </div>
      );
    }

    // Idle state (no segment selected, no live)
    if (!activeSegment || playbackMode === 'idle') {
      return (
        <div className={styles.emptyState}>
          <PlayCircleOutlined className={styles.emptyIcon} />
          <span className={styles.emptyText}>
            {t('recording.playback.selectSegment')}
          </span>
          {selectedCamera && segments.length > 0 && (
            <Button
              type="primary"
              icon={<WifiOutlined />}
              onClick={handleSwitchToLive}
              className={styles.liveButton}
            >
              {t('recording.playback.modeLive')}
            </Button>
          )}
        </div>
      );
    }

    // Playback mode
    const playbackUrl = getRecordingPlaybackUrl(activeSegment.id);
    const isTs = (activeSegment.file_path || '').toLowerCase().endsWith('.ts');

    return (
      <div className={styles.playerContainer}>
        {renderModeBadge()}
        <video
          ref={videoRef}
          className={styles.playerVideo}
          src={isTs ? undefined : playbackUrl}
          autoPlay={isPlaying}
          loop={false}
          volume={volume}
          playbackRate={playbackRate}
          onTimeUpdate={(e) => {
            const localTime = e.target.currentTime;
            if (activeSegment) {
              const segmentStartSec = dayjsToSeconds(dayjs(activeSegment.start_time));
              setGlobalTime(segmentStartSec + localTime);
            }
          }}
          onLoadedMetadata={(e) => {
            const videoDuration = e.target.duration;
            const fallback = activeSegment?.duration_seconds || 0;
            // NaN/Infinity 都视为无效，强制回退到后端返回的 duration_seconds
            const validDuration = (typeof videoDuration === 'number' && Number.isFinite(videoDuration) && videoDuration > 0)
              ? videoDuration
              : fallback;
            setDuration(validDuration);
          }}
          onEnded={handlePlayNext}
        />
        <div className={styles.playerControls}>
          <div
            className={styles.progressBarClickable}
            onClick={handleProgressBarClick}
            onMouseMove={handleProgressBarHover}
            onMouseLeave={handleProgressBarLeave}
          >
            <div
              className={styles.progressFill}
              style={{ width: `${duration > 0 ? (Math.min(activeSegment ? globalTime - dayjsToSeconds(dayjs(activeSegment.start_time)) : 0, duration) / duration) * 100 : 0}%` }}
            />
            {hoverProgress && (
              <>
                <div
                  className={styles.progressHoverLine}
                  style={{ left: `${hoverProgress.x}px` }}
                />
                <div
                  className={styles.progressHoverTime}
                  style={{ left: `${hoverProgress.x}px` }}
                >
                  {formatTime(hoverProgress.time)}
                </div>
              </>
            )}
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
                {formatTime(activeSegment ? Math.min(globalTime - dayjsToSeconds(dayjs(activeSegment.start_time)), duration) : 0)} / {formatTime(duration)}
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
              <Tooltip title={t('recording.playback.modeLive')}>
                <span className={styles.controlBtn} onClick={handleSwitchToLive}>
                  <WifiOutlined />
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
            loading="lazy"
            decoding="async"
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
            activeSegment={activeSegment}
            globalTime={globalTime}
            selectedDate={selectedDate}
            zoom={zoomLevel}
            onZoomChange={setZoomLevel}
            onSegmentClick={handleSegmentClick}
            onSeek={handleTimelineSeek}
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
