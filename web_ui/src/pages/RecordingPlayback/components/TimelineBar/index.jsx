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

const SECONDS_PER_DAY = 24 * 60 * 60;

/**
 * 缩放级别配置
 * viewSeconds: 当前视窗展示的总时间（秒）
 */
const ZOOM_LEVELS = [
  { viewSeconds: 86400, label: '24h' },
  { viewSeconds: 43200, label: '12h' },
  { viewSeconds: 21600, label: '6h' },
  { viewSeconds: 10800, label: '3h' },
  { viewSeconds: 5400,  label: '1.5h' },
  { viewSeconds: 2700,  label: '45m' },
  { viewSeconds: 1800,  label: '30m' },
  { viewSeconds: 900,   label: '15m' },
  { viewSeconds: 450,   label: '7.5m' },
  { viewSeconds: 225,   label: '3.75m' },
  { viewSeconds: 120,   label: '2m' },
  { viewSeconds: 60,    label: '1m' },
  { viewSeconds: 30,    label: '30s' },
  { viewSeconds: 15,    label: '15s' },
];

const MIN_ZOOM_INDEX = 0;
const MAX_ZOOM_INDEX = ZOOM_LEVELS.length - 1;

const MODE_CONFIG = {
  continuous: { color: '#4096ff', labelKey: 'recording.playback.triggerContinuous' },
  person:    { color: '#73d13d', labelKey: 'recording.playback.triggerPerson' },
  motion:    { color: '#ffc53d', labelKey: 'recording.playback.triggerMotion' },
};

/**
 * 将 dayjs 时间转换为当天秒数
 */
const dayjsToSeconds = (dt) => {
  return dt.hour() * 3600 + dt.minute() * 60 + dt.second() + dt.millisecond() / 1000;
};

/**
 * 根据缩放级别决定刻度配置
 * stepSeconds: 小刻度间距（秒）
 * labelStepSeconds: 带标签的大刻度间距（秒）
 */
const getTickConfig = (zoomIndex) => {
  const configs = [
    { stepSeconds: 3600,  labelStepSeconds: 7200 },   // 24h: 每小时小刻度, 每2h标签
    { stepSeconds: 1800,  labelStepSeconds: 7200 },   // 12h
    { stepSeconds: 900,   labelStepSeconds: 3600 },   // 6h
    { stepSeconds: 600,   labelStepSeconds: 3600 },   // 3h
    { stepSeconds: 300,   labelStepSeconds: 1800 },   // 1.5h
    { stepSeconds: 120,   labelStepSeconds: 600 },    // 45m
    { stepSeconds: 60,    labelStepSeconds: 300 },    // 30m
    { stepSeconds: 30,    labelStepSeconds: 300 },    // 15m
    { stepSeconds: 30,    labelStepSeconds: 120 },    // 7.5m
    { stepSeconds: 15,    labelStepSeconds: 60 },     // 3.75m
    { stepSeconds: 10,    labelStepSeconds: 60 },     // 2m
    { stepSeconds: 5,     labelStepSeconds: 30 },     // 1m
    { stepSeconds: 2,     labelStepSeconds: 10 },     // 30s
    { stepSeconds: 1,     labelStepSeconds: 5 },      // 15s
  ];
  return configs[Math.min(zoomIndex, configs.length - 1)];
};

/**
 * TimelineBar – 专业录像时间轴
 *
 * Props:
 *   segments        : RecordingSegment[]   所有录像片段
 *   activeSegmentId : string | null        当前激活片段 ID
 *   activeSegment   : RecordingSegment | null
 *   globalTime      : number               全局播放时间（当天秒数，从 00:00:00 开始计算）
 *   selectedDate    : dayjs                 选中的日期
 *   zoom            : number (0-13)
 *   onZoomChange    : (zoomIndex: number) => void
 *   onSegmentClick  : (segment: RecordingSegment) => void
 *   onSeek          : (globalTimeInSeconds: number) => void   seek 到全局时间（当天秒数）
 */
const TimelineBar = ({
  segments = [],
  activeSegmentId,
  activeSegment,
  globalTime = 0,
  selectedDate,
  zoom = 0,
  onZoomChange,
  onSegmentClick,
  onSeek,
}) => {
  const { t } = useTranslation();
  const scrollContainerRef = useRef(null);
  const isDragging = useRef(false);
  const dragStartX = useRef(0);
  const dragScrollLeft = useRef(0);
  const [hoverTime, setHoverTime] = useState(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [hoveredTickIdx, setHoveredTickIdx] = useState(null);

  const currentZoom = ZOOM_LEVELS[zoom] || ZOOM_LEVELS[0];
  const viewSeconds = currentZoom.viewSeconds;
  // zoomRatio: 全天秒数 / 当前视窗秒数，用于撑开内部轨道
  const zoomRatio = SECONDS_PER_DAY / viewSeconds;

  // ── 容器宽度监听 ─────────────────────────────────────────────────────
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const update = () => setContainerWidth(container.clientWidth);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(container);
    return () => ro.disconnect();
  }, []);

  // ── 刻度生成 ─────────────────────────────────────────────────────────
  const tickConfig = useMemo(() => getTickConfig(zoom), [zoom]);

  const tickMarks = useMemo(() => {
    const marks = [];
    const { stepSeconds, labelStepSeconds } = tickConfig;
    for (let sec = 0; sec <= SECONDS_PER_DAY; sec += stepSeconds) {
      const rounded = Math.round(sec * 100) / 100;
      if (rounded > SECONDS_PER_DAY + 0.1) break;

      const isLabel = Math.abs(rounded % labelStepSeconds) < 0.1 || rounded < 0.1;
      const h = Math.floor(rounded / 3600);
      const m = Math.floor((rounded % 3600) / 60);
      const s = Math.floor(rounded % 60);

      let label = '';
      if (isLabel) {
        if (viewSeconds <= 3600) {
          // 高缩放级别：显示 HH:mm:ss
          label = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
        } else {
          label = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
        }
      }

      // 刻度级别
      let level = 'minor';
      if (s === 0 && m === 0) level = 'hour';
      else if (s === 0 && m % 30 === 0) level = 'halfHour';
      else if (s === 0 && m % 15 === 0) level = 'quarter';
      else if (s === 0 && m % 5 === 0) level = 'fiveMinute';
      else if (s === 0) level = 'minute';

      marks.push({
        left: (rounded / SECONDS_PER_DAY) * 100,
        isLabel,
        label,
        seconds: rounded,
        level,
      });
    }
    return marks;
  }, [tickConfig, viewSeconds]);

  // ── 智能标签防重叠 ──────────────────────────────────────────────────
  const visibleTickLabels = useMemo(() => {
    if (!containerWidth || tickMarks.length === 0) return tickMarks;

    const labelTicks = tickMarks.filter((tk) => tk.isLabel);
    if (labelTicks.length <= 1) return tickMarks;

    const LABEL_WIDTH = 50;
    const SAFE_GAP = 8;
    const MIN_SPACING = LABEL_WIDTH + SAFE_GAP;

    const first = labelTicks[0];
    const last = labelTicks[labelTicks.length - 1];
    const spanSeconds = last.seconds - first.seconds;
    const availableForLabels = containerWidth * (spanSeconds / SECONDS_PER_DAY);
    const avgSpacingPx = availableForLabels / (labelTicks.length - 1);

    let strategy = 'all';
    if (avgSpacingPx < MIN_SPACING * 0.18) strategy = 'compact';
    else if (avgSpacingPx < MIN_SPACING * 0.35) strategy = 'compact';
    else if (avgSpacingPx < MIN_SPACING * 0.6) strategy = 'hourOnly';
    else if (avgSpacingPx < MIN_SPACING) strategy = 'skip';

    return tickMarks.map((tick) => {
      if (!tick.isLabel) return { ...tick, hidden: false, displayLabel: '', showOnHover: false };

      const idx = labelTicks.findIndex((l) => Math.abs(l.seconds - tick.seconds) < 0.1);
      if (idx === -1) return { ...tick, hidden: false, displayLabel: tick.label, showOnHover: false };

      let hidden = false;
      let displayLabel = tick.label;
      let showOnHover = false;

      switch (strategy) {
        case 'skip':
          hidden = idx % 2 !== 0;
          showOnHover = hidden;
          break;
        case 'hourOnly':
          hidden = tick.seconds % 3600 > 0.1;
          showOnHover = hidden;
          break;
        case 'compact':
          if (tick.seconds % 3600 < 0.1) {
            hidden = false;
            const h = Math.floor(tick.seconds / 3600);
            displayLabel = `${String(h).padStart(2, '0')}:00`;
          } else {
            hidden = true;
            showOnHover = true;
          }
          break;
        default:
          break;
      }

      return { ...tick, hidden, displayLabel, showOnHover, strategy };
    });
  }, [tickMarks, containerWidth]);

  // ── 片段数据（严格按实际时间对齐） ───────────────────────────────────
  const segmentBlocks = useMemo(() => {
    if (!segments.length) return [];
    return segments
      .map((seg) => {
        const start = dayjs(seg.start_time);
        const end = dayjs(seg.end_time);
        // 当天秒数（从 00:00:00 开始）
        const startSec = dayjsToSeconds(start);
        const endSec = dayjsToSeconds(end);
        const left = (startSec / SECONDS_PER_DAY) * 100;
        // 严格按实际时间长度计算宽度，不做强制最小宽度限制，确保比例准确
        const widthPercent = ((endSec - startSec) / SECONDS_PER_DAY) * 100;
        return {
          ...seg,
          left,
          width: widthPercent,
          startSec,
          endSec,
        };
      })
      .filter((b) => b.width > 0);
  }, [segments, zoomRatio]);

  // ── 播放指示线 ────────────────────────────────────────────────────────
  const playheadInfo = useMemo(() => {
    if (globalTime <= 0 && !activeSegment) return null;

    // 使用全局时间（当天秒数）
    const minute = globalTime / 60;
    const left = (globalTime / SECONDS_PER_DAY) * 100;

    const h = Math.floor(globalTime / 3600);
    const m = Math.floor((globalTime % 3600) / 60);
    const s = Math.floor(globalTime % 60);
    const ms = Math.floor((globalTime % 1) * 1000);
    const dateStr = selectedDate ? selectedDate.format('YYYY-MM-DD') : dayjs().format('YYYY-MM-DD');
    const timeStr = `${dateStr} ${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;

    let timeFormat;
    if (viewSeconds <= 3600) {
      timeFormat = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    } else {
      timeFormat = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
    }

    return { left, timeStr, label: timeFormat };
  }, [globalTime, selectedDate, viewSeconds, activeSegment]);

  // ── 缩放操作 ──────────────────────────────────────────────────────────
  const handleZoomIn = useCallback(
    () => zoom < MAX_ZOOM_INDEX && onZoomChange?.(zoom + 1),
    [zoom, onZoomChange],
  );
  const handleZoomOut = useCallback(
    () => zoom > MIN_ZOOM_INDEX && onZoomChange?.(zoom - 1),
    [zoom, onZoomChange],
  );
  const handleZoomReset = useCallback(() => onZoomChange?.(0), [onZoomChange]);

  // 鼠标滚轮缩放（以鼠标位置为锚点）
  const handleWheel = useCallback(
    (e) => {
      e.preventDefault();
      const container = scrollContainerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      const mouseXRatio = (e.clientX - rect.left + container.scrollLeft) / container.scrollWidth;
      const delta = e.deltaY < 0 ? 1 : -1;
      const next = Math.max(MIN_ZOOM_INDEX, Math.min(MAX_ZOOM_INDEX, zoom + delta));
      if (next === zoom) return;

      const newViewSeconds = ZOOM_LEVELS[next].viewSeconds;
      const newScrollWidth = (SECONDS_PER_DAY / newViewSeconds) * rect.width;
      const newScrollLeft = mouseXRatio * newScrollWidth - (e.clientX - rect.left);

      onZoomChange?.(next);
      requestAnimationFrame(() => {
        container.scrollLeft = Math.max(0, newScrollLeft);
      });
    },
    [zoom, onZoomChange],
  );

  // ── 拖拽平移 ──────────────────────────────────────────────────────────
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
    if (!isDragging.current) return;
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
  const handleTrackMouseMove = useCallback(
    (e) => {
      const container = scrollContainerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      const mouseX = e.clientX - rect.left + container.scrollLeft;
      const ratio = mouseX / container.scrollWidth;
      const totalSec = ratio * SECONDS_PER_DAY;
      const h = Math.floor(totalSec / 3600);
      const m = Math.floor((totalSec % 3600) / 60);
      const s = Math.floor(totalSec % 60);

      let timeFormat;
      if (viewSeconds <= 3600) {
        timeFormat = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
      } else {
        timeFormat = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
      }

      // 判断鼠标是否在某个活跃片段上
      let isOverActive = false;
      if (activeSegmentId) {
        const ab = segmentBlocks.find((b) => b.id === activeSegmentId);
        if (ab) {
          isOverActive = totalSec >= ab.startSec && totalSec <= ab.endSec;
        }
      }

      setHoverTime({
        left: (totalSec / SECONDS_PER_DAY) * 100,
        label: timeFormat,
        x: e.clientX - rect.left,
        isOverActive,
      });
    },
    [activeSegmentId, segmentBlocks, viewSeconds],
  );

  const handleTrackMouseLeave = useCallback(() => setHoverTime(null), []);

  // ── 点击定位 ──────────────────────────────────────────────────────────
  const handleTrackClick = useCallback(
    (e) => {
      if (isDragging.current) return;
      const container = scrollContainerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      const mouseX = e.clientX - rect.left + container.scrollLeft;
      const ratio = mouseX / container.scrollWidth;
      const clickSec = ratio * SECONDS_PER_DAY;

      // 查找点击命中的片段
      const hit = segmentBlocks.find(
        (b) => clickSec >= b.startSec && clickSec <= b.endSec,
      );

      if (hit) {
        if (hit.id === activeSegmentId && onSeek) {
          // 已在播放该片段 → seek 到全局时间
          onSeek(clickSec);
        } else {
          onSegmentClick?.(hit);
        }
      }
    },
    [segmentBlocks, activeSegmentId, onSegmentClick, onSeek],
  );

  // ── 渲染 ──────────────────────────────────────────────────────────────
  const showPlayhead = playheadInfo != null;

  const getTickLineClass = (level) => {
    switch (level) {
      case 'hour':       return `${styles.tickLine} ${styles.tickLine_hour}`;
      case 'halfHour':   return `${styles.tickLine} ${styles.tickLine_halfHour}`;
      case 'quarter':    return `${styles.tickLine} ${styles.tickLine_quarter}`;
      case 'fiveMinute': return `${styles.tickLine} ${styles.tickLine_fiveMinute}`;
      case 'minute':     return `${styles.tickLine} ${styles.tickLine_minute}`;
      default:           return `${styles.tickLine} ${styles.tickLine_minor}`;
    }
  };

  return (
    <div className={styles.timelineWrapper}>
      {/* ── 头部：标题 + 缩放控件 ── */}
      <div className={styles.timelineHeader}>
        <span className={styles.timelineTitle}>{t('recording.playback.timeline')}</span>
        <div className={styles.timelineControls}>
          <div className={styles.controlGroup}>
            <Tooltip title={t('common.zoomOut')}>
              <button
                className={styles.zoomBtn}
                disabled={zoom <= MIN_ZOOM_INDEX}
                onClick={handleZoomOut}
              >
                <MinusOutlined />
              </button>
            </Tooltip>
            <span className={styles.zoomLabel}>{currentZoom.label}</span>
            <Tooltip title={t('common.zoomIn')}>
              <button
                className={styles.zoomBtn}
                disabled={zoom >= MAX_ZOOM_INDEX}
                onClick={handleZoomIn}
              >
                <PlusOutlined />
              </button>
            </Tooltip>
          </div>
          <Tooltip title={t('common.reset')}>
            <button
              className={styles.zoomBtn}
              disabled={zoom === 0}
              onClick={handleZoomReset}
            >
              <CompressOutlined />
            </button>
          </Tooltip>
        </div>
      </div>

      {/* ── 时间轴主体 ── */}
      <div className={styles.timelineBody}>
        <div
          ref={scrollContainerRef}
          className={styles.timelineScroll}
          onMouseDown={handleMouseDown}
          onMouseMove={handleTrackMouseMove}
          onMouseLeave={handleTrackMouseLeave}
          onClick={handleTrackClick}
        >
          {/* 内部轨道：宽度 = zoomRatio * 100% */}
          <div
            className={styles.timelineTrackInner}
            style={{ width: `${zoomRatio * 100}%` }}
          >
            {/* ── 刻度标签行 ── */}
            <div className={styles.tickRow}>
              {visibleTickLabels
                .filter((tk) => tk.isLabel)
                .map((tick) => (
                  <span
                    key={`lbl-${tick.seconds}`}
                  className={`${styles.tickLabel} ${
                    tick.hidden ? styles.tickLabelHidden : ''
                  } ${
                    tick.showOnHover && hoveredTickIdx === `lbl-${tick.seconds}`
                      ? styles.tickLabelHovered
                      : ''
                  }`}
                    style={{ left: `${tick.left}%` }}
                    onMouseEnter={() => setHoveredTickIdx(`lbl-${tick.seconds}`)}
                    onMouseLeave={() => setHoveredTickIdx(null)}
                  >
                    {tick.displayLabel || tick.label}
                    {tick.showOnHover && hoveredTickIdx !== `lbl-${tick.seconds}` && (
                      <span className={styles.tickLabelDots}>···</span>
                    )}
                  </span>
                ))}
            </div>

            {/* ── 刻度竖线 ── */}
            <div className={styles.tickLines}>
              {tickMarks.map((tick) => (
                <div
                  key={`line-${tick.seconds}`}
                  className={getTickLineClass(tick.level)}
                  style={{ left: `${tick.left}%` }}
                />
              ))}
            </div>

            {/* ── 轨道背景 + 片段填充 ── */}
            <div className={styles.segmentTrack}>
              {segmentBlocks.map((seg) => {
                const modeCfg = MODE_CONFIG[seg.recording_mode] || MODE_CONFIG.continuous;
                const isActive = seg.id === activeSegmentId;
                return (
                  <Tooltip
                    key={seg.id}
                    title={`${dayjs(seg.start_time).format('HH:mm:ss')} - ${dayjs(seg.end_time).format('HH:mm:ss')} · ${t(modeCfg.labelKey)}${isActive ? ` · ${t('recording.playback.clickToSeek')}` : ''}`}
                    placement="top"
                  >
                    <div
                      className={`${styles.segmentFill} ${isActive ? styles.segmentFillActive : ''}`}
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
                  <div className={styles.playheadBubble}>{playheadInfo.label}</div>
                </div>
              )}

              {/* 悬停指示线 */}
              {hoverTime && !isDragging.current && (
                <div
                  className={`${styles.hoverLine} ${hoverTime.isOverActive ? styles.hoverLineSeekable : ''}`}
                  style={{ left: `${hoverTime.left}%` }}
                >
                  <span className={styles.hoverLabel} style={{ left: `${hoverTime.x}px` }}>
                    {hoverTime.label}
                    {hoverTime.isOverActive && (
                      <span className={styles.seekHint}> · {t('recording.playback.clickToSeek')}</span>
                    )}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── 底部信息 ── */}
      <div className={styles.timelineFooter}>
        <span className={styles.footerTime}>
          {playheadInfo
            ? `${playheadInfo.timeStr} (${t('recording.playback.deviceRecording')})`
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
