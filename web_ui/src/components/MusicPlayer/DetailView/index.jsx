import React, { useRef, useEffect } from 'react'
import { Empty } from 'antd'
import { useMusicPlayerStore } from '@/stores/musicPlayerStore'
import styles from './index.module.less'

const CloseIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M19 12H5M12 19l-7-7 7-7" />
  </svg>
)

const MusicIcon = () => (
  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="1">
    <circle cx="12" cy="12" r="10" />
    <circle cx="12" cy="12" r="3" />
  </svg>
)

const LyricsIcon = () => (
  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="1">
    <path d="M9 18V5l12-2v13" />
    <circle cx="6" cy="18" r="3" />
    <circle cx="18" cy="16" r="3" />
  </svg>
)

const DetailView = ({ onClose }) => {
  const {
    currentSong, playbackState,
    lyrics, currentLyricIndex, seek,
  } = useMusicPlayerStore()

  const lyricsRef = useRef(null)
  const activeRef = useRef(null)

  useEffect(() => {
    if (activeRef.current && lyricsRef.current) {
      const container = lyricsRef.current
      const active = activeRef.current
      const containerRect = container.getBoundingClientRect()
      const activeRect = active.getBoundingClientRect()
      const offset = activeRect.top - containerRect.top - containerRect.height / 2 + activeRect.height / 2
      container.scrollTo({ top: container.scrollTop + offset, behavior: 'smooth' })
    }
  }, [currentLyricIndex])

  if (!currentSong) {
    return (
      <div className={styles.emptyDetail}>
        <Empty description="未播放任何歌曲" />
      </div>
    )
  }

  const isPlaying = playbackState === 'playing'
  const coverUrl = currentSong.cover_url
  const hasLyrics = lyrics && lyrics.length > 0

  return (
    <div className={styles.detailContainer}>
      {/* Blurred Background */}
      {coverUrl && (
        <div className={styles.bgBlur}>
          <img src={coverUrl} alt="" />
        </div>
      )}

      {/* Close Button */}
      {onClose && (
        <button className={styles.closeBtn} onClick={onClose}>
          <CloseIcon />
        </button>
      )}

      <div className={styles.detailContent}>
        {/* Left: Vinyl Disc */}
        <div className={styles.jukeboxSection}>
          <div className={styles.jukebox}>
            <div className={styles.discOuter}>
              <div className={`${styles.discInner} ${isPlaying ? styles.spinning : ''}`}>
                {coverUrl ? (
                  <img src={coverUrl} alt="" className={styles.discImg} />
                ) : (
                  <div className={styles.discPlaceholder}>
                    <MusicIcon />
                  </div>
                )}
              </div>
            </div>
            <div className={styles.songMeta}>
              <h2 className={styles.detailTitle}>{currentSong.title}</h2>
              <p className={styles.detailArtist}>{currentSong.artist}</p>
              {currentSong.album && (
                <p className={styles.detailAlbum}>{currentSong.album}</p>
              )}
            </div>
          </div>
        </div>

        {/* Right: Lyrics */}
        <div className={styles.lyricsSection}>
          {hasLyrics ? (
            <div className={styles.lyricsPanel} ref={lyricsRef}>
              <div className={styles.lyricsPad} />
              {lyrics.map((line, index) => (
                <div
                  key={index}
                  ref={index === currentLyricIndex ? activeRef : null}
                  className={`${styles.lyricLine} ${index === currentLyricIndex ? styles.lyricActive : ''} ${index < currentLyricIndex ? styles.lyricPassed : ''}`}
                  onClick={() => seek(line.time)}
                >
                  {line.text}
                </div>
              ))}
              <div className={styles.lyricsPad} />
            </div>
          ) : (
            <div className={styles.noLyrics}>
              <LyricsIcon />
              <span>暂无歌词</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default DetailView
