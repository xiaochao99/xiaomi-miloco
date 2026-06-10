import React, { useRef, useEffect } from 'react'
import { Empty } from 'antd'
import { useMusicPlayerStore } from '@/stores/musicPlayerStore'
import styles from './index.module.less'

const LyricsPanel = () => {
  const { lyrics, currentLyricIndex, seek } = useMusicPlayerStore()
  const containerRef = useRef(null)
  const activeRef = useRef(null)

  useEffect(() => {
    if (activeRef.current && containerRef.current) {
      const container = containerRef.current
      const active = activeRef.current
      const containerRect = container.getBoundingClientRect()
      const activeRect = active.getBoundingClientRect()
      const offset = activeRect.top - containerRect.top - containerRect.height / 2 + activeRect.height / 2
      container.scrollTo({
        top: container.scrollTop + offset,
        behavior: 'smooth',
      })
    }
  }, [currentLyricIndex])

  if (!lyrics || lyrics.length === 0) {
    return (
      <div className={styles.lyricsPanel}>
        <div className={styles.emptyState}>
          <div className={styles.emptyIcon}>
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="1">
              <path d="M9 18V5l12-2v13" />
              <circle cx="6" cy="18" r="3" />
              <circle cx="18" cy="16" r="3" />
            </svg>
          </div>
          <span className={styles.emptyText}>暂无歌词</span>
          <span className={styles.emptyHint}>等待音乐开始...</span>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.lyricsPanel} ref={containerRef}>
      <div className={styles.lyricsPadding} />
      {lyrics.map((lyric, index) => (
        <div
          key={index}
          ref={index === currentLyricIndex ? activeRef : null}
          className={`${styles.lyricLine} ${index === currentLyricIndex ? styles.active : ''} ${index < currentLyricIndex ? styles.passed : ''}`}
          onClick={() => seek(lyric.time)}
        >
          <span className={styles.lyricText}>{lyric.text || '♪'}</span>
          {index === currentLyricIndex && (
            <span className={styles.lyricHighlight} />
          )}
        </div>
      ))}
      <div className={styles.lyricsPadding} />
    </div>
  )
}

export default LyricsPanel
