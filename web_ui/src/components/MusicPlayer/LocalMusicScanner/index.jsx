import React from 'react'
import { useMusicPlayerStore } from '@/stores/musicPlayerStore'
import LazyImage from '@/components/MusicPlayer/LazyImage'
import styles from './index.module.less'

const PlayAllIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
    <path d="M8 5v14l11-7z" />
  </svg>
)

const PlayIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
    <path d="M8 5v14l11-7z" />
  </svg>
)

const MusicIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <circle cx="12" cy="12" r="10" />
    <circle cx="12" cy="12" r="3" />
  </svg>
)

const HeartIcon = ({ filled }) => filled ? (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="#ec4141"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>
) : (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
)

const FolderIcon = () => (
  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="1.5">
    <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" />
  </svg>
)

const formatDuration = (seconds) => {
  if (!seconds || isNaN(seconds)) return '--:--'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

const LocalMusicList = () => {
  const songs = useMusicPlayerStore((s) => s.songs)
  const library = useMusicPlayerStore((s) => s.library)
  const currentSong = useMusicPlayerStore((s) => s.currentSong)
  const playbackState = useMusicPlayerStore((s) => s.playbackState)
  const displayMode = useMusicPlayerStore((s) => s.displayModes['local'] || 'list')
  const favoriteIds = useMusicPlayerStore((s) => s.favoriteIds)
  const playSong = useMusicPlayerStore((s) => s.playSong)
  const playAll = useMusicPlayerStore((s) => s.playAll)
  const toggleFavorite = useMusicPlayerStore((s) => s.toggleFavorite)
  const addToPlaylist = useMusicPlayerStore((s) => s.addToPlaylist)

  const localSongs = library.filter((s) => String(s.id).startsWith('local_'))
  const isCard = displayMode === 'card'

  const handlePlay = (song) => playSong(song)

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h3 className={styles.title}>本地音乐</h3>
        <div className={styles.headerRight}>
          <span className={styles.count}>{localSongs.length} 首</span>
          {localSongs.length > 0 && (
            <button className={styles.playAllBtn} onClick={() => playAll(localSongs)}>
              <PlayAllIcon />
              <span>全部播放</span>
            </button>
          )}
        </div>
      </div>

      {localSongs.length > 0 ? (
        isCard ? (
          <div className={styles.cardGrid}>
            {localSongs.map((song) => {
              const isCurrent = currentSong?.id === song.id
              const isPlaying = isCurrent && playbackState === 'playing'
              return (
                <div key={song.id} className={`${styles.cardItem} ${isCurrent ? styles.cardItemActive : ''}`}
                  onClick={() => handlePlay(song)}>
                  <div className={styles.cardCover}>
                    {song.cover_url ? (
                      <LazyImage src={song.cover_url} alt={song.title}
                        fallback={<div className={styles.cardCoverPlaceholder}><MusicIcon/></div>} />
                    ) : (
                      <div className={styles.cardCoverPlaceholder}><MusicIcon/></div>
                    )}
                    <button className={`${styles.cardPlayBtn} ${isPlaying ? styles.cardPlayBtnActive : ''}`}
                      onClick={(e) => { e.stopPropagation(); handlePlay(song) }}>
                      {isPlaying ? (
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                      ) : <PlayAllIcon />}
                    </button>
                  </div>
                  <div className={styles.cardInfo}>
                    <div className={styles.cardTitle}>{song.title}</div>
                    <div className={styles.cardArtist}>{song.artist}</div>
                  </div>
                  <div className={styles.cardActions}>
                    <button className={styles.cardAddBtn} title="添加到播放列表"
                      onClick={(e) => { e.stopPropagation(); addToPlaylist(song) }}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
                      </svg>
                    </button>
                    <button className={`${styles.cardHeart} ${favoriteIds.includes(song.id) ? styles.cardHeartLiked : ''}`}
                      onClick={(e) => { e.stopPropagation(); toggleFavorite(song.id) }}>
                      <HeartIcon filled={favoriteIds.includes(song.id)}/>
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
        <div className={styles.songList}>
          {localSongs.map((song) => {
            const isCurrent = currentSong?.id === song.id
            const isPlaying = isCurrent && playbackState === 'playing'
            return (
              <div
                key={song.id}
                className={`${styles.songItem} ${isCurrent ? styles.songItemActive : ''}`}
                onClick={() => handlePlay(song)}
              >
                <div className={styles.songCover}>
                  {song.cover_url ? (
                    <LazyImage
                      src={song.cover_url}
                      alt={song.title}
                      fallback={
                        <div className={styles.songCoverPlaceholder}>
                          <MusicIcon />
                        </div>
                      }
                    />
                  ) : (
                    <div className={styles.songCoverPlaceholder}>
                      <MusicIcon />
                    </div>
                  )}
                </div>
                <div className={styles.songInfo}>
                  <div className={styles.songTitle}>{song.title}</div>
                  <div className={styles.songArtist}>{song.artist} — {song.album}</div>
                </div>
                <span className={styles.songDuration}>{formatDuration(song.duration)}</span>
                <button className={styles.addToListBtn} title="添加到播放列表"
                  onClick={(e) => { e.stopPropagation(); addToPlaylist(song) }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
                  </svg>
                </button>
                <button
                  className={styles.playBtn}
                  onClick={(e) => { e.stopPropagation(); handlePlay(song) }}
                >
                  {isPlaying ? (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
                    </svg>
                  ) : (
                    <PlayIcon />
                  )}
                </button>
              </div>
            )
          })}
        </div>
        )
      ) : (
        <div className={styles.empty}>
          <FolderIcon />
          <p>暂无本地音乐</p>
          <p className={styles.emptyHint}>请先在「设置」中扫描本地目录</p>
        </div>
      )}
    </div>
  )
}

export default LocalMusicList
