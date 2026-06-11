import React, { useEffect, useState, useCallback } from 'react'
import { Spin, Tooltip } from 'antd'
import LazyImage from '@/components/MusicPlayer/LazyImage'
import { PlayCircleFilled } from '@ant-design/icons'
import { useMusicPlayerStore } from '@/stores/musicPlayerStore'
import * as musicApi from '@/api/musicApi'
import styles from './index.module.less'

const RANKING_CATEGORIES = [
  { key: 'hot', label: '热歌榜', keyword: '热歌' },
  { key: 'new', label: '新歌榜', keyword: '新歌' },
  { key: 'rising', label: '飙升榜', keyword: '飙升' },
  { key: 'electronic', label: '电音榜', keyword: '电音' },
  { key: 'hiphop', label: '说唱榜', keyword: '说唱' },
  { key: 'classic', label: '经典榜', keyword: '经典老歌' },
]

const RankingView = () => {
  const [activeCategory, setActiveCategory] = useState('hot')
  const [rankings, setRankings] = useState({})
  const [loading, setLoading] = useState(false)

  const currentSong = useMusicPlayerStore((s) => s.currentSong)
  const playbackState = useMusicPlayerStore((s) => s.playbackState)
  const { playSong, addToPlaylist, playAll } = useMusicPlayerStore()

  const loadRanking = useCallback(async (categoryKey) => {
    const cat = RANKING_CATEGORIES.find((c) => c.key === categoryKey)
    if (!cat) return
    if (rankings[categoryKey]) return

    setLoading(true)
    try {
      const results = await musicApi.searchSongs(cat.keyword, { count: 30 })
      const withCovers = await musicApi.batchBuildCoverUrls(results.slice(0, 8))
      const songs = [...withCovers, ...results.slice(8)]
      setRankings((prev) => ({ ...prev, [categoryKey]: songs }))
    } catch (e) {
      console.error('Load ranking failed:', e)
    } finally {
      setLoading(false)
    }
  }, [rankings])

  useEffect(() => {
    loadRanking(activeCategory)
  }, [activeCategory, loadRanking])

  const handleCategoryClick = (key) => {
    setActiveCategory(key)
  }

  const handlePlaySong = (song) => {
    playSong(song)
  }

  const songs = rankings[activeCategory] || []
  const activeCat = RANKING_CATEGORIES.find((c) => c.key === activeCategory)

  return (
    <div className={styles.container}>
      {/* Category Tabs */}
      <div className={styles.categoryBar}>
        {RANKING_CATEGORIES.map((cat) => (
          <button
            key={cat.key}
            className={`${styles.categoryBtn} ${activeCategory === cat.key ? styles.categoryActive : ''}`}
            onClick={() => handleCategoryClick(cat.key)}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Ranking Header */}
      <div className={styles.rankingHeader}>
        <div className={styles.rankingTitle}>
          <span className={styles.rankingIcon}>🏆</span>
          <span>{activeCat?.label || '排行榜'}</span>
        </div>
        <div className={styles.rankingRight}>
          <span className={styles.rankingCount}>{songs.length} 首</span>
          {songs.length > 0 && (
            <button className={styles.playAllBtn} onClick={() => playAll(songs)}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <path d="M8 5v14l11-7z" />
              </svg>
              <span>全部播放</span>
            </button>
          )}
        </div>
      </div>

      {/* Song List */}
      {loading && songs.length === 0 ? (
        <div className={styles.loadingState}>
          <Spin />
        </div>
      ) : songs.length > 0 ? (
        <div className={styles.songList}>
          {songs.map((song, index) => {
            const isCurrent = currentSong?.id === song.id
            const isPlaying = isCurrent && playbackState === 'playing'
            const rank = index + 1

            return (
              <div
                key={`${song.id}-${index}`}
                className={`${styles.songItem} ${isCurrent ? styles.songItemActive : ''}`}
                onClick={() => handlePlaySong(song)}
              >
                <div className={`${styles.rankBadge} ${rank <= 3 ? styles.rankTop : ''}`}>
                  {isCurrent && isPlaying ? (
                    <div className={styles.playingBars}>
                      <span /><span /><span />
                    </div>
                  ) : (
                    <span>{rank}</span>
                  )}
                </div>

                <div className={styles.songCover}>
                  {song.cover_url ? (
                    <LazyImage
                      src={song.cover_url}
                      alt={song.title}
                      className={styles.coverImg}
                      fallback={
                        <div className={styles.coverPlaceholder}>
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <circle cx="12" cy="12" r="10" />
                            <circle cx="12" cy="12" r="3" />
                          </svg>
                        </div>
                      }
                    />
                  ) : (
                    <div className={styles.coverPlaceholder}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <circle cx="12" cy="12" r="10" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    </div>
                  )}
                  <div className={styles.coverOverlay}>
                    <PlayCircleFilled />
                  </div>
                </div>

                <div className={styles.songInfo}>
                  <div className={styles.songTitle}>{song.title}</div>
                  <div className={styles.songMeta}>
                    <span className={styles.songArtist}>{song.artist}</span>
                    <span className={styles.songSep}>-</span>
                    <span className={styles.songAlbum}>{song.album}</span>
                  </div>
                </div>

                <Tooltip title="添加到播放列表">
                  <button
                    className={styles.addBtn}
                    onClick={(e) => { e.stopPropagation(); addToPlaylist(song) }}
                  >
                    +
                  </button>
                </Tooltip>
              </div>
            )
          })}
        </div>
      ) : (
        <div className={styles.emptyState}>
          <p>暂无数据</p>
        </div>
      )}
    </div>
  )
}

export default RankingView
