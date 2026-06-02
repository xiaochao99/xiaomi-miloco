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
const MIN_VISIBLE_WIDTH_PX = 4;
const MERGE_GAP_THRESHOLD = 2; // 融合阈值：相邻片段间隔 ≤ 2 秒时合并为一个色块

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

// ═══════════════════════════════════════════════════════════════════════════
// 工具函数
// ═══════════════════════════════════════════════════════════════════════════

const dayjsToSeconds = (dt) =>
  dt.hour() * 3600 + dt.minute() * 60 + dt.second() + dt.millisecond() / 1000;

const getTickConfig = (zoomIndex) => {
  if (zoomIndex <= 2) return { stepSeconds: 3600, labelStepSeconds: 3600 };
  if (zoomIndex <= 5) return { stepSeconds: 1800, labelStepSeconds: 1800 };
  if (zoomIndex <= 8) return { stepSeconds: 600, labelStepSeconds: 600 };
  return { stepSeconds: 60, labelStepSeconds: 60 };
};

const formatTimeLabel = (seconds, showSeconds = false) => {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (showSeconds) return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
};

const getTickLevel = (rounded) => {
  const s = Math.floor(rounded % 60);
  const m = Math.floor((rounded % 3600) / 60);
  if (s === 0 && m === 0) return 'hour';
  if (s === 0 && m % 30 === 0) return 'halfHour';
  if (s === 0 && m % 10 === 0) return 'tenMinute';
  if (s === 0) return 'minute';
  return 'minor';
};

const generateTickMarks = (tickConfig) => {
  const { stepSeconds, labelStepSeconds } = tickConfig;
  const marks = [];
  for (let sec = 0; sec <= SECONDS_PER_DAY; sec += stepSeconds) {
    const rounded = Math.round(sec * 100) / 100;
    if (rounded > SECONDS_PER_DAY + 0.1) break;
    const isLabel = Math.abs(rounded % labelStepSeconds) < 0.1 || rounded < 0.1;
    marks.push({
      left: (rounded / SECONDS_PER_DAY) * 100,
      isLabel,
      label: isLabel ? formatTimeLabel(rounded) : '',
      seconds: rounded,
      level: getTickLevel(rounded),
    });
  }
  return marks;
};

/**
 * 将相邻的色块融合：若两个相邻 blocks 之间的间隔 ≤ MERGE_GAP_THRESHOLD 秒，
 * 则合并为一个 block（保留左侧的 start_time，合并总宽度）。
 */
const mergeAdjacentBlocks = (blocks) => {
  if (blocks.length < 2) return blocks;
  // blocks 已按 startSec 排序
  const merged = [blocks[0]];
  for (let i = 1; i < blocks.length; i++) {
    const prev = merged[merged.length - 1];
    const curr = blocks[i];
    const gap = curr.startSec - prev.endSec;
    if (gap <= MERGE_GAP_THRESHOLD) {
      // 融合：扩展 prev 的右边界
      const newEndSec = curr.endSec;
      const newDurationSec = newEndSec - prev.startSec;
      const newWidth = (newDurationSec / SECONDS_PER_DAY) * 100;
      merged[merged.length - 1] = {
        ...prev,
        endSec: newEndSec,
        durationSec: newDurationSec,
        width: newWidth,
        // 融合后的 tooltip 显示范围
        end_time: curr.end_time,
        // 保留第一个片段的 start_time 和 id
        _merged: true,
        _mergedEndTime: curr.end_time,
      };
    } else {
      merged.push(curr);
    }
  }
  return merged;
};

// ═══════════════════════════════════════════════════════════════════════════
// TimelineBar
// ═══════════════════════════════════════════════════════════════════════════

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
  const viewportRef = useRef(null);

  // ── 平移状态（替代 scrollLeft） ──────────────────────────────────
  const [panX, setPanX] = useState(0);
  const panXRaf = useRef(null);

  // ── 交互状态 ref（避免 useCallback 依赖变化） ───────────────────
  const stateRef = useRef({
    mode: 'idle',        // 'idle' | 'pan' | 'seek' | 'playheadDrag'
    startMouseX: 0,
    startPanX: 0,
    dragDistance: 0,
    seekTargetSec: 0,
    isPanning: false,
  });

  const [containerWidth, setContainerWidth] = useState(0);
  const [hoveredTickIdx, setHoveredTickIdx] = useState(null);

  // 悬停指示线 — rAF 节流
  const [hoverDisplay, setHoverDisplay] = useState(null);
  const rafId = useRef(null);
  const rafPending = useRef(null);

  const scheduleHoverUpdate = useCallback(() => {
    if (rafId.current !== null) return;
    rafId.current = requestAnimationFrame(() => {
      rafId.current = null;
      if (rafPending.current !== null) {
        setHoverDisplay(rafPending.current);
        rafPending.current = null;
      }
    });
  }, []);

  const updateHoverDisplay = useCallback((data) => {
    rafPending.current = data;
    scheduleHoverUpdate();
  }, [scheduleHoverUpdate]);

  const zoomAnchorSecRef = useRef(null);
  const activeBlockInfoRef = useRef(null);

  const currentZoom = ZOOM_LEVELS[zoom] || ZOOM_LEVELS[0];
  const viewSeconds = currentZoom.viewSeconds;
  const zoomRatio = SECONDS_PER_DAY / viewSeconds;

  // 内容总宽度（像素）
  const contentWidthPx = useMemo(
    () => containerWidth * zoomRatio,
    [containerWidth, zoomRatio],
  );

  // ── 容器宽度监听（rAF 节流） ─────────────────────────────────────
  useEffect(() => {
    const container = viewportRef.current;
    if (!container) return;
    let frameId;
    const update = () => {
      if (frameId) return;
      frameId = requestAnimationFrame(() => {
        frameId = null;
        setContainerWidth(container.clientWidth);
      });
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(container);
    return () => ro.disconnect();
  }, []);

  // ── 刻度 ─────────────────────────────────────────────────────────
  const tickConfig = useMemo(() => getTickConfig(zoom), [zoom]);
  const tickMarks = useMemo(() => generateTickMarks(tickConfig), [tickConfig]);

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

    const labelMap = new Map();
    labelTicks.forEach((l, i) => labelMap.set(Math.round(l.seconds), i));

    return tickMarks.map((tick) => {
      if (!tick.isLabel) return { ...tick, hidden: false, displayLabel: '', showOnHover: false };
      const idx = labelMap.get(Math.round(tick.seconds));
      if (idx === undefined) return { ...tick, hidden: false, displayLabel: tick.label, showOnHover: false };

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

  // ── 片段块数据 + 融合相邻色块 ────────────────────────────────────
  const segmentBlocks = useMemo(() => {
    if (!segments.length) return [];
    const trackInnerPx = contentWidthPx;
    const shouldEnforceMinWidth = zoom > 2;

    const rawBlocks = [];
    for (let i = 0; i < segments.length; i++) {
      const seg = segments[i];
      const startSec = dayjsToSeconds(dayjs(seg.start_time));

      let durationSec;
      if (typeof seg.duration_seconds === 'number' && seg.duration_seconds > 0) {
        durationSec = seg.duration_seconds;
      } else if (seg.file_size_bytes > 0) {
        durationSec = Math.max(1, Math.round(seg.file_size_bytes / (150 * 1024)));
      } else {
        durationSec = Math.max(0, dayjsToSeconds(dayjs(seg.end_time)) - startSec);
      }
      if (durationSec <= 0) continue;

      const endSec = startSec + durationSec;
      const rawLeft = (startSec / SECONDS_PER_DAY) * 100;
      const rawWidth = (durationSec / SECONDS_PER_DAY) * 100;

      const realWidthPx = trackInnerPx > 0 ? rawWidth * trackInnerPx / 100 : 0;
      let displayWidth = rawWidth;
      let adjustedLeft = rawLeft;

      if (shouldEnforceMinWidth && realWidthPx > 0 && realWidthPx < MIN_VISIBLE_WIDTH_PX) {
        const minPct = trackInnerPx > 0 ? (MIN_VISIBLE_WIDTH_PX / trackInnerPx) * 100 : 0;
        displayWidth = Math.max(rawWidth, minPct);
        adjustedLeft = Math.max(0, rawLeft - (displayWidth - rawWidth) / 2);
      }

      rawBlocks.push({
        ...seg,
        left: adjustedLeft,
        width: displayWidth,
        startSec,
        endSec,
        durationSec,
        isActive: seg.id === activeSegmentId,
      });
    }

    // 按 startSec 排序
    rawBlocks.sort((a, b) => a.startSec - b.startSec);

    // 融合相邻色块（间隔 ≤ 2s）
    return mergeAdjacentBlocks(rawBlocks);
  }, [segments, contentWidthPx, zoom, activeSegmentId]);

  // ── 视口裁剪 ─────────────────────────────────────────────────────
  const visibleBlocks = useMemo(() => {
    if (!containerWidth || segmentBlocks.length === 0) return segmentBlocks;
    const viewLeftPx = panX;
    const viewRightPx = panX + containerWidth;
    const totalWidthPx = contentWidthPx;

    const BUFFER = 200;
    const viewLeftPct = ((viewLeftPx - BUFFER) / totalWidthPx) * 100;
    const viewRightPct = ((viewRightPx + BUFFER) / totalWidthPx) * 100;

    let lo = 0, hi = segmentBlocks.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (segmentBlocks[mid].left + segmentBlocks[mid].width < viewLeftPct) {
        lo = mid + 1;
      } else {
        hi = mid;
      }
    }

    const result = [];
    for (let i = lo; i < segmentBlocks.length; i++) {
      const b = segmentBlocks[i];
      if (b.left > viewRightPct) break;
      result.push(b);
    }
    return result;
  }, [segmentBlocks, containerWidth, panX, contentWidthPx]);

  // ── 播放指示线（内容空间 + 视口空间） ────────────────────────────
  const playheadInfo = useMemo(() => {
    if (globalTime <= 0 && !activeSegment) return null;
    const leftPct = (globalTime / SECONDS_PER_DAY) * 100;
    const dateStr = selectedDate ? selectedDate.format('YYYY-MM-DD') : dayjs().format('YYYY-MM-DD');
    const timeStr = `${dateStr} ${formatTimeLabel(globalTime, true)}`;
    const label = formatTimeLabel(globalTime, viewSeconds <= 3600);
    // 视口像素坐标（用于不受 transform 影响的时间标签）
    const viewportX = (leftPct / 100) * contentWidthPx - panX;
    return { leftPct, timeStr, label, viewportX };
  }, [globalTime, selectedDate, viewSeconds, activeSegment, contentWidthPx, panX]);

  // 滚动监听改为监听 panX 变化即可（通过 state 驱动）

  // ── 缩放操作 ─────────────────────────────────────────────────────
  const handleZoomIn = useCallback(
    () => zoom < MAX_ZOOM_INDEX && onZoomChange?.(zoom + 1),
    [zoom, onZoomChange],
  );
  const handleZoomOut = useCallback(
    () => zoom > MIN_ZOOM_INDEX && onZoomChange?.(zoom - 1),
    [zoom, onZoomChange],
  );
  const handleZoomReset = useCallback(() => onZoomChange?.(0), [onZoomChange]);

  // ── 鼠标滚轮缩放（以光标为中心）+ 80ms 节流 ─────────────────────
  const wheelThrottleRef = useRef(0);
  const handleWheel = useCallback(
    (e) => {
      e.preventDefault();
      const now = performance.now();
      if (now - wheelThrottleRef.current < 80) return;
      wheelThrottleRef.current = now;

      const container = viewportRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();

      // 光标在内容空间中的像素位置（考虑 pan offset）
      const cursorContentX = e.clientX - rect.left + panX;
      const totalWidthPx = contentWidthPx;
      const anchorSec = (cursorContentX / totalWidthPx) * SECONDS_PER_DAY;

      const delta = e.deltaY < 0 ? 1 : -1;
      const next = Math.max(MIN_ZOOM_INDEX, Math.min(MAX_ZOOM_INDEX, zoom + delta));
      if (next === zoom) return;

      zoomAnchorSecRef.current = { sec: anchorSec, mouseViewportX: e.clientX - rect.left };
      onZoomChange?.(next);
    },
    [zoom, onZoomChange, panX, contentWidthPx],
  );

  // 缩放后重定位 panX 使锚点保持在鼠标位置
  useLayoutEffect(() => {
    const anchor = zoomAnchorSecRef.current;
    if (!anchor) return;
    zoomAnchorSecRef.current = null;

    const totalWidthPx = contentWidthPx;
    const anchorPx = (anchor.sec / SECONDS_PER_DAY) * totalWidthPx;
    const newPanX = Math.max(0, anchorPx - anchor.mouseViewportX);
    // 限制 panX 不超出内容范围
    const maxPan = Math.max(0, totalWidthPx - containerWidth);
    setPanX(Math.min(newPanX, maxPan));
  }, [zoom, contentWidthPx, containerWidth]);

  // ── 坐标换算 ─────────────────────────────────────────────────────
  /**
   * 将鼠标事件转换为视口像素坐标 + 内容空间秒数
   * viewportX：鼠标相对于视口左边缘的像素偏移（用于 hover 层精确定位）
   */
  const mouseEventToCoords = useCallback((e) => {
    const container = viewportRef.current;
    if (!container) return { viewportX: 0, totalSec: 0 };
    const rect = container.getBoundingClientRect();
    const viewportX = e.clientX - rect.left;  // 视口像素偏移，无视 transform 影响
    const mouseContentX = viewportX + panX;   // 内容空间像素偏移
    const totalWidthPx = contentWidthPx;
    const totalSec = totalWidthPx > 0
      ? (mouseContentX / totalWidthPx) * SECONDS_PER_DAY
      : 0;
    return { viewportX, totalSec };
  }, [panX, contentWidthPx]);

  /** 简写：仅获取当天秒数 */
  const mouseEventToGlobalSec = useCallback((e) => mouseEventToCoords(e).totalSec, [mouseEventToCoords]);

  // ── 二分查找命中片段 ────────────────────────────────────────────
  const findSegmentAt = useCallback((sec) => {
    let lo = 0, hi = segmentBlocks.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const b = segmentBlocks[mid];
      if (sec >= b.startSec && sec <= b.endSec) return b;
      if (sec < b.startSec) hi = mid - 1;
      else lo = mid + 1;
    }
    return null;
  }, [segmentBlocks]);

  // 同步 activeBlockInfoRef
  useMemo(() => {
    if (!activeSegmentId || !segmentBlocks.length) {
      activeBlockInfoRef.current = null;
      return;
    }
    const ab = segmentBlocks.find((b) => b.id === activeSegmentId);
    activeBlockInfoRef.current = ab ? { startSec: ab.startSec, endSec: ab.endSec } : null;
  }, [activeSegmentId, segmentBlocks]);

  // ── Pan 偏移约束 ─────────────────────────────────────────────────
  const clampPanX = useCallback((value) => {
    const maxPan = Math.max(0, contentWidthPx - containerWidth);
    return Math.max(0, Math.min(value, maxPan));
  }, [contentWidthPx, containerWidth]);

  // ── 鼠标事件处理 ─────────────────────────────────────────────────
  /**
   * 交互模型（参考专业视频剪辑软件）：
   *   - 标尺/刻度区域拖拽 → 平移时间轴
   *   - 片段轨道区域：
   *       - 点击片段（拖动 < 3px）→ 切换/播放
   *       - 点击空白（拖动 < 3px）→ seek 到该位置
   *       - 拖拽片段 → 在当前活跃片段内快进/快退
   *       - 拖拽空白区域 → 平移时间轴
   *   - 播放头拖拽 → 快进/快退
   */
  const handleTrackMouseDown = useCallback(
    (e) => {
      if (e.button !== 0) return;
      e.preventDefault();

      const s = stateRef.current;
      s.startMouseX = e.clientX;
      s.startPanX = panX;
      s.dragDistance = 0;
      s.seekTargetSec = mouseEventToGlobalSec(e);
      s.isPanning = false;

      // 判断点击目标
      const targetEl = e.target;
      const isPlayhead = targetEl?.closest?.('[data-playhead]');
      const isRuler = targetEl?.closest?.(`.${styles.tickRow}`) || targetEl?.closest?.(`.${styles.tickLines}`);
      const isSegment = targetEl?.closest?.(`.${styles.segmentFill}`);

      if (isPlayhead) {
        s.mode = 'playheadDrag';
        document.body.style.cursor = 'ew-resize';
      } else if (isRuler || !isSegment) {
        // 标尺或空白区域 → 平移
        s.mode = 'pan';
        document.body.style.cursor = 'grabbing';
      } else {
        // 点击在片段上 → 可能 seek 或 平移（取决于拖拽距离）
        s.mode = 'segment';
      }

      document.body.style.userSelect = 'none';
    },
    [panX, mouseEventToGlobalSec],
  );

  // 全局 mousemove
  const handleGlobalMouseMove = useCallback(
    (e) => {
      const s = stateRef.current;
      if (s.mode === 'idle') return;
      s.dragDistance += Math.abs(e.movementX || 0);

      if (s.mode === 'pan' || (s.mode === 'segment' && s.dragDistance >= 3)) {
        // 平移时间轴
        if (!s.isPanning) {
          s.isPanning = true;
          document.body.style.cursor = 'grabbing';
        }
        const deltaX = s.startMouseX - e.clientX;
        const newPan = clampPanX(s.startPanX + deltaX);
        setPanX(newPan);
        updateHoverDisplay(null);
        return;
      }

      if (s.mode === 'playheadDrag' || (s.mode === 'segment' && s.dragDistance >= 3)) {
        // 拖拽快进（在活跃片段范围内）
        const { viewportX, totalSec } = mouseEventToCoords(e);
        const abi = activeBlockInfoRef.current;
        if (abi && s.mode === 'segment') {
          s.seekTargetSec = Math.max(abi.startSec, Math.min(abi.endSec, totalSec));
        } else {
          s.seekTargetSec = totalSec;
        }
        updateHoverDisplay({
          viewportX,
          totalSec: s.seekTargetSec,
          label: formatTimeLabel(s.seekTargetSec, viewSeconds <= 3600),
          isOverActive: true,
          isSeeking: true,
          isOverAnySegment: true,
        });
        // 实时 seek
        onSeek?.(s.seekTargetSec);
      }
    },
    [mouseEventToCoords, viewSeconds, updateHoverDisplay, clampPanX, onSeek],
  );

  const handleGlobalMouseUp = useCallback(
    (e) => {
      const s = stateRef.current;
      if (s.mode === 'idle') {
        document.body.style.userSelect = '';
        return;
      }

      const isClick = s.dragDistance < 3;

      if (s.mode === 'segment' && isClick) {
        const hit = findSegmentAt(s.seekTargetSec);
        if (hit && hit.id !== activeSegmentId) {
          // 不同片段：先切换并开始播放，等视频加载后再 seek 到点击位置
          onSegmentClick?.(hit);
          const targetSec = s.seekTargetSec;
          setTimeout(() => onSeek?.(targetSec), 200);
        } else if (hit && onSeek) {
          // 同一片段：直接 seek
          onSeek(s.seekTargetSec);
        }
      } else if ((s.mode === 'segment' || s.mode === 'playheadDrag') && !isClick) {
        // 拖拽快进完成 → 最后的 seek 已在 mousemove 中执行
      } else if (!s.isPanning && isClick && s.mode !== 'pan') {
        // 点击空白 → seek
        if (onSeek) onSeek(s.seekTargetSec);
      }

      s.mode = 'idle';
      s.isPanning = false;
      updateHoverDisplay(null);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    },
    [findSegmentAt, activeSegmentId, onSeek, onSegmentClick, updateHoverDisplay],
  );

  // 全局事件注册（只注册一次，ref 包装）
  const handleGlobalMouseMoveRef = useRef(handleGlobalMouseMove);
  handleGlobalMouseMoveRef.current = handleGlobalMouseMove;
  const handleGlobalMouseUpRef = useRef(handleGlobalMouseUp);
  handleGlobalMouseUpRef.current = handleGlobalMouseUp;

  useEffect(() => {
    const onMove = (e) => handleGlobalMouseMoveRef.current(e);
    const onUp = (e) => handleGlobalMouseUpRef.current(e);
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, []);

  useEffect(() => {
    const c = viewportRef.current;
    if (!c) return;
    c.addEventListener('wheel', handleWheel, { passive: false });
    return () => c.removeEventListener('wheel', handleWheel);
  }, [handleWheel]);

  // ── 轨道 hover（非拖拽状态） ─────────────────────────────────────
  const handleTrackHover = useCallback(
    (e) => {
      if (stateRef.current.mode !== 'idle') return;
      const { viewportX, totalSec } = mouseEventToCoords(e);
      const abi = activeBlockInfoRef.current;
      const isOverActive = abi
        ? totalSec >= abi.startSec && totalSec <= abi.endSec
        : false;
      const isOverAnySegment = findSegmentAt(totalSec) !== null;

      updateHoverDisplay({
        viewportX,  // 视口像素坐标，用于精确定位
        totalSec,
        label: formatTimeLabel(totalSec, viewSeconds <= 3600),
        isOverActive,
        isOverAnySegment,
        isSeeking: false,
      });
    },
    [mouseEventToCoords, viewSeconds, findSegmentAt, updateHoverDisplay],
  );

  const handleTrackMouseLeave = useCallback(() => {
    if (stateRef.current.mode === 'idle') {
      updateHoverDisplay(null);
    }
  }, [updateHoverDisplay]);

  // ── 渲染辅助 ─────────────────────────────────────────────────────
  const getTickLineClass = useCallback((level) => {
    const map = {
      hour: styles.tickLine_hour, halfHour: styles.tickLine_halfHour,
      tenMinute: styles.tickLine_tenMinute, minute: styles.tickLine_minute,
      minor: styles.tickLine_minor,
    };
    return `${styles.tickLine} ${map[level] || styles.tickLine_minor}`;
  }, []);

  const activeIdSet = useMemo(
    () => new Set(activeSegmentId ? [activeSegmentId] : []),
    [activeSegmentId],
  );

  // 当前是否正在拖拽（用于 cursor 样式）
  const isPanning = stateRef.current.mode === 'pan' || stateRef.current.isPanning;

  // ═══════════════════════════════════════════════════════════════════
  // 渲染
  // ═══════════════════════════════════════════════════════════════════

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

      {/* ── 时间轴主体（无滚动条，通过拖拽平移） ── */}
      <div className={styles.timelineBody}>
        <div
          ref={viewportRef}
          className={`${styles.timelineViewport} ${isPanning ? styles.panning : ''}`}
          onMouseDown={handleTrackMouseDown}
          onMouseMove={handleTrackHover}
          onMouseLeave={handleTrackMouseLeave}
        >
          <div
            className={styles.timelineTrackInner}
            style={{
              width: `${zoomRatio * 100}%`,
              transform: `translateX(${-panX}px)`,
            }}
          >
            {/* 刻度标签行 */}
            <div className={styles.tickRow}>
              {visibleTickLabels
                .filter((tk) => tk.isLabel)
                .map((tick) => {
                  const key = `lbl-${tick.seconds}`;
                  const isHovered = hoveredTickIdx === key;
                  return (
                    <span
                      key={key}
                      className={`${styles.tickLabel} ${
                        tick.hidden ? styles.tickLabelHidden : ''
                      } ${
                        tick.showOnHover && isHovered ? styles.tickLabelHovered : ''
                      }`}
                      style={{ left: `${tick.left}%` }}
                      onMouseEnter={() => setHoveredTickIdx(key)}
                      onMouseLeave={() => setHoveredTickIdx(null)}
                    >
                      {tick.displayLabel || tick.label}
                      {tick.showOnHover && !isHovered && (
                        <span className={styles.tickLabelDots}>···</span>
                      )}
                    </span>
                  );
                })}
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

            {/* 轨道 + 片段色块 */}
            <div className={styles.segmentTrack}>
              {visibleBlocks.map((seg) => {
                const modeCfg = MODE_CONFIG[seg.recording_mode] || MODE_CONFIG.continuous;
                const isActive = activeIdSet.has(seg.id);
                const tooltipEnd = seg._mergedEndTime || seg.end_time;
                return (
                  <div
                    key={seg.id}
                    className={`${styles.segmentFill} ${isActive ? styles.segmentFillActive : ''}`}
                    title={`${dayjs(seg.start_time).format('HH:mm:ss')} - ${dayjs(tooltipEnd).format('HH:mm:ss')} · ${t(modeCfg.labelKey)}`}
                    style={{
                      left: `${seg.left}%`,
                      width: `${seg.width}%`,
                      background: modeCfg.color,
                      opacity: isActive ? 1 : 0.75,
                    }}
                    onClick={(e) => { e.stopPropagation(); }}
                  />
                );
              })}

              {/* 播放指示线（dot + line 在内容区内，时间标签在视口覆盖层避免裁切） */}
              {playheadInfo && (
                <div
                  className={styles.playheadLine}
                  style={{ left: `${playheadInfo.leftPct}%` }}
                >
                  <div className={styles.playheadDot} data-playhead="true" />
                </div>
              )}

            </div>
          </div>

          {/* ── 播放头时间标签（视口层，避免 overflow:hidden 裁切） ── */}
          {playheadInfo && (
            <div className={styles.playheadTimeLabel} style={{ left: `${playheadInfo.viewportX}px` }}>
              {playheadInfo.label}
            </div>
          )}

          {/* ── hover/seek 指示线 + 时间浮标（视口层，不受 transform 影响） ── */}
          {hoverDisplay && (
            <div className={styles.hoverOverlay} style={{ left: `${hoverDisplay.viewportX}px` }}>
              <div
                className={`${styles.hoverLine} ${
                  hoverDisplay.isSeeking ? styles.hoverLineSeeking : ''
                } ${
                  hoverDisplay.isOverAnySegment ? styles.hoverLineSeekable : ''
                }`}
              />
              <span className={`${styles.hoverLabel} ${hoverDisplay.isSeeking ? styles.hoverLabelSeeking : ''}`}>
                {hoverDisplay.label}
                {(hoverDisplay.isOverAnySegment || hoverDisplay.isSeeking) && (
                  <span className={styles.seekHint}>
                    {' '}· {hoverDisplay.isSeeking
                      ? t('recording.playback.seeking')
                      : t('recording.playback.clickToSeek')}
                  </span>
                )}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* ── 底部 ── */}
      <div className={styles.timelineFooter}>
        <span className={styles.footerTime}>
          {playheadInfo
            ? playheadInfo.timeStr
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
