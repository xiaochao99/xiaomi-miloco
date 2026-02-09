/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import Icon from '@/components/Icon';
import CameraItem from './CameraItem';
import styles from './index.module.less';

/**
 * CameraImagesMessage Component - Camera images message component
 * 摄像头图片消息组件
 *
 * @param {Object} data - The data to display
 * @returns {JSX.Element} Camera images message component
 */
const CameraImagesMessage = ({ data }) => {
  const { image_path_seq_list = [] } = data;
  const autoOpen = image_path_seq_list.length < 3;


  return (
    <div className={styles.wrap}>
      {image_path_seq_list.map((cameraData, index) => (
        <CameraItem
          key={index}
          cameraData={cameraData}
          autoOpen={autoOpen}
          last={index === image_path_seq_list.length - 1}
        />
      ))}
    </div>
  );
};

export default CameraImagesMessage;
