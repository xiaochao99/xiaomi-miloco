import React, { useRef, useState, useCallback, useMemo, useEffect, useLayoutEffect } from 'react';
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
const MIN_VISIBLE_WIDTH_PX = 4; // 片段色块最小可见宽度，确保缩放后仍有基本可辨识度

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

// ── 工具函数 ──────────────────────────────────────────────────────────────

const dayjsToSeconds = (dt) =>
  dt.hour() * 3600 + dt.minute() * 60 + dt.second() + dt.millisecond() / 1000;

const getTickConfig = (zoomIndex) => {
  // 根据放大级别动态切换四种刻度精度：小时 / 30分钟 / 10分钟 / 1分钟
  // labelStepSeconds 与 stepSeconds 保持一致，确保放大后每个刻度都带时间标签
  if (zoomIndex <= 2) {
    // 24h, 12h, 6h -> 小时刻度
    return { stepSeconds: 3600, labelStepSeconds: 3600 };
  } else if (zoomIndex <= 5) {
    // 3h, 1.5h, 45m -> 30分钟刻度
    return { stepSeconds: 1800, labelStepSeconds: 1800 };
  } else if (zoomIndex <= 8) {
    // 30m, 15m, 7.5m -> 10分钟刻度
    return { stepSeconds: 600, labelStepSeconds: 600 };
  } else {
    // 3.75m 及以下 -> 1分钟刻度
    return { stepSeconds: 60, labelStepSeconds: 60 };
  }
};

/**
 * 将秒数格式化为时间字符串
 */
const formatTimeLabel = (seconds, showSeconds = false) => {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (showSeconds) return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
};

/**
 * TimelineBar – 专业录像时间轴
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

  // ── 拖拽/Seek 状态 ────────────────────────────────────────────────────
  const isSeeking = useRef(false);       // 拖拽跳转进度
  const seekStartSec = useRef(0);        // seek 起始秒数
  const seekTargetSec = useRef(0);       // seek 当前位置秒数
  const dragDistance = useRef(0);        // 拖拽距离（区分点击/拖拽）

  const [hoverTime, setHoverTime] = useState(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [hoveredTickIdx, setHoveredTickIdx] = useState(null);

  // ── 缩放锚点：预存鼠标命中的时间点，zoom 变化后在 effect 中居中 ──────
  const zoomAnchorSecRef = useRef(null);

  const currentZoom = ZOOM_LEVELS[zoom] || ZOOM_LEVELS[0];
  const viewSeconds = currentZoom.viewSeconds;
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

      let label = '';
      if (isLabel) {
        label = formatTimeLabel(rounded, viewSeconds <= 3600);
      }

      const s = Math.floor(rounded % 60);
      const m = Math.floor((rounded % 3600) / 60);
      let level = 'minor';
      if (s === 0 && m === 0) level = 'hour';
      else if (s === 0 && m % 30 === 0) level = 'halfHour';
      else if (s === 0 && m % 10 === 0) level = 'tenMinute';
      else if (s === 0) level = 'minute';

      marks.push({ left: (rounded / SECONDS_PER_DAY) * 100, isLabel, label, seconds: rounded, level });
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
    const contentWidth = containerWidth * zoomRatio;
    const availableForLabels = contentWidth * (spanSeconds / SECONDS_PER_DAY);
    const avgSpacingPx = availableForLabels / (labelTicks.length - 1);

    let strategy = 'all';
    if (avgSpacingPx < MIN_SPACING * 0.25) strategy = 'compact';
    else if (avgSpacingPx < MIN_SPACING * 0.5) strategy = 'hourOnly';
    else if (avgSpacingPx < MIN_SPACING) strategy = 'skip';

    return tickMarks.map((tick) => {
      if (!tick.isLabel) return { ...tick, hidden: false, displayLabel: '', showOnHover: false };
      const idx = labelTicks.findIndex((l) => Math.abs(l.seconds - tick.seconds) < 0.1);
      if (idx === -1) return { ...tick, hidden: false, displayLabel: tick.label, showOnHover: false };

      let hidden = false, displayLabel = tick.label, showOnHover = false;
      switch (strategy) {
        case 'skip':
          hidden = idx % 2 !== 0; showOnHover = hidden; break;
        case 'hourOnly':
          hidden = tick.seconds % 3600 > 0.1; showOnHover = hidden; break;
        case 'compact':
          if (tick.seconds % 3600 < 0.1) {
            hidden = false;
            displayLabel = `${String(Math.floor(tick.seconds / 3600)).padStart(2, '0')}:00`;
          } else { hidden = true; showOnHover = true; }
          break;
        default: break;
      }
      return { ...tick, hidden, displayLabel, showOnHover, strategy };
    });
  }, [tickMarks, containerWidth, zoomRatio]);

  // ── 片段块数据 ───────────────────────────────────────────────────────
  const segmentBlocks = useMemo(() => {
    if (!segments.length) return [];
    const trackInnerPx = containerWidth * zoomRatio;

    const blocks = segments
      .map((seg) => {
        const startSec = dayjsToSeconds(dayjs(seg.start_time));
        // 优先使用后端返回的 duration_seconds 计算宽度，确保与播放器时长一致
        let durationSec;
        if (typeof seg.duration_seconds === 'number' && seg.duration_seconds > 0) {
          durationSec = seg.duration_seconds;
        } else if (seg.file_size_bytes > 0) {
          // 文件大小估算兜底：150KB/s 码率
          durationSec = Math.max(1, Math.round(seg.file_size_bytes / (150 * 1024)));
        } else {
          durationSec = Math.max(0, dayjsToSeconds(dayjs(seg.end_time)) - startSec);
        }
        const endSec = startSec + durationSec;
        const rawLeft = (startSec / SECONDS_PER_DAY) * 100;
        const rawWidth = (durationSec / SECONDS_PER_DAY) * 100;

        // 默认使用真实宽度
        // 仅在放大级别足够高（zoom > 2）且真实像素宽度不足 MIN_VISIBLE_WIDTH_PX 时做最小保护
        // 低 zoom 级别下保持真实比例，让用户看到时段分布
        const realWidthPx = trackInnerPx > 0 ? (rawWidth / 100) * trackInnerPx : 0;
        let displayWidth = rawWidth;
        let adjustedLeft = rawLeft;
        const shouldEnforceMinWidth = zoom > 2; // 仅在高 zoom（< 6h 视图）时强制最小宽度
        if (shouldEnforceMinWidth && realWidthPx > 0 && realWidthPx < MIN_VISIBLE_WIDTH_PX) {
          const minPct = trackInnerPx > 0 ? (MIN_VISIBLE_WIDTH_PX / trackInnerPx) * 100 : 0;
          displayWidth = Math.max(rawWidth, minPct);
          adjustedLeft = Math.max(0, rawLeft - (displayWidth - rawWidth) / 2);
        }

        return {
          ...seg,
          left: adjustedLeft,
          width: displayWidth,
          startSec,
          endSec,
          durationSec,
          rawWidth,
          realWidthPx,
          isClamped: realWidthPx > 0 && realWidthPx < MIN_VISIBLE_WIDTH_PX,
        };
      })
      .filter((b) => b.durationSec > 0);

    // DEBUG: 输出前5个片段的宽度计算详情
    if (blocks.length > 0) {
      console.group('[DEBUG TimelineBar] segmentBlocks widths');
      console.log('containerWidth:', containerWidth, 'zoom:', zoom, 'zoomRatio:', zoomRatio, 'trackInnerPx:', trackInnerPx);
      blocks.slice(0, 5).forEach((b, i) => {
        console.log(`[${i}] dur=${b.durationSec}s rawWidth=${b.rawWidth.toFixed(4)}% displayWidth=${b.width.toFixed(4)}% realPx=${b.realWidthPx?.toFixed(1)}px clamped=${b.isClamped}`, {
          start_time: b.start_time,
          duration_seconds: b.duration_seconds,
        });
      });
      console.groupEnd();
    }

    return blocks;
  }, [segments, containerWidth, zoomRatio, zoom]);

  // ── 播放指示线 ────────────────────────────────────────────────────────
  const playheadInfo = useMemo(() => {
    if (globalTime <= 0 && !activeSegment) return null;
    const left = (globalTime / SECONDS_PER_DAY) * 100;
    const dateStr = selectedDate ? selectedDate.format('YYYY-MM-DD') : dayjs().format('YYYY-MM-DD');
    const dateTime = `${dateStr} ${formatTimeLabel(globalTime, true)}`;
    return { left, timeStr: dateTime, label: formatTimeLabel(globalTime, viewSeconds <= 3600) };
  }, [globalTime, selectedDate, viewSeconds, activeSegment]);

  // ── 活跃片段位置缓存 ──────────────────────────────────────────────────
  const activeBlockInfo = useMemo(() => {
    if (!activeSegmentId || !segmentBlocks.length) return null;
    const ab = segmentBlocks.find((b) => b.id === activeSegmentId);
    return ab ? { startSec: ab.startSec, endSec: ab.endSec } : null;
  }, [activeSegmentId, segmentBlocks]);

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

  // ── 鼠标滚轮缩放（以鼠标位置为中心） ────────────────────────────────
  const handleWheel = useCallback(
    (e) => {
      e.preventDefault();
      const container = scrollContainerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();

      // 预存鼠标对应的内容时间点（秒）
      const mouseX = e.clientX - rect.left + container.scrollLeft;
      const contentWidth = container.scrollWidth;
      const anchorSec = (mouseX / contentWidth) * SECONDS_PER_DAY;

      const delta = e.deltaY < 0 ? 1 : -1;
      const next = Math.max(MIN_ZOOM_INDEX, Math.min(MAX_ZOOM_INDEX, zoom + delta));
      if (next === zoom) return;

      // 保存锚点时间和鼠标在 viewport 中的位置
      zoomAnchorSecRef.current = { sec: anchorSec, mouseViewportX: e.clientX - rect.left };
      onZoomChange?.(next);
    },
    [zoom, onZoomChange],
  );

  /**
   * 缩放后重新定位滚动，使锚点时间保持在鼠标位置
   * 用 useLayoutEffect 在 DOM 更新后、浏览器绘制前同步执行
   */
  useLayoutEffect(() => {
    const anchor = zoomAnchorSecRef.current;
    if (!anchor) return;
    zoomAnchorSecRef.current = null;

    const container = scrollContainerRef.current;
    if (!container) return;

    // 使用实际 scrollWidth 而非手动计算，更准确
    const contentWidth = container.scrollWidth;
    // 锚点时间在内容中的像素位置
    const anchorPx = (anchor.sec / SECONDS_PER_DAY) * contentWidth;
    // 令锚点像素位置对齐鼠标在视口中的位置
    container.scrollLeft = Math.max(0, anchorPx - anchor.mouseViewportX);
  }, [zoom]);

  // ── 坐标换算工具 ──────────────────────────────────────────────────────
  const mouseXToGlobalSec = useCallback((e) => {
    const container = scrollContainerRef.current;
    if (!container) return 0;
    const rect = container.getBoundingClientRect();
    const mouseX = e.clientX - rect.left + container.scrollLeft;
    return (mouseX / container.scrollWidth) * SECONDS_PER_DAY;
  }, []);

  const globalSecToMouseX = useCallback((sec) => {
    const container = scrollContainerRef.current;
    if (!container) return 0;
    const rect = container.getBoundingClientRect();
    return (sec / SECONDS_PER_DAY) * container.scrollWidth - container.scrollLeft + rect.left;
  }, []);

  // ── 判断时间是否在某个片段范围内 ──────────────────────────────────────
  const findSegmentAt = useCallback((sec) => {
    return segmentBlocks.find((b) => sec >= b.startSec && sec <= b.endSec) || null;
  }, [segmentBlocks]);

  // ── 轨道处理事件 ──────────────────────────────────────────────────────
  const handleTrackMouseDown = useCallback(
    (e) => {
      if (e.button !== 0) return;
      const clickSec = mouseXToGlobalSec(e);

      // 点击/拖拽时间轴任意位置均触发 seek
      isSeeking.current = true;
      seekStartSec.current = clickSec;
      seekTargetSec.current = clickSec;
      dragDistance.current = 0;
      document.body.style.userSelect = 'none';
    },
    [mouseXToGlobalSec],
  );

  const handleTrackMouseMoveGlobal = useCallback(
    (e) => {
      if (!isSeeking.current) return;

      // ── 拖拽 seek：实时更新 seek 目标时间 ──
      const curSec = mouseXToGlobalSec(e);

      // 限制在当前活跃片段范围内（如果有的话）
      if (activeBlockInfo) {
        seekTargetSec.current = Math.max(
          activeBlockInfo.startSec,
          Math.min(activeBlockInfo.endSec, curSec),
        );
      } else {
        seekTargetSec.current = curSec;
      }

      // 更新悬停线（显示 seek 预览）
      const container = scrollContainerRef.current;
      if (container) {
        const rect = container.getBoundingClientRect();
        setHoverTime({
          left: (seekTargetSec.current / SECONDS_PER_DAY) * 100,
          label: formatTimeLabel(seekTargetSec.current, viewSeconds <= 3600),
          x: e.clientX - rect.left,
          isOverActive: true,
          isSeeking: true,
        });
      }
      dragDistance.current += Math.abs(e.movementX || 0);
    },
    [mouseXToGlobalSec, activeBlockInfo, viewSeconds],
  );

  const handleTrackMouseUp = useCallback(
    (e) => {
      if (!isSeeking.current) {
        document.body.style.userSelect = '';
        return;
      }

      // ── seek 完成 ──
      const targetSec = seekTargetSec.current;
      const isClick = dragDistance.current < 3;

      if (isClick) {
        // 点击：检查是否命中了某个片段
        const hit = findSegmentAt(targetSec);
        if (hit && hit.id !== activeSegmentId) {
          // 切换到新片段
          onSegmentClick?.(hit);
        } else if (onSeek) {
          // 同一片段或无片段，执行 seek
          onSeek(targetSec);
        }
      } else {
        // 拖拽：始终执行 seek
        if (onSeek) onSeek(targetSec);
      }

      isSeeking.current = false;
      seekTargetSec.current = 0;
      setHoverTime(null);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    },
    [findSegmentAt, activeSegmentId, onSeek, onSegmentClick],
  );

  // ── 注册全局鼠标事件 ─────────────────────────────────────────────────
  useEffect(() => {
    document.addEventListener('mousemove', handleTrackMouseMoveGlobal);
    document.addEventListener('mouseup', handleTrackMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleTrackMouseMoveGlobal);
      document.removeEventListener('mouseup', handleTrackMouseUp);
    };
  }, [handleTrackMouseMoveGlobal, handleTrackMouseUp]);

  useEffect(() => {
    const c = scrollContainerRef.current;
    if (!c) return;
    c.addEventListener('wheel', handleWheel, { passive: false });
    return () => c.removeEventListener('wheel', handleWheel);
  }, [handleWheel]);

  // ── 鼠标悬停时间 ──────────────────────────────────────────────────────
  const handleTrackHover = useCallback(
    (e) => {
      if (isSeeking.current) return;
      const totalSec = mouseXToGlobalSec(e);
      const container = scrollContainerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();

      const isOverActive = activeBlockInfo
        ? totalSec >= activeBlockInfo.startSec && totalSec <= activeBlockInfo.endSec
        : false;

      // 检查是否在任意片段范围内（用于显示 seek 提示）
      const isOverAnySegment = findSegmentAt(totalSec) !== null;

      setHoverTime({
        left: (totalSec / SECONDS_PER_DAY) * 100,
        label: formatTimeLabel(totalSec, viewSeconds <= 3600),
        x: e.clientX - rect.left,
        isOverActive,
        isOverAnySegment,
        isSeeking: false,
      });
    },
    [mouseXToGlobalSec, activeBlockInfo, viewSeconds, findSegmentAt],
  );

  const handleTrackMouseLeave = useCallback(() => {
    if (!isSeeking.current) {
      setHoverTime(null);
    }
  }, []);

  // ── 渲染辅助 ──────────────────────────────────────────────────────────
  const getTickLineClass = (level) => {
    const map = {
      hour: styles.tickLine_hour, halfHour: styles.tickLine_halfHour,
      tenMinute: styles.tickLine_tenMinute, quarter: styles.tickLine_quarter,
      fiveMinute: styles.tickLine_fiveMinute, minute: styles.tickLine_minute,
      minor: styles.tickLine_minor,
    };
    return `${styles.tickLine} ${map[level] || styles.tickLine_minor}`;
  };

  const showPlayhead = playheadInfo != null;

  return (
    <div className={styles.timelineWrapper}>
      {/* ── 头部 ── */}
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

      {/* ── 时间轴主体 ── */}
      <div className={styles.timelineBody}>
        <div
          ref={scrollContainerRef}
          className={styles.timelineScroll}
          onMouseDown={handleTrackMouseDown}
          onMouseMove={handleTrackHover}
          onMouseLeave={handleTrackMouseLeave}
        >
          {/* 内部轨道 */}
          <div className={styles.timelineTrackInner} style={{ width: `${zoomRatio * 100}%` }}>
            {/* 刻度标签行 */}
            <div className={styles.tickRow}>
              {visibleTickLabels
                .filter((tk) => tk.isLabel)
                .map((tick) => (
                  <span
                    key={`lbl-${tick.seconds}`}
                    className={`${styles.tickLabel} ${
                      tick.hidden ? styles.tickLabelHidden : ''
                    } ${
                      tick.showOnHover && hoveredTickIdx === `lbl-${tick.seconds}` ? styles.tickLabelHovered : ''
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

            {/* 刻度竖线 */}
            <div className={styles.tickLines}>
              {tickMarks.map((tick) => (
                <div
                  key={`line-${tick.seconds}`}
                  className={getTickLineClass(tick.level)}
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
                    title={`${dayjs(seg.start_time).format('HH:mm:ss')} - ${dayjs(seg.end_time).format('HH:mm:ss')} · ${t(modeCfg.labelKey)} · ${t('recording.playback.clickToSeek')}`}
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

              {/* 悬停/Seek 指示线 */}
              {hoverTime && (isSeeking.current === hoverTime.isSeeking) && (
                <div
                  className={`${styles.hoverLine} ${
                    hoverTime.isSeeking ? styles.hoverLineSeeking : ''
                  } ${
                    hoverTime.isOverAnySegment ? styles.hoverLineSeekable : ''
                  }`}
                  style={{ left: `${hoverTime.left}%` }}
                >
                  <span className={styles.hoverLabel}>
                    {hoverTime.label}
                    {(hoverTime.isOverAnySegment || hoverTime.isSeeking) && (
                      <span className={styles.seekHint}>
                        {' '}· {hoverTime.isSeeking ? t('recording.playback.seeking') : t('recording.playback.clickToSeek')}
                      </span>
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
