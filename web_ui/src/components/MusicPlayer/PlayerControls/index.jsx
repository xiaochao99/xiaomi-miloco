import React, { useState } from 'react'
import { Button, Slider, Tooltip } from 'antd'
import {
  CaretRightOutlined, PauseOutlined,
  StepBackwardOutlined, StepForwardOutlined,
  SoundFilled, SoundOutlined,
  LoadingOutlined,
} from '@ant-design/icons'
import { useMusicPlayerStore, REPEAT_MODES, formatTime } from '@/stores/musicPlayerStore'
import styles from './index.module.less'

const RepeatIcon = ({ mode, size }) => {
  if (mode === REPEAT_MODES.SINGLE) {
    return (
      <svg width={size || 18} height={size || 18} viewBox="0 0 24 24" fill="currentColor">
        <path d="M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z" />
        <circle cx="12" cy="12" r="2" fill="currentColor" />
      </svg>
    )
  }
  if (mode === REPEAT_MODES.SHUFFLE) {
    return (
      <svg width={size || 18} height={size || 18} viewBox="0 0 24 24" fill="currentColor">
        <path d="M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm0.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z" />
      </svg>
    )
  }
  return (
    <svg width={size || 18} height={size || 18} viewBox="0 0 24 24" fill="currentColor">
      <path d="M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z" />
    </svg>
  )
}

const PlayerControls = () => {
  const {
    playbackState, position, duration,
    volume, isMuted, repeatMode,
    isControlling,
    play, pause, next, previous,
    seek, setVolume, toggleMute, cycleRepeatMode,
  } = useMusicPlayerStore()

  const [isDragging, setIsDragging] = useState(false)
  const [dragValue, setDragValue] = useState(0)
  const [showVolume, setShowVolume] = useState(false)

  const isPlaying = playbackState === 'playing'
  const isStopped = playbackState === 'stopped'

  const handleProgressChange = (value) => {
    setDragValue(value)
  }

  const handleProgressAfterChange = async (value) => {
    setIsDragging(false)
    await seek(value).catch(() => {})
  }

  const handleVolumeChange = async (value) => {
    await setVolume(value / 100).catch(() => {})
  }

  const currentProgress = isDragging ? dragValue : position

  return (
    <div className={styles.playerControls}>
      <div className={styles.progressSection}>
        <span className={styles.timeDisplay}>{formatTime(currentProgress)}</span>
        <div className={styles.progressWrapper}>
          <Slider
            className={styles.progressSlider}
            value={currentProgress}
            max={duration || 100}
            onChange={handleProgressChange}
            onAfterChange={handleProgressAfterChange}
            disabled={isStopped}
            tooltip={{ formatter: (v) => formatTime(v) }}
          />
        </div>
        <span className={styles.timeDisplay}>{formatTime(duration)}</span>
      </div>

      <div className={styles.mainControls}>
        <div className={styles.controlGroup}>
          <Tooltip title="上一首">
            <Button
              type="text"
              icon={<StepBackwardOutlined />}
              onClick={previous}
              className={styles.controlBtn}
              disabled={isControlling || isStopped}
            />
          </Tooltip>
        </div>

        <div className={styles.centerGroup}>
          <Tooltip title={`${repeatMode === REPEAT_MODES.SINGLE ? '单曲循环' : repeatMode === REPEAT_MODES.SHUFFLE ? '随机播放' : '列表循环'}`}>
            <Button
              type="text"
              icon={<RepeatIcon mode={repeatMode} />}
              onClick={cycleRepeatMode}
              className={`${styles.repeatBtn} ${
                repeatMode === REPEAT_MODES.SINGLE ? styles.singleActive :
                repeatMode === REPEAT_MODES.SHUFFLE ? styles.shuffleActive :
                styles.listActive
              }`}
              disabled={isControlling}
            />
          </Tooltip>

          <Button
            type="text"
            icon={isControlling ? <LoadingOutlined /> : (isPlaying ? <PauseOutlined /> : <CaretRightOutlined />)}
            onClick={() => isPlaying ? pause() : play()}
            className={styles.playBtn}
            disabled={isControlling}
          />

          <Tooltip title="下一首">
            <Button
              type="text"
              icon={<StepForwardOutlined />}
              onClick={next}
              className={styles.controlBtn}
              disabled={isControlling || isStopped}
            />
          </Tooltip>
        </div>

        <div className={styles.controlGroup}>
          <div
            className={styles.volumeWrapper}
            onMouseEnter={() => setShowVolume(true)}
            onMouseLeave={() => setShowVolume(false)}
          >
            <Tooltip title={isMuted ? '取消静音' : '静音'} placement="bottom">
              <Button
                type="text"
                icon={isMuted || volume === 0 ? <SoundOutlined /> : <SoundFilled />}
                onClick={toggleMute}
                className={styles.controlBtn}
                disabled={isControlling}
              />
            </Tooltip>
            <div className={`${styles.volumeSliderWrapper} ${showVolume ? styles.visible : ''}`}>
              <div className={styles.volumeSliderInner}>
                <Slider
                  value={isMuted ? 0 : volume * 100}
                  onChange={handleVolumeChange}
                  onAfterChange={handleVolumeChange}
                  className={styles.volumeSlider}
                  tooltip={{ formatter: null }}
                />
                <span className={styles.volumeValue}>
                  {isMuted ? '0' : Math.round(volume * 100)}%
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default PlayerControls
