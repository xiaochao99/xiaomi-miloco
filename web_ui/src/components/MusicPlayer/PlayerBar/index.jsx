import React, { useState, useRef, useEffect } from 'react'
import { Tooltip } from 'antd'
import { useMusicPlayerStore, REPEAT_MODES } from '@/stores/musicPlayerStore'
import LazyImage from '@/components/MusicPlayer/LazyImage'
import DLNADeviceSelector from '@/components/MusicPlayer/DLNADeviceSelector'
import styles from './index.module.less'

const formatTime = (seconds) => {
  if (!seconds || isNaN(seconds)) return '00:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

// ─── SVG Icons ─────────────────────────────────────

const PlayIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
    <path d="M8 5v14l11-7z" />
  </svg>
)

const PauseIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
    <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
  </svg>
)

const PrevIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
    <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z" />
  </svg>
)

const NextIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
    <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z" />
  </svg>
)

const VolumeHighIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
    <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" />
  </svg>
)

const VolumeMuteIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
    <path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z" />
  </svg>
)

const RepeatListIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
    <path d="M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z" />
  </svg>
)

const RepeatSingleIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
    <path d="M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4zm-4-2V9h-1l-2 1v1h1.5v4H13z" />
  </svg>
)

const ShuffleIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
    <path d="M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z" />
  </svg>
)

const HeartIcon = ({ filled }) => filled ? (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="#ec4141">
    <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
  </svg>
) : (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
  </svg>
)

const PlaylistIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
    <path d="M15 6H3v2h12V6zm0 4H3v2h12v-2zM3 16h8v-2H3v2zM17 6v8.18c-.31-.11-.65-.18-1-.18-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3V8h3V6h-5z" />
  </svg>
)

const LoadingIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" className={styles.spinIcon}>
    <path d="M12 4V2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10h-2c0 4.41-3.59 8-8 8s-8-3.59-8-8 3.59-8 8-8z" opacity="0.3" />
    <path d="M12 2C6.48 2 2 6.48 2 12h2c0-4.41 3.59-8 8-8V2z" />
  </svg>
)

// ─── Repeat Button ─────────────────────────────────

const RepeatButton = ({ mode, onClick }) => {
  const configs = {
    [REPEAT_MODES.LIST]: { Icon: RepeatListIcon, title: '列表循环' },
    [REPEAT_MODES.SINGLE]: { Icon: RepeatSingleIcon, title: '单曲循环' },
    [REPEAT_MODES.SHUFFLE]: { Icon: ShuffleIcon, title: '随机播放' },
  }
  const config = configs[mode] || configs[REPEAT_MODES.LIST]
  return (
    <Tooltip title={config.title}>
      <button className={styles.iconBtn} onClick={onClick}>
        <config.Icon />
      </button>
    </Tooltip>
  )
}

// ─── PlayerBar Component ───────────────────────────

const PlayerBar = ({ onShowDetail, onTogglePlaylist }) => {
  const {
    playbackState, currentSong, position, duration,
    volume, isMuted, repeatMode, isControlling,
    togglePlay, next, previous, seek,
    setVolume, toggleMute, cycleRepeatMode,
    songs,
    favoriteIds,
    toggleFavorite,
  } = useMusicPlayerStore()

  const liked = currentSong?.id ? favoriteIds.includes(currentSong.id) : false
  const [showVolume, setShowVolume] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const progressRef = useRef(null)
  const volumeRef = useRef(null)

  const isPlaying = playbackState === 'playing'
  const hasSong = !!currentSong
  const coverUrl = currentSong?.cover_url
  const songTitle = currentSong?.title || '未播放'
  const songArtist = currentSong?.artist || ''

  // ─── Progress Bar ──────────────────────────────

  const handleProgressClick = (e) => {
    if (!hasSong || !progressRef.current) return
    const rect = progressRef.current.getBoundingClientRect()
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
    seek(ratio * (duration || 0))
  }

  const handleProgressMouseDown = (e) => {
    setIsDragging(true)
    handleProgressClick(e)
  }

  useEffect(() => {
    if (!isDragging) return
    const handleMove = (e) => handleProgressClick(e)
    const handleUp = () => setIsDragging(false)
    window.addEventListener('mousemove', handleMove)
    window.addEventListener('mouseup', handleUp)
    return () => {
      window.removeEventListener('mousemove', handleMove)
      window.removeEventListener('mouseup', handleUp)
    }
  }, [isDragging, duration])

  const progressPercent = duration > 0 ? (position / duration) * 100 : 0

  // ─── Volume ────────────────────────────────────

  const handleVolumeClick = (e) => {
    if (!volumeRef.current) return
    const rect = volumeRef.current.getBoundingClientRect()
    const ratio = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height))
    setVolume(1 - ratio)
  }

  const displayVolume = isMuted ? 0 : volume

  return (
    <div className={styles.playerBar}>
      {/* Left: Cover + Info */}
      <div className={styles.leftSection}>
        <div
          className={`${styles.albumDisc} ${isPlaying ? styles.spinning : ''}`}
          onClick={() => hasSong && onShowDetail?.()}
        >
          {coverUrl ? (
            <LazyImage src={coverUrl} alt="" className={styles.albumImg} key={coverUrl} rootMargin="0px" />
          ) : (
            <div className={styles.albumPlaceholder}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="12" cy="12" r="10" />
                <circle cx="12" cy="12" r="3" />
              </svg>
            </div>
          )}
        </div>
        <div className={styles.songInfo}>
          <div className={styles.songTitle} onClick={() => hasSong && onShowDetail?.()}>
            {songTitle}
          </div>
          <div className={styles.songArtist}>{songArtist || '未知歌手'}</div>
        </div>
        <Tooltip title={liked ? '取消喜欢' : '喜欢'}>
          <button
            className={styles.iconBtn}
            onClick={() => currentSong?.id && toggleFavorite(currentSong.id)}
            disabled={!hasSong}
          >
            <HeartIcon filled={liked} />
          </button>
        </Tooltip>
      </div>

      {/* Center: Controls + Progress */}
      <div className={styles.centerSection}>
        <div className={styles.controlsRow}>
          <RepeatButton mode={repeatMode} onClick={cycleRepeatMode} />
          <Tooltip title="上一首">
            <button className={styles.iconBtn} onClick={previous} disabled={songs.length === 0}>
              <PrevIcon />
            </button>
          </Tooltip>
          <button
            className={styles.playBtn}
            onClick={togglePlay}
            disabled={isControlling}
          >
            {isControlling ? <LoadingIcon /> : isPlaying ? <PauseIcon /> : <PlayIcon />}
          </button>
          <Tooltip title="下一首">
            <button className={styles.iconBtn} onClick={next} disabled={songs.length === 0}>
              <NextIcon />
            </button>
          </Tooltip>
          <div className={styles.placeholder} />
        </div>
        <div className={styles.progressRow}>
          <span className={styles.timeLabel}>{formatTime(position)}</span>
          <div
            className={styles.progressTrack}
            ref={progressRef}
            onMouseDown={handleProgressMouseDown}
          >
            <div className={styles.progressFill} style={{ width: `${progressPercent}%` }} />
            <div
              className={styles.progressThumb}
              style={{ left: `${progressPercent}%` }}
            />
          </div>
          <span className={styles.timeLabel}>{formatTime(duration)}</span>
        </div>
      </div>

      {/* Right: DLNA + Volume + Playlist */}
      <div className={styles.rightSection}>
        <DLNADeviceSelector />
        <div
          className={styles.volumeWrapper}
          onMouseEnter={() => setShowVolume(true)}
          onMouseLeave={() => setShowVolume(false)}
        >
          <Tooltip title={isMuted ? '取消静音' : '静音'}>
            <button className={styles.iconBtn} onClick={toggleMute}>
              {isMuted || volume === 0 ? <VolumeMuteIcon /> : <VolumeHighIcon />}
            </button>
          </Tooltip>
          <div className={`${styles.volumePopup} ${showVolume ? styles.visible : ''}`}>
            <div className={styles.volumeInner}>
              <div
                className={styles.volumeTrack}
                ref={volumeRef}
                onClick={handleVolumeClick}
              >
                <div className={styles.volumeFill} style={{ height: `${displayVolume * 100}%` }} />
                <div className={styles.volumeThumb} style={{ bottom: `${displayVolume * 100}%` }} />
              </div>
              <span className={styles.volumeText}>
                {Math.round(displayVolume * 100)}
              </span>
            </div>
          </div>
        </div>
        <Tooltip title="播放列表">
          <button className={styles.iconBtn} onClick={onTogglePlaylist}>
            <PlaylistIcon />
            {songs.length > 0 && (
              <span className={styles.songCount}>{songs.length}</span>
            )}
          </button>
        </Tooltip>
      </div>
    </div>
  )
}

export default PlayerBar
