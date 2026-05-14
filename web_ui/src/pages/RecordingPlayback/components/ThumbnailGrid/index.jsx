import React, { useState, useEffect, useRef, useCallback } from 'react';
import { PlayCircleOutlined, VideoCameraOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { getRecordingThumbnailUrl } from '@/api';
import styles from './index.module.less';

const LazyThumbnail = ({ segment, isActive, onClick }) => {
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
  const dateStr = startTime
    ? `${startTime.getMonth() + 1}/${startTime.getDate()}`
    : '';

  return (
    <div
      className={`${styles.thumbnailItem} ${isActive ? styles.active : ''}`}
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
      </div>

      <div className={styles.thumbInfo}>
        <div className={styles.thumbTime}>
          {dateStr} {timeStr}
        </div>
        <div className={styles.thumbSize}>
          {formatFileSize(segment.file_size_bytes)}
        </div>
      </div>
    </div>
  );
};

const ThumbnailGrid = ({ segments = [], activeSegmentId, onSegmentClick }) => {
  const { t } = useTranslation();

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
    <div className={styles.thumbnailGrid}>
      {segments.map((seg) => (
        <LazyThumbnail
          key={seg.id}
          segment={seg}
          isActive={seg.id === activeSegmentId}
          onClick={onSegmentClick}
        />
      ))}
    </div>
  );
};

export default ThumbnailGrid;
