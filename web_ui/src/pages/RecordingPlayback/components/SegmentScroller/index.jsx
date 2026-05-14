import React, { useState, useEffect, useRef, useCallback } from 'react';
import { PlayCircleOutlined, VideoCameraOutlined, DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { getRecordingThumbnailUrl } from '@/api';
import styles from './index.module.less';

const LazyThumbnail = ({ segment, isActive, isSelected, onClick, onToggleSelect }) => {
  const { t } = useTranslation();
  const imgRef = useRef(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          const img = imgRef.current;
          if (img) {
            img.src = getRecordingThumbnailUrl(segment.id, 1);
          }
          observer.disconnect();
        }
      },
      { rootMargin: '200px' }
    );

    if (imgRef.current) {
      observer.observe(imgRef.current);
    }

    return () => observer.disconnect();
  }, [segment.id]);

  const formatDuration = (seconds) => {
    if (!seconds) return '0s';
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return m > 0 ? `${m}:${String(s).padStart(2, '0')}` : `${s}s`;
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return '0 B';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`;
  };

  const modeLabels = {
    continuous: t('recording.playback.triggerContinuous'),
    person: t('recording.playback.triggerPerson'),
    motion: t('recording.playback.triggerMotion'),
  };

  const startTime = segment.start_time ? new Date(segment.start_time) : null;
  const timeStr = startTime
    ? `${String(startTime.getHours()).padStart(2, '0')}:${String(startTime.getMinutes()).padStart(2, '0')}:${String(startTime.getSeconds()).padStart(2, '0')}`
    : '';

  return (
    <div
      className={`${styles.thumbnailItem} ${isActive ? styles.active : ''} ${isSelected ? styles.selected : ''}`}
      onClick={() => onClick(segment)}
    >
      <div className={styles.thumbImageWrapper}>
        <img
          ref={imgRef}
          className={styles.thumbImage}
          alt=""
          onLoad={() => setLoaded(true)}
          onError={() => setError(true)}
          style={{ display: error ? 'none' : 'block' }}
        />
        {!loaded && !error && (
          <div className={styles.thumbPlaceholder}>
            <VideoCameraOutlined />
          </div>
        )}

        <div className={styles.thumbOverlay}>
          <div className={styles.playIcon}>
            <PlayCircleOutlined />
          </div>
        </div>

        <span className={styles.thumbDuration}>
          {formatDuration(segment.duration_seconds)}
        </span>

        {segment.recording_mode && (
          <span className={`${styles.thumbMode} ${styles[segment.recording_mode]}`}>
            {modeLabels[segment.recording_mode] || segment.recording_mode}
          </span>
        )}

        <div
          className={styles.checkbox}
          onClick={(e) => {
            e.stopPropagation();
            onToggleSelect(segment.id);
          }}
        >
          <input
            type="checkbox"
            checked={isSelected}
            onChange={() => onToggleSelect(segment.id)}
          />
        </div>
      </div>

      <div className={styles.thumbInfo}>
        <div className={styles.thumbTime}>{timeStr}</div>
        <div className={styles.thumbSize}>{formatFileSize(segment.file_size_bytes)}</div>
      </div>
    </div>
  );
};

const SegmentScroller = ({
  segments = [],
  activeSegmentId,
  selectedSegmentIds = new Set(),
  onSegmentClick,
  onToggleSelect,
  onSelectAll,
  onDeleteSingle,
}) => {
  const { t } = useTranslation();
  const scrollRef = useRef(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const checkScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 0);
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    checkScroll();
    el.addEventListener('scroll', checkScroll);
    window.addEventListener('resize', checkScroll);
    return () => {
      el.removeEventListener('scroll', checkScroll);
      window.removeEventListener('resize', checkScroll);
    };
  }, [checkScroll, segments]);

  const scrollBy = (direction) => {
    const el = scrollRef.current;
    if (!el) return;
    const amount = el.clientWidth * 0.7;
    el.scrollBy({ left: direction === 'left' ? -amount : amount, behavior: 'smooth' });
  };

  const isAllSelected = segments.length > 0 && selectedSegmentIds.size === segments.length;

  if (!segments.length) {
    return (
      <div className={styles.emptyGrid}>
        <div className={styles.emptyIcon}>
          <VideoCameraOutlined />
        </div>
        <div>{t('recording.playback.noSegments')}</div>
      </div>
    );
  }

  return (
    <div className={styles.segmentScrollerWrapper}>
      <div className={styles.scrollerHeader}>
        <div className={styles.scrollerControls}>
          <label
            className={`${styles.selectAllLabel} ${isAllSelected ? styles.checked : ''}`}
          >
            <input
              type="checkbox"
              checked={isAllSelected}
              onChange={() => onSelectAll()}
            />
            <span>{t('recording.playback.selectAll')}</span>
          </label>
        </div>
      </div>

      <div className={styles.scrollerContainer}>
        {canScrollLeft && (
          <button className={`${styles.scrollButton} ${styles.left}`} onClick={() => scrollBy('left')}>
            ‹
          </button>
        )}

        <div className={styles.scrollerTrack} ref={scrollRef}>
          {segments.map((seg) => (
            <LazyThumbnail
              key={seg.id}
              segment={seg}
              isActive={seg.id === activeSegmentId}
              isSelected={selectedSegmentIds.has(seg.id)}
              onClick={onSegmentClick}
              onToggleSelect={onToggleSelect}
            />
          ))}
        </div>

        {canScrollRight && (
          <button className={`${styles.scrollButton} ${styles.right}`} onClick={() => scrollBy('right')}>
            ›
          </button>
        )}
      </div>
    </div>
  );
};

export default SegmentScroller;