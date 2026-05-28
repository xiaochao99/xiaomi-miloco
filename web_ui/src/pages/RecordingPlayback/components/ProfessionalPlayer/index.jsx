import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  PlayCircleOutlined,
  PauseOutlined,
  StepBackwardOutlined,
  StepForwardOutlined,
  SoundOutlined,
  SoundFilled,
  ExpandOutlined,
  CompressOutlined,
  ReloadOutlined,
  CameraOutlined,
  FastForwardOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Spin, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  getRecordingPlaybackUrl,
  getRecordingVideoInfo,
} from '@/api';
import styles from './index.module.less';

// 动态导入ffmpeg.wasm
let FFmpeg;
let fetchFile;

const SPEED_OPTIONS = [0.5, 1, 1.5, 2, 4];

// 检测浏览器是否支持H.265/HEVC
const isHEVCSupported = () => {
  const video = document.createElement('video');
  return video.canPlayType('video/mp4; codecs="hev1.1.6.L93.B0"') !== '' ||
         video.canPlayType('video/mp4; codecs="hev1.2.4.L93.B0"') !== '' ||
         video.canPlayType('video/mp4; codecs="hev1.3.6.L93.B0"') !== '' ||
         video.canPlayType('video/mp4; codecs="hev1"') !== '';
};

const ProfessionalPlayer = ({
  segment,
  segments = [],  // All segments for timeline display
  cameraName = '',
  autoPlay = true,
  onPlayNext,
  onPlayPrev,
  hasNext = false,
  hasPrev = false,
}) => {
  const { t } = useTranslation();
  const videoRef = useRef(null);
  const progressRef = useRef(null);
  const containerRef = useRef(null);
  const onPlayNextRef = useRef(onPlayNext);
  const abortRef = useRef(null);
  const ffmpegRef = useRef(null);
  const handleClientTranscodeRef = useRef(null);
  const needsTranscodeRef = useRef(false);
  const clientTranscodingRef = useRef(false);
  const videoInfoRef = useRef(null);

  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [buffered, setBuffered] = useState(0);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [showSpeedMenu, setShowSpeedMenu] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [videoSrc, setVideoSrc] = useState('');
  const [needsTranscode, setNeedsTranscode] = useState(false);
  const [videoInfo, setVideoInfo] = useState(null);
  const [showControls, setShowControls] = useState(true);
  const [videoError, setVideoError] = useState(false);
  const [clientTranscoding, setClientTranscoding] = useState(false);
  const [transcodeProgress, setTranscodeProgress] = useState(0);
  const [blobUrl, setBlobUrl] = useState(null);

  // 同步更新 needsTranscodeRef 和 clientTranscodingRef
  useEffect(() => {
    needsTranscodeRef.current = needsTranscode;
  }, [needsTranscode]);

  useEffect(() => {
    clientTranscodingRef.current = clientTranscoding;
  }, [clientTranscoding]);

  useEffect(() => {
    videoInfoRef.current = videoInfo;
  }, [videoInfo]);

  // 前端客户端转码函数
  const handleClientTranscode = useCallback(async () => {
    if (clientTranscodingRef.current) return;
    
    try {
      setClientTranscoding(true);
      setTranscodeProgress(0);
      setLoading(true);
      
      // 清理之前的Blob URL
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
        setBlobUrl(null);
      }
      
      // 动态导入ffmpeg.wasm
      if (!FFmpeg) {
        const ffmpegModule = await import('@ffmpeg/ffmpeg');
        FFmpeg = ffmpegModule.FFmpeg;
      }
      if (!fetchFile) {
        const utilModule = await import('@ffmpeg/util');
        fetchFile = utilModule.fetchFile;
      }
      
      // 初始化ffmpeg实例
      if (!ffmpegRef.current) {
        ffmpegRef.current = new FFmpeg();
        
        // 监听转码进度
        ffmpegRef.current.on('progress', ({ progress }) => {
          setTranscodeProgress(Math.round(progress * 100));
        });
        
        // 加载ffmpeg核心
        await ffmpegRef.current.load();
      }
      
      const ffmpeg = ffmpegRef.current;
      
      // 从服务器获取视频文件
      const videoUrl = getRecordingPlaybackUrl(segment.id);
      const response = await fetch(videoUrl);
      const videoData = await response.arrayBuffer();
      
      // 写入输入文件
      await ffmpeg.writeFile('input.mp4', new Uint8Array(videoData));
      
      // 执行H.265到H.264转码，保持原始帧率和时间基
      await ffmpeg.exec([
        '-i', 'input.mp4',
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-crf', '23',
        '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
        '-vsync', 'cfr',
        '-movflags', '+faststart',
        '-an',
        'output.mp4'
      ]);
      
      // 读取输出文件
      const outputData = await ffmpeg.readFile('output.mp4');
      
      // 创建新的Blob URL
      const blob = new Blob([outputData.buffer], { type: 'video/mp4' });
      const newBlobUrl = URL.createObjectURL(blob);
      
      // 清理临时文件
      await ffmpeg.deleteFile('input.mp4');
      await ffmpeg.deleteFile('output.mp4');
      
      // 更新状态
      setBlobUrl(newBlobUrl);
      setVideoSrc(newBlobUrl);
      setNeedsTranscode(false);
      setLoading(false);
      setClientTranscoding(false);
      
    } catch (error) {
      console.error('Client transcode failed:', error);
      setClientTranscoding(false);
      setLoading(false);
      setVideoError(true);
    }
  }, [segment, blobUrl]);

  // 保持 ref 始终指向最新的 handleClientTranscode
  useEffect(() => {
    handleClientTranscodeRef.current = handleClientTranscode;
  }, [handleClientTranscode]);

  // 组件卸载时清理Blob URL
  useEffect(() => {
    return () => {
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
      }
    };
  }, [blobUrl]);

  // Keep onPlayNext ref up to date
  useEffect(() => {
    onPlayNextRef.current = onPlayNext;
  }, [onPlayNext]);

  useEffect(() => {
    if (!segment) {
      setVideoSrc('');
      setVideoInfo(null);
      setVideoError(false);
      return;
    }

    // Cancel any previous in-flight detection
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    // 清理之前的Blob URL
    if (blobUrl) {
      URL.revokeObjectURL(blobUrl);
      setBlobUrl(null);
    }

    // 取消正在进行的转码
    setClientTranscoding(false);
    setTranscodeProgress(0);
    
    setLoading(true);
    setPlaying(false);
    setCurrentTime(0);
    setDuration(0);
    setBuffered(0);
    setVideoError(false);

    const detectAndSetSource = async () => {
      try {
        const res = await getRecordingVideoInfo(segment.id);
        // Check if this request was cancelled
        if (controller.signal.aborted) return;

        if (res && res.code === 0 && res.data) {
          setVideoInfo(res.data);
          if (res.data.needs_transcode) {
            // 视频需要转码（H.265），检测浏览器是否支持
            if (isHEVCSupported()) {
              // 浏览器支持H.265，直接播放源视频
              setNeedsTranscode(false);
              setVideoSrc(getRecordingPlaybackUrl(segment.id));
            } else {
              // 浏览器不支持H.265，直接触发前端客户端转码，不等待视频加载失败
              setNeedsTranscode(true);
              setVideoSrc(''); // 先清空视频源
              handleClientTranscodeRef.current?.();
            }
          } else {
            setNeedsTranscode(false);
            setVideoSrc(getRecordingPlaybackUrl(segment.id));
          }
        } else {
          // When video info detection fails (e.g. ffprobe not available),
          // 先尝试播放源视频，由 onError 触发前端转码
          setNeedsTranscode(true);
          setVideoSrc(getRecordingPlaybackUrl(segment.id));
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        // 先尝试播放源视频，由 onError 触发前端转码
        setNeedsTranscode(true);
        setVideoSrc(getRecordingPlaybackUrl(segment.id));
      }
    };

    detectAndSetSource();

    return () => {
      controller.abort();
    };
  }, [segment?.id]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onTimeUpdate = () => {
      setCurrentTime(video.currentTime);
      if (video.buffered.length > 0) {
        setBuffered(video.buffered.end(video.buffered.length - 1));
      }
    };
    const onDurationChange = () => setDuration(video.duration || 0);
    const onLoadedData = () => {
      setLoading(false);
      setVideoError(false);
      if (autoPlay) {
        video.play().catch(() => {});
      }
    };
    const onWaiting = () => setLoading(true);
    const onCanPlay = () => setLoading(false);
    const onEnded = () => {
      setPlaying(false);
      if (onPlayNextRef.current) onPlayNextRef.current();
    };
    
    const onError = () => {
      setLoading(false);
      setPlaying(false);
      
      const isHEVC = videoInfoRef.current?.codec === 'hevc' || videoInfoRef.current?.codec === 'h265';
      
      // 使用ref避免闭包问题：
      // 1. 如果后端标记需要转码且未在转码中 → 尝试前端客户端转码
      // 2. 如果视频是HEVC编码但浏览器播放失败（即使声称支持HEVC）→ 也尝试转码作为兜底
      if (!clientTranscodingRef.current && (needsTranscodeRef.current || isHEVC)) {
        needsTranscodeRef.current = true;
        handleClientTranscodeRef.current?.();
      } else {
        setVideoError(true);
      }
      
      console.error('Video load error:', video.src, video.error, { codec: videoInfoRef.current?.codec, needsTranscode: needsTranscodeRef.current });
    };

    video.addEventListener('play', onPlay);
    video.addEventListener('pause', onPause);
    video.addEventListener('timeupdate', onTimeUpdate);
    video.addEventListener('durationchange', onDurationChange);
    video.addEventListener('loadeddata', onLoadedData);
    video.addEventListener('waiting', onWaiting);
    video.addEventListener('canplay', onCanPlay);
    video.addEventListener('ended', onEnded);
    video.addEventListener('error', onError);

    return () => {
      video.removeEventListener('play', onPlay);
      video.removeEventListener('pause', onPause);
      video.removeEventListener('timeupdate', onTimeUpdate);
      video.removeEventListener('durationchange', onDurationChange);
      video.removeEventListener('loadeddata', onLoadedData);
      video.removeEventListener('waiting', onWaiting);
      video.removeEventListener('canplay', onCanPlay);
      video.removeEventListener('ended', onEnded);
      video.removeEventListener('error', onError);
    };
  }, [videoSrc, autoPlay]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.playbackRate = speed;
  }, [speed]);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  useEffect(() => {
    let timer;
    const handleMouseMove = () => {
      setShowControls(true);
      clearTimeout(timer);
      timer = setTimeout(() => {
        if (playing) setShowControls(false);
      }, 3000);
    };
    const container = containerRef.current;
    if (container) {
      container.addEventListener('mousemove', handleMouseMove);
      container.addEventListener('mouseleave', () => {
        if (playing) setShowControls(false);
      });
    }
    return () => {
      if (container) {
        container.removeEventListener('mousemove', handleMouseMove);
      }
      clearTimeout(timer);
    };
  }, [playing]);

  const togglePlay = useCallback(() => {
    const video = videoRef.current;
    if (!video || !videoSrc) return;
    if (video.paused) {
      video.play().catch(() => {});
    } else {
      video.pause();
    }
  }, [videoSrc]);

  const handleProgressClick = useCallback((e) => {
    const video = videoRef.current;
    const bar = progressRef.current;
    if (!video || !bar || !duration) return;
    const rect = bar.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    video.currentTime = ratio * duration;
  }, [duration]);

  const skipSeconds = useCallback((seconds) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = Math.max(0, Math.min(video.duration, video.currentTime + seconds));
  }, []);

  const toggleMute = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    video.muted = !video.muted;
    setMuted(video.muted);
  }, []);

  const handleVolumeChange = useCallback((e) => {
    const video = videoRef.current;
    if (!video) return;
    const val = parseFloat(e.target.value);
    video.volume = val;
    setVolume(val);
    if (val === 0) {
      video.muted = true;
      setMuted(true);
    } else if (video.muted) {
      video.muted = false;
      setMuted(false);
    }
  }, []);

  const toggleFullscreen = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      container.requestFullscreen();
    }
  }, []);

  const handleDownload = useCallback(() => {
    if (!segment) return;
    const link = document.createElement('a');
    link.href = videoSrc;
    link.download = `recording_${segment.id}.mp4`;
    link.click();
  }, [segment, videoSrc]);

  const formatTime = (seconds) => {
    if (!seconds || !isFinite(seconds)) return '00:00';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) {
      return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  const progressPercent = duration ? (currentTime / duration) * 100 : 0;
  const bufferedPercent = duration ? (buffered / duration) * 100 : 0;
  
  // Compute segment markers for the unified timeline
  const segmentMarkers = useMemo(() => {
    if (!segments.length || !segment) return [];
    
    // Sort segments by start_time
    const sorted = [...segments].sort(
      (a, b) => new Date(a.start_time) - new Date(b.start_time)
    );
    
    // Find the time range
    const firstStart = new Date(sorted[0].start_time);
    const lastSeg = sorted[sorted.length - 1];
    const lastEnd = lastSeg.is_live 
      ? new Date()  // Live segment uses current time
      : new Date(lastSeg.end_time || lastSeg.start_time);
    
    const totalRange = (lastEnd - firstStart) / 1000; // in seconds
    if (totalRange <= 0) return [];
    
    return sorted.map((seg, idx) => {
      const segStart = new Date(seg.start_time);
      const segEnd = seg.is_live 
        ? new Date()
        : new Date(seg.end_time || seg.start_time);
      const left = ((segStart - firstStart) / 1000 / totalRange) * 100;
      const width = Math.max(((segEnd - segStart) / 1000 / totalRange) * 100, 0.5);
      
      return {
        id: seg.id,
        isActive: seg.id === segment?.id,
        isLive: seg.is_live,
        left,
        width,
      };
    });
  }, [segments, segment]);

  if (!segment) {
    return (
      <div className={styles.noVideo}>
        <CameraOutlined className={styles.noVideoIcon} />
        <span className={styles.noVideoText}>{t('recording.playback.selectSegment')}</span>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={styles.playerWrapper}
      onDoubleClick={toggleFullscreen}
    >
      <div className={styles.videoContainer}>
        {videoSrc && (
          <video
            ref={videoRef}
            src={videoSrc}
            preload="auto"
            onClick={togglePlay}
            playsInline
          />
        )}

        <div className={styles.watermark}>
          <span className={styles.watermarkText}>{cameraName}</span>
          <span className={styles.watermarkText}>
            {segment.start_time ? new Date(segment.start_time).toLocaleString() : ''}
          </span>
        </div>

        {needsTranscode && !videoError && (
          <div className={styles.transcodeBadge}>
            {t('recording.playback.transcoding')}
          </div>
        )}

        {loading && !videoError && (
          <div className={styles.loadingOverlay}>
            <Spin size="large" />
          </div>
        )}

        {clientTranscoding && (
          <div className={styles.loadingOverlay}>
            <div className={styles.transcodeContainer}>
              <Spin size="large" />
              <div className={styles.transcodeText}>
                {t('recording.playback.transcoding')} {transcodeProgress}%
              </div>
              <div className={styles.progressBar}>
                <div 
                  className={styles.progressFill} 
                  style={{ width: `${transcodeProgress}%` }}
                />
              </div>
            </div>
          </div>
        )}

        {videoError && (
          <div className={styles.errorOverlay}>
            <div className={styles.errorContent}>
              <WarningOutlined className={styles.errorIcon} />
              <span className={styles.errorText}>{t('recording.playback.loadFailed')}</span>
              <button
                className={styles.retryBtn}
                onClick={() => {
                  setVideoError(false);
                  setLoading(true);
                  if (videoRef.current) {
                    videoRef.current.load();
                  }
                }}
              >
                <ReloadOutlined /> {t('recording.playback.reload')}
              </button>
            </div>
          </div>
        )}

        {!playing && !loading && !videoError && videoSrc && (
          <div className={styles.videoOverlay}>
            <div className={styles.playButtonLarge} onClick={togglePlay}>
              <PlayCircleOutlined />
            </div>
          </div>
        )}
      </div>

      <div className={`${styles.controls} ${showControls || !playing ? styles.alwaysShow : ''}`}>
        <div className={styles.progressRow}>
          <span className={styles.timeLabel}>{formatTime(currentTime)}</span>
          <div
            ref={progressRef}
            className={styles.progressBar}
            onClick={handleProgressClick}
          >
            <div className={styles.progressBuffered} style={{ width: `${bufferedPercent}%` }} />
            <div className={styles.progressPlayed} style={{ width: `${progressPercent}%` }}>
              <div className={styles.progressHandle} />
            </div>
            {/* Segment markers on the timeline */}
            {segmentMarkers.map((marker) => (
              <div
                key={marker.id}
                className={`${styles.segmentMarker} ${marker.isActive ? styles.segmentMarkerActive : ''} ${marker.isLive ? styles.segmentMarkerLive : ''}`}
                style={{ left: `${marker.left}%`, width: `${marker.width}%` }}
                title={marker.isLive ? 'Live recording' : ''}
              />
            ))}
          </div>
          <span className={styles.timeLabel}>{formatTime(duration)}</span>
        </div>

        <div className={styles.controlBar}>
          <div className={styles.controlLeft}>
            <Tooltip title={playing ? t('recording.playback.pause') : t('recording.playback.play')}>
              <button className={styles.ctrlBtn} onClick={togglePlay}>
                {playing ? <PauseOutlined /> : <PlayCircleOutlined />}
              </button>
            </Tooltip>
            <Tooltip title={t('recording.playback.backward10s')}>
              <button className={styles.ctrlBtn} onClick={() => skipSeconds(-10)}>
                <StepBackwardOutlined />
              </button>
            </Tooltip>
            <Tooltip title={t('recording.playback.forward10s')}>
              <button className={styles.ctrlBtn} onClick={() => skipSeconds(10)}>
                <StepForwardOutlined />
              </button>
            </Tooltip>

            <div className={styles.volumeGroup}>
              <button className={styles.ctrlBtn} onClick={toggleMute}>
                {muted || volume === 0 ? <SoundOutlined /> : <SoundFilled />}
              </button>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={muted ? 0 : volume}
                onChange={handleVolumeChange}
                className={styles.volumeSlider}
                style={{
                  accentColor: '#00bdc3',
                }}
              />
            </div>

            <div
              className={styles.speedControl}
              onMouseEnter={() => setShowSpeedMenu(true)}
              onMouseLeave={() => setShowSpeedMenu(false)}
            >
              <Tooltip title={t('recording.playback.speed')}>
                <button className={`${styles.ctrlBtn} ${speed !== 1 ? styles.active : ''}`}>
                  <FastForwardOutlined />
                  <span className={styles.speedLabel}>{speed}x</span>
                </button>
              </Tooltip>
              {showSpeedMenu && (
                <div className={styles.speedMenu}>
                  {SPEED_OPTIONS.map((s) => (
                    <button
                      key={s}
                      className={`${styles.speedOption} ${speed === s ? styles.active : ''}`}
                      onClick={() => {
                        setSpeed(s);
                        setShowSpeedMenu(false);
                      }}
                    >
                      {s}x
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className={styles.controlRight}>
            {hasPrev && (
              <Tooltip title={t('recording.playback.prevSegment')}>
                <button className={styles.ctrlBtn} onClick={onPlayPrev}>
                  <StepBackwardOutlined />
                </button>
              </Tooltip>
            )}
            {hasNext && (
              <Tooltip title={t('recording.playback.nextSegment')}>
                <button className={styles.ctrlBtn} onClick={onPlayNext}>
                  <StepForwardOutlined />
                </button>
              </Tooltip>
            )}
            <Tooltip title={t('recording.playback.reload')}>
              <button
                className={styles.ctrlBtn}
                onClick={() => {
                  if (videoRef.current) {
                    videoRef.current.load();
                  }
                }}
              >
                <ReloadOutlined />
              </button>
            </Tooltip>
            <Tooltip title={isFullscreen ? t('recording.playback.exitFullscreen') : t('recording.playback.fullscreen')}>
              <button className={styles.ctrlBtn} onClick={toggleFullscreen}>
                {isFullscreen ? <CompressOutlined /> : <ExpandOutlined />}
              </button>
            </Tooltip>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProfessionalPlayer;
