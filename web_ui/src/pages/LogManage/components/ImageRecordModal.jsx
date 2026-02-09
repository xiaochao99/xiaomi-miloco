/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { Empty, Modal, Button, message } from 'antd';
import { useTranslation } from 'react-i18next';
import { DownloadOutlined } from '@ant-design/icons';
import { zip } from 'fflate';
import styles from './ImageRecordModal.module.less';

/**
 * ImageRecordModal Component - Image record modal component
 * 图片记录弹窗组件
 *
 * @param {Object} props - Component props
 * @param {boolean} props.visible - Whether the modal is visible
 * @param {Function} props.onCancel - Function to cancel the modal
 * @param {Array} props.imageData - Image data
 * @returns {JSX.Element} ImageRecordModal component
 */
const ImageRecordModal = ({
  visible,
  onCancel,
  imageData = []
}) => {
  const { t } = useTranslation();

  // download all images of the specified camera (ZIP packaging)
  const downloadCameraImages = async (camera) => {
    if (!camera.images || camera.images.length === 0) {
      return;
    }

    try {
      const cameraName = camera.camera_info?.name || 'camera';
      // parallel download all images and add to ZIP
      const downloadPromises = camera.images.map(async (image, index) => {
        try {
          const imageUrl = image.data?.startsWith('/') ?
            `${window.location.origin}${import.meta.env.VITE_API_BASE}${image.data}` :
            (image.data?.startsWith('http') ? image.data : `${import.meta.env.VITE_API_BASE}/${image.data}`);

          const response = await fetch(imageUrl);
          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
          }

          const blob = await response.blob();
          const arrayBuffer = await blob.arrayBuffer();
          const fileName = `${cameraName}_${String(index + 1).padStart(3, '0')}_${image.timestamp || Date.now()}.jpg`;

          return {
            fileName,
            data: new Uint8Array(arrayBuffer)
          };
        } catch (error) {
          console.error('downloadImageFailed:', image.timestamp, error);
          return null;
        }
      });

      // wait for all images to be downloaded
      const imageFiles = await Promise.all(downloadPromises);
      const validFiles = imageFiles.filter(file => file !== null);
      const zipFiles = {};
      validFiles.forEach(file => {
        zipFiles[file.fileName] = file.data;
      });


      const zipBlob = await new Promise((resolve, reject) => {
        zip(zipFiles, (err, data) => {
          if (err) {
            reject(err);
          } else {
            resolve(new Blob([data], { type: 'application/zip' }));
          }
        });
      });

      const downloadUrl = window.URL.createObjectURL(zipBlob);
      const link = document.createElement('a');
      const now = new Date();
      const timestamp = now.toISOString().slice(0, 19).replace(/[-:]/g, '').replace('T', '_');
      link.href = downloadUrl;
      link.download = `${cameraName}_images_${timestamp}.zip`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(downloadUrl);

      console.log(`imagesPackaged: ${cameraName}_images_${timestamp}.zip`);
      message.success(t('logManage.imagesPackaged'));
    } catch (error) {
      console.error('downloadCameraImages failed:', error);
      message.error(t('logManage.imagesPackagedFailed'));
    }
  };
  const renderImagePlaceholder = (image, index) => {
    const { data: imagePath, timestamp } = image;
    const imageUrl = imagePath?.startsWith('/') ?
      `${window.location.origin}${import.meta.env.VITE_API_BASE}${imagePath}` :
      (imagePath?.startsWith('http') ? imagePath : `${import.meta.env.VITE_API_BASE}/${imagePath}`);
    return (
      <div key={index} className={styles.imagePlaceholder}>
        <img src={imageUrl} alt={timestamp} />
      </div>
    );
  };

  const renderCameraSection = (camera, index) => {
    const { images = [], camera_info = {} } = camera;
    const { name, home_name, room_name } = camera_info || {};
    return (
      <div key={index} className={styles.cameraSection}>
        <div className={styles.cameraTitleWrapper}>
          <h3 className={styles.cameraTitle}>{`${name}(${home_name || ''}${room_name || ''})`}</h3>
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            onClick={() => downloadCameraImages(camera)}
            size="small"
            disabled={!images || images.length === 0}
          >
            {t('common.download')}
          </Button>
        </div>
        {images?.length > 0
          ?
          <div className={styles.imageGrid}>
            {images?.map((image, imgIndex) => renderImagePlaceholder(image, imgIndex))}
          </div>
          : <div className={styles.emptyWrap}><Empty description="No data" /></div>
        }
      </div>
    )
  };

  return (
    <Modal
      title={t('logManage.imageRecord')}
      open={visible}
      onCancel={onCancel}
      footer={null}
      width={800}
      className={styles.imageRecordModal}
      center
    >
      <div className={styles.modalContent}>
        {imageData?.length > 0
          ? imageData?.map((camera, index) => renderCameraSection(camera, index))
          : <div
            className={styles.emptyWrap}><Empty description="No data" /></div>
        }
      </div>
    </Modal>
  );
};

export default ImageRecordModal;
