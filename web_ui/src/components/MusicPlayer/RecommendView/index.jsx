import React, { useEffect, useCallback } from 'react'
import { Spin, Tooltip } from 'antd'
import LazyImage from '@/components/MusicPlayer/LazyImage'
import {
  PlayCircleFilled,
  PlayCircleOutlined,
} from '@ant-design/icons'
import { useMusicPlayerStore } from '@/stores/musicPlayerStore'
import styles from './index.module.less'

const RecommendView = () => {
  const {
    recommendSeeds,
    recommendLoading,
    currentRecommendKey,
    loadRecommendSeeds,
    loadRecommendSongs,
    getActiveRecommendSongs,
    playSong,
    addToPlaylist,
    playAll,
  } = useMusicPlayerStore()

  const currentSong = useMusicPlayerStore((s) => s.currentSong)
  const playbackState = useMusicPlayerStore((s) => s.playbackState)

  useEffect(() => {
    loadRecommendSeeds()
  }, [loadRecommendSeeds])

  const handleSeedClick = useCallback((keyword) => {
    loadRecommendSongs(keyword)
  }, [loadRecommendSongs])

  const handlePlaySong = useCallback((song) => {
    playSong(song)
  }, [playSong])

  const handleAddToPlaylist = useCallback((e, song) => {
    e.stopPropagation()
    addToPlaylist(song)
  }, [addToPlaylist])

  const songs = getActiveRecommendSongs()
  const activeSeed = recommendSeeds.find((s) => s.keyword === currentRecommendKey)

  return (
    <div className={styles.container}>
      {/* Seed Tags */}
      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>推荐歌手</h3>
        <div className={styles.seedGrid}>
          {recommendSeeds.map((seed) => (
            <div
              key={seed.keyword}
              className={`${styles.seedCard} ${currentRecommendKey === seed.keyword ? styles.seedActive : ''}`}
              style={{ '--seed-color': seed.color }}
              onClick={() => handleSeedClick(seed.keyword)}
            >
              <div className={styles.seedBg} />
              <span className={styles.seedLabel}>{seed.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Song List */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <h3 className={styles.sectionTitle}>
            {activeSeed ? activeSeed.label : '推荐歌曲'}
          </h3>
          <div className={styles.sectionRight}>
            {recommendLoading && <Spin size="small" />}
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

        {songs.length > 0 ? (
          <div className={styles.songList}>
            {songs.map((song, index) => {
              const isCurrent = currentSong?.id === song.id
              const isPlaying = isCurrent && playbackState === 'playing'

              return (
                <div
                  key={`${song.id}-${index}`}
                  className={`${styles.songItem} ${isCurrent ? styles.songItemActive : ''}`}
                  onClick={() => handlePlaySong(song)}
                >
                  <div className={styles.songIndex}>
                    {isCurrent && isPlaying ? (
                      <div className={styles.playingBars}>
                        <span /><span /><span />
                      </div>
                    ) : (
                      <span className={styles.indexNum}>{index + 1}</span>
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
                    <div className={styles.songArtist}>{song.artist}</div>
                  </div>

                  <div className={styles.songAlbum}>{song.album}</div>

                  <div className={styles.songActions}>
                    <Tooltip title="添加到播放列表">
                      <button
                        className={styles.addBtn}
                        onClick={(e) => handleAddToPlaylist(e, song)}
                      >
                        +
                      </button>
                    </Tooltip>
                  </div>
                </div>
              )
            })}
          </div>
        ) : !recommendLoading ? (
          <div className={styles.emptyState}>
            <p>选择上方标签发现音乐</p>
          </div>
        ) : (
          <div className={styles.loadingState}>
            <Spin />
          </div>
        )}
      </div>
    </div>
  )
}

export default RecommendView
