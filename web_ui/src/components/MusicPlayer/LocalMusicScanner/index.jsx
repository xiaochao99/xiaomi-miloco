import React from 'react'
import { useMusicPlayerStore } from '@/stores/musicPlayerStore'
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
  const playSong = useMusicPlayerStore((s) => s.playSong)
  const playAll = useMusicPlayerStore((s) => s.playAll)

  const localSongs = library.filter((s) => String(s.id).startsWith('local_'))
  // Mark which ones are in the play queue
  const playlistIds = new Set(songs.map(s => s.id))

  const handlePlay = (song) => {
    playSong(song)
  }

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
                    <img
                      src={song.cover_url}
                      alt=""
                      onError={(e) => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex' }}
                    />
                  ) : null}
                  <div className={styles.songCoverPlaceholder} style={song.cover_url ? { display: 'none' } : {}}>
                    <MusicIcon />
                  </div>
                </div>
                <div className={styles.songInfo}>
                  <div className={styles.songTitle}>{song.title}</div>
                  <div className={styles.songArtist}>{song.artist} — {song.album}</div>
                </div>
                <span className={styles.songDuration}>{formatDuration(song.duration)}</span>
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
