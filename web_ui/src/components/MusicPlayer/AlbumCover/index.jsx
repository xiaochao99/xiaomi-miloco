import React, { useState } from 'react'
import { Image, Modal } from 'antd'
import { useMusicPlayerStore } from '@/stores/musicPlayerStore'
import styles from './index.module.less'

const AlbumCover = () => {
  const { currentSong, playbackState } = useMusicPlayerStore()
  const [previewVisible, setPreviewVisible] = useState(false)

  const coverUrl = currentSong?.cover_url || ''
  const isPlaying = playbackState === 'playing'
  const noCover = !currentSong

  return (
    <div className={styles.albumCoverContainer}>
      <div
        className={`${styles.coverOuter} ${isPlaying ? styles.playing : ''} ${noCover ? styles.noCover : ''}`}
        onClick={() => !noCover && setPreviewVisible(true)}
      >
        <div className={styles.coverShadow} />
        <div className={styles.coverTurntable}>
          <div className={styles.coverVinyl}>
            {noCover ? (
              <div className={styles.placeholderCover}>
                <div className={styles.placeholderIcon}>
                  <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth="1.5">
                    <circle cx="12" cy="12" r="10" />
                    <circle cx="12" cy="12" r="3" />
                    <line x1="12" y1="2" x2="12" y2="7" />
                    <line x1="12" y1="17" x2="12" y2="22" />
                    <line x1="2" y1="12" x2="7" y2="12" />
                    <line x1="17" y1="12" x2="22" y2="12" />
                  </svg>
                </div>
                <div className={styles.placeholderText}>未播放</div>
              </div>
            ) : (
              <Image
                src={coverUrl}
                alt={currentSong?.title || 'Cover'}
                className={styles.coverImage}
                preview={false}
                fallback="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='280' height='280'%3E%3Crect fill='%23333' width='280' height='280'/%3E%3C/svg%3E"
              />
            )}
          </div>
          <div className={styles.coverCenterPin} />
        </div>
        <div className={styles.toneArm}>
          <div className={styles.toneArmBase} />
          <div className={styles.toneArmBar} />
          <div className={styles.toneArmHead} />
        </div>
      </div>

      {isPlaying && (
        <div className={styles.playingIndicator}>
          <span className={styles.bar} style={{ animationDelay: '0s' }} />
          <span className={styles.bar} style={{ animationDelay: '0.15s' }} />
          <span className={styles.bar} style={{ animationDelay: '0.3s' }} />
          <span className={styles.bar} style={{ animationDelay: '0.45s' }} />
          <span className={styles.bar} style={{ animationDelay: '0.6s' }} />
        </div>
      )}

      <div className={styles.songInfo}>
        <div className={styles.songTitleWrapper}>
          <h3 className={styles.songTitle}>{currentSong?.title || '未播放'}</h3>
        </div>
        <p className={styles.songArtist}>{currentSong?.artist || ' '}</p>
        <p className={styles.songAlbum}>{currentSong?.album || ' '}</p>
      </div>

      <Modal
        open={previewVisible}
        onCancel={() => setPreviewVisible(false)}
        footer={null}
        width={420}
        centered
        className={styles.previewModal}
      >
        {currentSong?.cover_url && (
          <Image
            src={currentSong.cover_url}
            alt={currentSong.title || 'Cover'}
            width="100%"
            preview={false}
          />
        )}
      </Modal>
    </div>
  )
}

export default AlbumCover
