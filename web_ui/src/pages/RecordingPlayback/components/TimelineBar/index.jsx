import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { ZoomInOutlined, ZoomOutOutlined } from '@ant-design/icons';
import styles from './index.module.less';

const TimelineBar = ({
  segments = [],
  selectedDate = '',
  activeSegmentId,
  currentTime = 0,
  duration = 0,
  onSegmentClick,
  onTimelineClick,
}) => {
  const { t } = useTranslation();
  const trackRef = useRef(null);
  const [zoomLevel, setZoomLevel] = useState(1); // 1 = 24h, 2 = 12h, 4 = 6h, 8 = 3h, 16 = 1.5h
  const [scrollOffset, setScrollOffset] = useState(0);
  const [trackWidth, setTrackWidth] = useState(0);

  const zoomLevels = [
    { value: 1, label: '24h', hoursVisible: 24 },
    { value: 2, label: '12h', hoursVisible: 12 },
    { value: 4, label: '6h', hoursVisible: 6 },
    { value: 8, label: '3h', hoursVisible: 3 },
    { value: 16, label: '1.5h', hoursVisible: 1.5 },
  ];

  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setTrackWidth(entry.contentRect.width);
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const hoursVisible = useMemo(() => {
    const level = zoomLevels.find((l) => l.value === zoomLevel);
    return level ? level.hoursVisible : 24;
  }, [zoomLevel]);

  const maxScrollOffset = useMemo(() => {
    if (!trackWidth) return 0;
    const totalWidth = trackWidth * zoomLevel;
    return Math.max(0, totalWidth - trackWidth);
  }, [trackWidth, zoomLevel]);

  useEffect(() => {
    if (scrollOffset > maxScrollOffset) {
      setScrollOffset(maxScrollOffset);
    }
  }, [scrollOffset, maxScrollOffset]);

  const handleZoomIn = useCallback(() => {
    setZoomLevel((prev) => {
      const idx = zoomLevels.findIndex((l) => l.value === prev);
      if (idx < zoomLevels.length - 1) {
        return zoomLevels[idx + 1].value;
      }
      return prev;
    });
  }, []);

  const handleZoomOut = useCallback(() => {
    setZoomLevel((prev) => {
      const idx = zoomLevels.findIndex((l) => l.value === prev);
      if (idx > 0) {
        return zoomLevels[idx - 1].value;
      }
      return prev;
    });
  }, []);

  const hourMarks = useMemo(() => {
    const marks = [];
    const hoursPerMark = hoursVisible <= 3 ? 0.5 : 1;
    const totalHours = 24; // 时间轴总是表示24小时

    for (let h = 0; h <= totalHours; h += hoursPerMark) {
      marks.push(h);
    }
    return marks;
  }, [hoursVisible]);

  const dayRange = useMemo(() => {
    const start = selectedDate
      ? new Date(`${selectedDate}T00:00:00`).getTime()
      : new Date().setHours(0, 0, 0, 0);
    const end = start + 24 * 60 * 60 * 1000;
    return { start, end };
  }, [selectedDate]);

  const dayStartMs = dayRange.start;

  const segmentBlocks = useMemo(() => {
    if (!segments.length) return [];

    const totalRange = dayRange.end - dayRange.start;

    return segments.map((seg) => {
      const segStart = new Date(seg.start_time).getTime();
      const segEnd = new Date(seg.end_time || seg.start_time).getTime();

      const leftPercent = ((segStart - dayRange.start) / totalRange) * 100;
      const widthPercent = ((segEnd - segStart) / totalRange) * 100;

      return {
        ...seg,
        left: `${leftPercent}%`,
        width: `${Math.max(widthPercent, 0.1)}%`,
      };
    });
  }, [segments, dayRange]);

  const playheadPercent = useMemo(() => {
    if (!duration || !currentTime) return 0;
    return (currentTime / duration) * 100;
  }, [currentTime, duration]);

  const handleTrackClick = (e) => {
    const track = e.currentTarget;
    const rect = track.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / track.scrollWidth;

    if (onTimelineClick) {
      const clickTime = dayRange.start + ratio * 24 * 60 * 60 * 1000;

      let closestSeg = null;
      let minDist = Infinity;
      for (const seg of segments) {
        const segStart = new Date(seg.start_time).getTime();
        const segEnd = new Date(seg.end_time || seg.start_time).getTime();
        if (clickTime >= segStart && clickTime <= segEnd) {
          closestSeg = seg;
          break;
        }
        const dist = Math.min(Math.abs(clickTime - segStart), Math.abs(clickTime - segEnd));
        if (dist < minDist) {
          minDist = dist;
          closestSeg = seg;
        }
      }
      if (closestSeg) onTimelineClick(closestSeg);
    }
  };

  const formatTimeLabel = (h) => {
    const hours = Math.floor(h);
    const mins = Math.round((h - hours) * 60);
    return `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`;
  };

  const handleWheel = useCallback((e) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      if (e.deltaY < 0) {
        handleZoomIn();
      } else {
        handleZoomOut();
      }
    } else {
      setScrollOffset((prev) => {
        const next = prev + e.deltaY;
        return Math.max(0, Math.min(next, maxScrollOffset));
      });
    }
  }, [handleZoomIn, handleZoomOut, maxScrollOffset]);

  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => el.removeEventListener('wheel', handleWheel);
  }, [handleWheel]);

  return (
    <div className={styles.timelineWrapper}>
      <div className={styles.timelineHeader}>
        <span className={styles.timelineTitle}>{t('recording.playback.timeline')}</span>
        <div className={styles.timelineControls}>
          <span className={styles.zoomLabel}>{hoursVisible}h</span>
          <button
            className={styles.zoomButton}
            onClick={handleZoomOut}
            disabled={zoomLevel === 1}
          >
            <ZoomOutOutlined />
          </button>
          <div className={styles.zoomSlider}>
            <input
              type="range"
              min="1"
              max="16"
              step="1"
              value={zoomLevel}
              onChange={(e) => setZoomLevel(Number(e.target.value))}
            />
          </div>
          <button
            className={styles.zoomButton}
            onClick={handleZoomIn}
            disabled={zoomLevel === 16}
          >
            <ZoomInOutlined />
          </button>
        </div>
        <span className={styles.timelineDate}>{selectedDate}</span>
      </div>

      <div className={styles.timelineBody}>
        <div
          className={styles.timelineScrollContainer}
          ref={trackRef}
          onScroll={(e) => setScrollOffset(e.target.scrollLeft)}
        >
          <div
            className={styles.timelineTrackInner}
            style={{ width: `${zoomLevel * 100}%` }}
          >
            <div className={styles.hourMarks}>
              {hourMarks.map((h, idx) => (
                <div
                  key={idx}
                  className={`${styles.hourMark} ${
                    h % 1 === 0 ? styles.fullHour : styles.halfHour
                  }`}
                  style={{ left: `${(h / 24) * 100}%` }}
                >
                  {h % 1 === 0 && (
                    <span className={styles.hourLabel}>{formatTimeLabel(h)}</span>
                  )}
                  <div className={styles.markLine} />
                </div>
              ))}
            </div>

            <div className={styles.timelineTrack} onClick={handleTrackClick}>
              {segmentBlocks.map((block) => (
                <div
                  key={block.id}
                  className={`${styles.segmentBlock} ${styles[block.recording_mode] || ''} ${
                    block.id === activeSegmentId ? styles.active : ''
                  }`}
                  style={{ left: block.left, width: block.width }}
                  onClick={(e) => {
                    e.stopPropagation();
                    onSegmentClick?.(block);
                  }}
                >
                  <div className={styles.segmentTooltip}>
                    {new Date(block.start_time).toLocaleTimeString()} -{' '}
                    {block.end_time ? new Date(block.end_time).toLocaleTimeString() : ''}
                    {' '}({block.duration_seconds}s)
                  </div>
                </div>
              ))}

              {playheadPercent > 0 && (
                <div
                  className={styles.currentTimeLine}
                  style={{ left: `${playheadPercent}%` }}
                />
              )}
            </div>
          </div>
        </div>
      </div>

      <div className={styles.timelineLegend}>
        <div className={styles.legendItem}>
          <span className={`${styles.legendDot} ${styles.continuous}`} />
          {t('recording.playback.triggerContinuous')}
        </div>
        <div className={styles.legendItem}>
          <span className={`${styles.legendDot} ${styles.person}`} />
          {t('recording.playback.triggerPerson')}
        </div>
        <div className={styles.legendItem}>
          <span className={`${styles.legendDot} ${styles.motion}`} />
          {t('recording.playback.triggerMotion')}
        </div>
      </div>
    </div>
  );
};

export default TimelineBar;
