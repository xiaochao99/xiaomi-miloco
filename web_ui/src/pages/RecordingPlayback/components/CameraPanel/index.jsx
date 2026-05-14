import React from 'react';
import { VideoCameraOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styles from './index.module.less';

const CameraPanel = ({
  cameras = [],
  selectedCameraId,
  recordingStatuses = {},
  segmentCounts = {},
  onCameraSelect,
}) => {
  const { t } = useTranslation();

  return (
    <div className={styles.cameraPanel}>
      <div className={styles.panelHeader}>
        <span className={styles.headerTitle}>
          <VideoCameraOutlined />
          {t('recording.playback.cameras')}
        </span>
        <span className={styles.cameraCount}>
          {cameras.length}
        </span>
      </div>

      <div className={styles.cameraList}>
        {cameras.map((camera) => {
          const isSelected = camera.did === selectedCameraId;
          const status = recordingStatuses[camera.did];
          const isRecording = status?.recording_active;
          const segCount = segmentCounts[camera.did] || 0;

          return (
            <div
              key={camera.did}
              className={`${styles.cameraItem} ${isSelected ? styles.selected : ''}`}
              onClick={() => onCameraSelect(camera.did)}
            >
              <div className={styles.cameraIcon}>
                <VideoCameraOutlined />
              </div>

              <div className={styles.cameraInfo}>
                <div className={styles.cameraName}>{camera.name}</div>
                <div className={styles.cameraId}>{camera.did}</div>
                {status && (
                  <div className={styles.cameraStatus}>
                    <span className={`${styles.statusDot} ${isRecording ? styles.recording : styles.idle}`} />
                    <span className={styles.statusText}>
                      {isRecording
                        ? t('recording.config.active')
                        : status.recording_enabled
                          ? t('recording.config.disabled')
                          : t('recording.config.disabled')}
                    </span>
                  </div>
                )}
              </div>

              {segCount > 0 && (
                <span className={styles.segmentBadge}>{segCount}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default CameraPanel;
