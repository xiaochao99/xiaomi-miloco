/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Icon from '@/components/Icon';

/**
 * CameraItem Component - Camera item component
 * 单个摄像头图片组件
 *
 * @param {Object} cameraData - The camera data to display
 * @param {boolean} autoOpen - Whether to open automatically
 * @param {boolean} last - Whether to show the last item
 * @returns {JSX.Element} Camera item component
 */
const CameraItem = ({ cameraData, autoOpen = false, last = false }) => {
  const { t } = useTranslation();
  const { camera_info, channel, img_list = [] } = cameraData;
  const { name, home_name, room_name, online } = camera_info || {};
  const [isExpanded, setIsExpanded] = useState(autoOpen);

  if(!online){
    return null;
  }

  return (
    <div>
      <div
        onClick={() => setIsExpanded(!isExpanded)}
        style={{
          padding: '8px 16px 8px',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          backgroundColor: 'var(--bg-color)'
        }}
      >
        {camera_info?.icon && <img src={camera_info.icon} alt="camera" style={{ width: '36px', height: '36px' }} />}
        <div style={{ flex: 1 }}>
          <div style={{
            fontSize: '14px',
            color: 'var(--text-color)',
            fontWeight: '500',
            marginBottom: '2px'
          }}>
            {name}
          </div>
          <div style={{
            fontSize: '12px',
            color: 'var(--text-color-6)',
            display: 'flex',
            gap: '8px'
          }}>
            <span>{home_name}</span>
            <span>·</span>
            <span>{room_name}</span>
            {channel !== undefined && (
              <>
                <span>·</span>
                <span>{t('instant.chat.channel')}{channel}</span>
              </>
            )}
          </div>
        </div>
        <span style={{
          fontSize: '12px',
          color: 'var(--text-color-6)',
          opacity: 0.8,
          marginRight: '8px'
        }}>
          {img_list.length} {t('instant.chat.images')}
        </span>
        <div style={{
          transform: !isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
          transition: 'transform 0.2s',
        }}>
          <Icon name="arrow" size={16} color={'var(--text-color)'} />
        </div>
      </div>

      {isExpanded && (
        <div style={{
          maxHeight: '400px',
          overflowY: 'scroll',
          padding: '0px 16px 16px',
          backgroundColor: 'var(--bg-color)'
        }}>
          {img_list.length > 0 ? (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(min(30%, 260px), 1fr))',
              gap: '8px',
            }}>
              {img_list.map((image, imgIndex) => {
                const { data: imagePath } = image;
                const imageUrl = imagePath?.startsWith('/') ?
                  `${window.location.origin}${import.meta.env.VITE_API_BASE}${imagePath}` :
                  (imagePath?.startsWith('http') ? imagePath : `${import.meta.env.VITE_API_BASE}/${imagePath}`);

                return (
                  <div key={imgIndex} style={{
                    position: 'relative',
                    aspectRatio: '16/9',
                    borderRadius: '4px',
                    overflow: 'hidden',
                    backgroundColor: 'var(--bg-color-6)',
                    width: '264px',
                  }}>
                    <img
                      src={imageUrl}
                      alt={`${name} - ${imgIndex + 1}`}
                      style={{
                        width: '100%',
                        height: '100%',
                        objectFit: 'cover'
                      }}
                      onError={(e) => {
                        e.target.style.display = 'none';
                        e.target.nextSibling.style.display = 'flex';
                      }}
                    />
                    <div style={{
                      display: 'none',
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      height: '100%',
                      alignItems: 'center',
                      justifyContent: 'center',
                      backgroundColor: 'var(--bg-color-6)',
                      color: '#999',
                      fontSize: '12px'
                    }}>
                      {t('common.loadFailed')}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div style={{
              padding: '20px',
              textAlign: 'center',
              color: 'var(--text-color-6)',
              fontSize: '12px',
              backgroundColor: 'var(--bg-color-6)',
              borderRadius: '6px',
            }}>
              {t('instant.chat.noImages')}
            </div>
          )}
        </div>
      )}
      {
        !last && (
          <div style={{
            height: '1px',
            backgroundColor: 'var(--border-color)',
            margin: '0px 20px'
          }}>
          </div>
        )
      }
    </div>
  );
};

export default CameraItem;
