/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { useTranslation } from 'react-i18next';
import styles from './SelectedCameras.module.less';
import Icon from '@/components/Icon';

/**
 * SelectedCameras Component - Display selected cameras
 * 已选择摄像头组件 - 显示已选择的摄像头
 *
 * @param {Object} props - Component props
 * @param {Array} props.selectedCameras - List of selected cameras
 * @param {Function} props.onRemoveCamera - Function to remove a camera
 * @returns {JSX.Element} SelectedCameras component
 */
const SelectedCameras = ({
  selectedCameras,
  onRemoveCamera
}) => {
  const { t } = useTranslation();

  if (!selectedCameras || selectedCameras.length === 0) {
    return null;
  }

  return (
    <div className={styles.selectedCamerasContainer}>
      {selectedCameras.map((camera) => (
        <div key={camera.did} className={styles.cameraTag}>
          <span className={styles.cameraName}>
            {camera.name || camera.did}
          </span>
          <button
            className={styles.removeButton}
            onClick={() => onRemoveCamera(camera.did)}
            title={t('instant.chat.removeCamera')}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
};

export default SelectedCameras;
