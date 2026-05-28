import React, { useRef, useState, useCallback, useMemo, useEffect } from 'react';
import dayjs from 'dayjs';
import {
  MinusOutlined,
  PlusOutlined,
  CompressOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { Tooltip } from 'antd';
import styles from './index.module.less';

const MINUTES_PER_DAY = 24 * 60;

const ZOOM_LEVELS = [
  { duration: 1440, label: '24h' },
  { duration: 720,  label: '12h' },
  { duration: 360,  label: '6h' },
  { duration: 180,  label: '3h' },
  { duration: 60,   label: '1h' },
  { duration: 30,   label: '30m' },
  { duration: 15,   label: '15m' },
  { duration: 5,    label: '5m' },
  { duration: 1,    label: '1m' },
];

const MIN_ZOOM_INDEX = 0;
const MAX_ZOOM_INDEX = ZOOM_LEVELS.length - 1;

const MODE_CONFIG = {
  continuous: { color: '#4096ff', labelKey: 'recording.playback.triggerContinuous' },
  person:    { color: '#73d13d', labelKey: 'recording.playback.triggerPerson' },
  motion:    { color: '#ffc53d', labelKey: 'recording.playback.triggerMotion' },
};

const getTickConfig = (zoomIndex) => {
  const configs = [
    { step: 10, labelStep: 60 },     // 24h: 每10分钟小刻度, 每小时带标签
    { step: 10, labelStep: 60 },     // 12h: 同上
    { step: 10, labelStep: 60 },     // 6h
    { step: 10, labelStep: 30 },     // 3h: 每10分钟小刻度, 每30分钟带标签
    { step: 2,  labelStep: 10 },     // 1h: 10分钟5格 (2分钟×5=10分钟)
    { step: 2,  labelStep: 10 },     // 30m: 同上
    { step: 1,  labelStep: 5 },      // 15m: 5分钟5格 (1分钟×5=5分钟)
    { step: 1,  labelStep: 1 },      // 5m: 每分钟带标签
    { step: 0.25, labelStep: 1 },    // 1m: 15秒小刻度, 每分钟带标签
  ];
  return configs[Math.min(zoomIndex, configs.length - 1)];
};

/**
 * TimelineBar – 专业录像时间轴
 *
 * Props:
 *   segments       : RecordingSegment[]
 *   activeSegmentId: string | null
 *   currentTime    : number
 *   zoom           : number (0-8)
 *   onZoomChange   : (zoomIndex: number) => void
 *   onSegmentClick : (segment: RecordingSegment) => void
 */
const TimelineBar = ({
  segments = [],
  activeSegmentId,
  currentTime = 0,
  zoom = 0,
  onZoomChange,
  onSegmentClick,
}) => {
  const { t } = useTranslation();
  const scrollContainerRef = useRef(null);
  const isDragging = useRef(false);
  const dragStartX = useRef(0);
  const dragScrollLeft = useRef(0);
  const [hoverTime, setHoverTime] = useState(null);

  const currentZoom = ZOOM_LEVELS[zoom] || ZOOM_LEVELS[0];
  const viewDuration = currentZoom.duration;
  const zoomRatio = MINUTES_PER_DAY / viewDuration;

  // ── 刻度 ──────────────────────────────────────────────────────────────
  const tickConfig = useMemo(() => getTickConfig(zoom), [zoom]);

  const tickMarks = useMemo(() => {
    const marks = [];
    const { step, labelStep } = tickConfig;
    for (let minute = 0; minute <= MINUTES_PER_DAY; minute += step) {
      const isLabel = minute % labelStep === 0 || minute === 0;
      let label = '';
      if (isLabel) {
        const h = Math.floor(minute / 60);
        const m = minute % 60;
        label = m === 0
          ? `${String(h).padStart(2, '0')}:00`
          : `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
      }
      marks.push({ left: (minute / MINUTES_PER_DAY) * 100, isLabel, label });
    }
    return marks;
  }, [tickConfig]);

  // ── 片段数据 ──────────────────────────────────────────────────────────
  const segmentBlocks = useMemo(() => {
    if (!segments.length) return [];
    return segments
      .map((seg) => {
        const start = dayjs(seg.start_time);
        const end = dayjs(seg.end_time);
        const startMin = start.hour() * 60 + start.minute() + start.second() / 60;
        const endMin = end.hour() * 60 + end.minute() + end.second() / 60;
        const left = (startMin / MINUTES_PER_DAY) * 100;
        const width = Math.max(((endMin - startMin) / MINUTES_PER_DAY) * 100, 0.1 / zoomRatio);
        return { ...seg, left, width };
      })
      .filter((b) => b.width > 0);
  }, [segments, zoomRatio]);

  // ── 播放指示线 ────────────────────────────────────────────────────────
  const activeBlock = useMemo(
    () => segmentBlocks.find((b) => b.id === activeSegmentId),
    [segmentBlocks, activeSegmentId],
  );

  const playheadInfo = useMemo(() => {
    if (!activeBlock) return null;
    const start = dayjs(activeBlock.start_time);
    const playheadTime = start.add(currentTime, 'second');
    const minute = playheadTime.hour() * 60 + playheadTime.minute() + playheadTime.second() / 60;
    return {
      left: (minute / MINUTES_PER_DAY) * 100,
      timeStr: playheadTime.format('YYYY-MM-DD HH:mm:ss'),
      label: playheadTime.format('HH:mm:ss'),
    };
  }, [activeBlock, currentTime]);

  // ── 缩放 ──────────────────────────────────────────────────────────────
  const handleZoomIn  = useCallback(() => zoom < MAX_ZOOM_INDEX && onZoomChange?.(zoom + 1), [zoom, onZoomChange]);
  const handleZoomOut = useCallback(() => zoom > MIN_ZOOM_INDEX && onZoomChange?.(zoom - 1), [zoom, onZoomChange]);
  const handleZoomReset = useCallback(() => onZoomChange?.(0), [onZoomChange]);

  const handleWheel = useCallback((e) => {
    e.preventDefault();
    const container = scrollContainerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const mouseXRatio = (e.clientX - rect.left + container.scrollLeft) / container.scrollWidth;
    const zoomDelta = e.deltaY < 0 ? 1 : -1;
    const newZoom = Math.max(MIN_ZOOM_INDEX, Math.min(MAX_ZOOM_INDEX, zoom + zoomDelta));
    if (newZoom === zoom) return;
    const newDuration = ZOOM_LEVELS[newZoom].duration;
    const newScrollWidth = (MINUTES_PER_DAY / newDuration) * rect.width;
    const newScrollLeft = mouseXRatio * newScrollWidth - (e.clientX - rect.left);
    onZoomChange?.(newZoom);
    requestAnimationFrame(() => { container.scrollLeft = Math.max(0, newScrollLeft); });
  }, [zoom, onZoomChange]);

  // ── 拖拽 ──────────────────────────────────────────────────────────────
  const handleMouseDown = useCallback((e) => {
    if (e.button !== 0) return;
    isDragging.current = true;
    dragStartX.current = e.clientX;
    dragScrollLeft.current = scrollContainerRef.current?.scrollLeft || 0;
    document.body.style.cursor = 'grabbing';
    document.body.style.userSelect = 'none';
  }, []);

  const handleMouseMove = useCallback((e) => {
    if (!isDragging.current) return;
    const dx = e.clientX - dragStartX.current;
    const c = scrollContainerRef.current;
    if (c) c.scrollLeft = dragScrollLeft.current - dx;
  }, []);

  const handleMouseUp = useCallback(() => {
    isDragging.current = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }, []);

  useEffect(() => {
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  useEffect(() => {
    const c = scrollContainerRef.current;
    if (!c) return;
    c.addEventListener('wheel', handleWheel, { passive: false });
    return () => c.removeEventListener('wheel', handleWheel);
  }, [handleWheel]);

  // ── 鼠标悬停时间 ──────────────────────────────────────────────────────
  const handleTrackMouseMove = useCallback((e) => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const mouseX = e.clientX - rect.left + container.scrollLeft;
    const ratio = mouseX / container.scrollWidth;
    const totalMin = ratio * MINUTES_PER_DAY;
    const h = Math.floor(totalMin / 60);
    const m = Math.floor(totalMin % 60);
    const s = Math.floor((totalMin % 1) * 60);
    const t = dayjs().hour(h).minute(m).second(s);
    setHoverTime({ left: (totalMin / MINUTES_PER_DAY) * 100, label: t.format('HH:mm:ss'), x: e.clientX - rect.left });
  }, []);

  const handleTrackMouseLeave = useCallback(() => setHoverTime(null), []);

  // ── 点击 ──────────────────────────────────────────────────────────────
  const handleTrackClick = useCallback((e) => {
    if (isDragging.current) return;
    const container = scrollContainerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const mouseX = e.clientX - rect.left + container.scrollLeft;
    const minuteRatio = mouseX / container.scrollWidth;
    const clickMinute = minuteRatio * MINUTES_PER_DAY;
    const hit = segmentBlocks.find((b) => {
      const start = dayjs(b.start_time);
      const end = dayjs(b.end_time);
      const s = start.hour() * 60 + start.minute() + start.second() / 60;
      const e = end.hour() * 60 + end.minute() + end.second() / 60;
      return clickMinute >= s && clickMinute <= e;
    });
    if (hit) onSegmentClick?.(hit);
  }, [segmentBlocks, onSegmentClick]);

  // ── 渲染 ──────────────────────────────────────────────────────────────
  const showPlayhead = playheadInfo != null;

  return (
    <div className={styles.timelineWrapper}>
      {/* 头部：标题 + 缩放控件 */}
      <div className={styles.timelineHeader}>
        <span className={styles.timelineTitle}>{t('recording.playback.timeline')}</span>
        <div className={styles.timelineControls}>
          <div className={styles.controlGroup}>
            <Tooltip title={t('common.zoomOut')}>
              <button className={styles.zoomBtn} disabled={zoom <= MIN_ZOOM_INDEX} onClick={handleZoomOut}>
                <MinusOutlined />
              </button>
            </Tooltip>
            <span className={styles.zoomLabel}>{currentZoom.label}</span>
            <Tooltip title={t('common.zoomIn')}>
              <button className={styles.zoomBtn} disabled={zoom >= MAX_ZOOM_INDEX} onClick={handleZoomIn}>
                <PlusOutlined />
              </button>
            </Tooltip>
          </div>
          <Tooltip title={t('common.reset')}>
            <button className={styles.zoomBtn} disabled={zoom === 0} onClick={handleZoomReset}>
              <CompressOutlined />
            </button>
          </Tooltip>
        </div>
      </div>

      {/* 时间轴主体 */}
      <div className={styles.timelineBody}>
        {/* 刻度标签行 */}
        <div className={styles.tickRow}>
          {tickMarks
            .filter((t) => t.isLabel)
            .map((tick, idx) => (
              <span key={idx} className={styles.tickLabel} style={{ left: `${tick.left}%` }}>
                {tick.label}
              </span>
            ))}
        </div>

        {/* 可滚动时间轴轨道 */}
        <div
          ref={scrollContainerRef}
          className={styles.timelineScroll}
          onMouseDown={handleMouseDown}
          onMouseMove={handleTrackMouseMove}
          onMouseLeave={handleTrackMouseLeave}
          onClick={handleTrackClick}
        >
          <div className={styles.timelineTrackInner} style={{ width: `${zoomRatio * 100}%` }}>
            {/* 时刻度线 */}
            <div className={styles.tickLines}>
              {tickMarks.map((tick, idx) => (
                <div
                  key={idx}
                  className={`${styles.tickLine} ${tick.isLabel ? styles.tickLine_major : styles.tickLine_minor}`}
                  style={{ left: `${tick.left}%` }}
                />
              ))}
            </div>

            {/* 轨道背景 + 片段填充 */}
            <div className={styles.segmentTrack}>
              {segmentBlocks.map((seg) => {
                const modeCfg = MODE_CONFIG[seg.recording_mode] || MODE_CONFIG.continuous;
                const isActive = seg.id === activeSegmentId;
                return (
                  <Tooltip
                    key={seg.id}
                    title={`${dayjs(seg.start_time).format('HH:mm:ss')} - ${dayjs(seg.end_time).format('HH:mm:ss')} · ${t(modeCfg.labelKey)}`}
                    placement="top"
                  >
                    <div
                      className={styles.segmentFill}
                      style={{
                        left: `${seg.left}%`,
                        width: `${seg.width}%`,
                        background: modeCfg.color,
                        opacity: isActive ? 1 : 0.75,
                      }}
                      onClick={(e) => { e.stopPropagation(); onSegmentClick?.(seg); }}
                    />
                  </Tooltip>
                );
              })}

              {/* 播放指示线 */}
              {showPlayhead && (
                <div className={styles.playheadLine} style={{ left: `${playheadInfo.left}%` }}>
                  <div className={styles.playheadDot} />
                  <div className={styles.playheadBubble}>
                    {playheadInfo.label}
                  </div>
                </div>
              )}

              {/* 悬停指示线 */}
              {hoverTime && !isDragging.current && (
                <div className={styles.hoverLine} style={{ left: `${hoverTime.left}%` }}>
                  <span className={styles.hoverLabel} style={{ left: `${hoverTime.x}px` }}>
                    {hoverTime.label}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 底部时间范围 + 图例 */}
      <div className={styles.timelineFooter}>
        <span className={styles.footerTime}>
          {playheadInfo
            ? `${playheadInfo.timeStr}(设备录播)`
            : '00:00:00 - 24:00:00'}
        </span>
        <div className={styles.footerLegend}>
          {Object.entries(MODE_CONFIG).map(([mode, cfg]) => (
            <span key={mode} className={styles.legendItem}>
              <span className={styles.legendSwatch} style={{ background: cfg.color }} />
              {t(cfg.labelKey)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};

export default TimelineBar;
