/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react'
import { Checkbox } from 'antd'
import { useTranslation } from 'react-i18next';
import { CloseOutlined } from '@ant-design/icons'
import { Icon } from '@/components';
import DeviceItem from '../DeviceItem'
import { useChatStore } from '@/stores/chatStore'
import styles from './index.module.less'

/**
 * DeviceList Component - List of camera devices with refresh and close functionality
 * 设备列表组件 - 带有刷新和关闭功能的摄像头设备列表
 *
 * @param {Object} props - Component props
 * @param {Array} props.cameraList - Array of camera device objects
 * @param {Function} props.onPlay - Play callback function for device items
 * @param {Array} props.currentPlayingId - Array of currently playing device IDs
 * @param {Function} props.onRefresh - Refresh callback function
 * @param {Function} props.onClose - Close callback function
 * @returns {JSX.Element} Device list component
 */
const DeviceList = ({ cameraList, onPlay, currentPlayingId, onRefresh, onClose }) => {
  const { t } = useTranslation();
  const { isRefreshing } = useChatStore();
  return (
    <div className={styles.deviceListWrap}>
      <div className={styles.titleWrap}>
        <span>{t('instant.deviceList.cameraList')}</span>
        <Icon
          name="refresh"
          className={`${styles.update} ${isRefreshing ? styles.rotating : ''}`}
          size={16}
          onClick={() => {
            if(isRefreshing) {return;}
            onRefresh();
          }}
        />
        <Icon name="arrowLeft"
          className={styles.closeIcon}
          size={16} onClick={() => {
            onClose()
          }} />
      </div>
      <div className={styles.listWrap}>
        {cameraList.map(item => (
          <DeviceItem
            key={item.did}
            item={item}
            onPlay={() => onPlay(item)}
            playing={currentPlayingId.includes(item.did)}
          />
        ))}
      </div>
    </div>
  )
}

export default DeviceList
