import React, { useState, useEffect } from 'react'
import { useMusicPlayerStore } from '@/stores/musicPlayerStore'
import styles from './index.module.less'

const CastIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M2 16.1A5 5 0 015.9 20M2 12.05A9 9 0 019.95 20M2 8V6a2 2 0 012-2h16a2 2 0 012 2v12a2 2 0 01-2 2h-6" />
    <line x1="2" y1="20" x2="2.01" y2="20" />
  </svg>
)

const WifiIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M5 12.55a11 11 0 0114.08 0M1.42 9a16 16 0 0121.16 0M8.53 16.11a6 6 0 016.95 0M12 20h.01" />
  </svg>
)

const RefreshIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="23 4 23 10 17 10" />
    <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" />
  </svg>
)

const SpeakerIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
    <path d="M19.07 4.93a10 10 0 010 14.14M15.54 8.46a5 5 0 010 7.07" />
  </svg>
)

const CloseIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
)

const DLNADeviceSelector = () => {
  const {
    dlnaDevices, selectedDLNADevice, isDLNACasting, dlnaPlayState, dlnaLoading,
    loadDLNADevices, discoverDLNADevices, selectDLNADevice,
    castToDLNA, stopDLNACast, pauseDLNA, playDLNA, currentSong,
  } = useMusicPlayerStore()

  const [open, setOpen] = useState(false)

  useEffect(() => {
    loadDLNADevices()
  }, [loadDLNADevices])

  const handleRefresh = async (e) => {
    e?.stopPropagation()
    await discoverDLNADevices()
  }

  const handleDeviceSelect = async (device) => {
    selectDLNADevice(device)
    const songId = currentSong?.id || null
    const audioUrl = currentSong?.audio_url || null
    await castToDLNA(device.udn || device.id, songId, audioUrl)
    setOpen(false)
  }

  const handleStopCast = async (e) => {
    e?.stopPropagation()
    if (selectedDLNADevice) {
      await stopDLNACast(selectedDLNADevice.udn || selectedDLNADevice.id)
    }
  }

  const handleDlnaPlayPause = async (e) => {
    e?.stopPropagation()
    if (!selectedDLNADevice) return
    const deviceId = selectedDLNADevice.udn || selectedDLNADevice.id
    if (dlnaPlayState === 'playing') {
      await pauseDLNA(deviceId)
    } else {
      await playDLNA(deviceId)
    }
  }

  return (
    <div className={styles.container}>
      <button
        className={`${styles.castBtn} ${isDLNACasting ? styles.castBtnActive : ''}`}
        onClick={(e) => { e.stopPropagation(); setOpen(!open) }}
        title={isDLNACasting ? '投屏中' : '投屏'}
      >
        <CastIcon />
      </button>

      {open && (
        <>
          <div className={styles.backdrop} onClick={() => setOpen(false)} />
          <div className={styles.dropdown}>
            <div className={styles.dropdownInner}>
              {/* Header */}
              <div className={styles.header}>
                <div className={styles.headerLeft}>
                  <WifiIcon />
                  <span className={styles.headerTitle}>
                    {isDLNACasting && selectedDLNADevice
                      ? `已连接: ${selectedDLNADevice.name}`
                      : 'DLNA 设备'
                    }
                  </span>
                </div>
                <button
                  className={styles.refreshBtn}
                  onClick={handleRefresh}
                  disabled={dlnaLoading}
                  title="刷新设备"
                >
                  <RefreshIcon />
                </button>
              </div>

              {/* Device List */}
              {dlnaLoading ? (
                <div className={styles.loadingState}>
                  <span className={styles.spinner} />
                  <span className={styles.loadingText}>扫描中...</span>
                </div>
              ) : dlnaDevices.length === 0 ? (
                <div className={styles.emptyState}>
                  <p>未发现 DLNA 设备</p>
                  <button className={styles.rescanBtn} onClick={handleRefresh}>
                    重新扫描
                  </button>
                </div>
              ) : (
                <div className={styles.deviceList}>
                  {dlnaDevices.map((device) => {
                    const isSelected = selectedDLNADevice?.udn === device.udn
                    return (
                      <div
                        key={device.udn || device.id}
                        className={`${styles.deviceItem} ${isSelected ? styles.deviceItemSelected : ''}`}
                        onClick={() => handleDeviceSelect(device)}
                      >
                        <div className={styles.deviceIcon}>
                          <SpeakerIcon />
                        </div>
                        <div className={styles.deviceMeta}>
                          <span className={styles.deviceName}>{device.name}</span>
                          <span className={styles.deviceHost}>{device.host || device.ip || ''}</span>
                        </div>
                        {isSelected && isDLNACasting && (
                          <span className={styles.castingBadge}>投屏中</span>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}

              {/* Control Bar */}
              {isDLNACasting && selectedDLNADevice && (
                <div className={styles.controlBar}>
                  {currentSong && (
                    <div className={styles.nowPlaying}>
                      <span className={styles.nowPlayingLabel}>正在投屏</span>
                      <span className={styles.nowPlayingTitle}>{currentSong.title}</span>
                    </div>
                  )}
                  <div className={styles.controlActions}>
                    <button
                      className={styles.controlBtn}
                      onClick={handleDlnaPlayPause}
                    >
                      {dlnaPlayState === 'playing' ? '暂停' : '播放'}
                    </button>
                    <button
                      className={styles.stopBtn}
                      onClick={handleStopCast}
                    >
                      <CloseIcon />
                      <span>停止投屏</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default DLNADeviceSelector
