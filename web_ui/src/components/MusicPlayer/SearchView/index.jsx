import React, { useMemo, useEffect, useState } from 'react'
import { Spin } from 'antd'
import { useMusicPlayerStore } from '@/stores/musicPlayerStore'
import * as musicApi from '@/api/musicApi'
import LazyImage from '@/components/MusicPlayer/LazyImage'
import styles from './index.module.less'

const formatDuration = (seconds) => {
  if (!seconds || isNaN(seconds)) return '--:--'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

const MusicIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="3" />
  </svg>
)

const PlayIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
    <path d="M8 5v14l11-7z" />
  </svg>
)

const HeartIcon = ({ filled }) => filled ? (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="#ec4141"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" /></svg>
) : (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" /></svg>
)

const ArtistIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </svg>
)

const AlbumIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="2" />
  </svg>
)

const SearchView = ({ keyword }) => {
  const {
    library, categories, currentSong, playbackState,
    playSong, playAll, toggleFavorite, addToPlaylist, favoriteIds,
    onlineMusicEnabled,
  } = useMusicPlayerStore()

  const [onlineResults, setOnlineResults] = useState([])
  const [onlineLoading, setOnlineLoading] = useState(false)

  const kwLower = (keyword || '').toLowerCase()

  // Online search with cover enrichment
  useEffect(() => {
    if (!keyword?.trim() || !onlineMusicEnabled) {
      setOnlineResults([])
      return
    }
    let cancelled = false
    setOnlineLoading(true)
    musicApi.searchSongs(keyword.trim(), { count: 20 }).then(async (results) => {
      if (cancelled) return
      const enriched = await musicApi.batchBuildCoverUrls(results || [])
      if (!cancelled) setOnlineResults(enriched)
    }).catch(() => {
      if (!cancelled) setOnlineResults([])
    }).finally(() => {
      if (!cancelled) setOnlineLoading(false)
    })
    return () => { cancelled = true }
  }, [keyword, onlineMusicEnabled])

  const sortByNameRelevance = (items, kw) => {
    return [...items].sort((a, b) => {
      const scoreA = (a.name || '').toLowerCase().includes(kw) ? 1 : 0
      const scoreB = (b.name || '').toLowerCase().includes(kw) ? 1 : 0
      return scoreB - scoreA
    })
  }

  // Local search: always filter library directly (no store dependency)
  const results = useMemo(() => {
    if (!kwLower) return { songs: [], artists: [], albums: [] }

    const localSongs = library.filter(s => String(s.id).startsWith('local_'))

    const matchedSongs = localSongs.filter(s =>
      (s.title || '').toLowerCase().includes(kwLower) ||
      (s.artist || '').toLowerCase().includes(kwLower) ||
      (s.album || '').toLowerCase().includes(kwLower)
    )

    const matchedArtists = (categories.artists || []).filter(a =>
      a.name.toLowerCase().includes(kwLower)
    ).map(a => ({
      ...a,
      songs: localSongs.filter(s => (s.artist || '未知艺术家') === a.name)
    }))

    const matchedAlbums = (categories.albums || []).filter(a =>
      a.name.toLowerCase().includes(kwLower)
    ).map(a => ({
      ...a,
      songs: localSongs.filter(s => (s.album || '未知专辑') === a.name),
      coverSong: localSongs.find(s => (s.album || '未知专辑') === a.name && s.cover_url)
    }))

    return {
      songs: matchedSongs,
      artists: sortByNameRelevance(matchedArtists, kwLower),
      albums: sortByNameRelevance(matchedAlbums, kwLower)
    }
  }, [library, categories, kwLower])

  const totalLocal = results.songs.length + results.artists.length + results.albums.length
  const hasResults = totalLocal > 0 || (onlineMusicEnabled && (onlineResults.length > 0 || onlineLoading))

  if (!keyword) return null

  return (
    <div className={styles.container}>
      {/* ─── 本地歌曲 ─── */}
      {results.songs.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <div className={styles.sectionTitle}>
              <MusicIcon />
              <span>本地歌曲</span>
            </div>
            <span className={styles.sectionCount}>{results.songs.length} 首</span>
            <button className={styles.playAllBtn} onClick={() => playAll(results.songs)}>
              <PlayIcon />
              <span>播放全部</span>
            </button>
          </div>
          <div className={styles.songList}>
            {results.songs.map((song, i) => {
              const isCurrent = currentSong?.id === song.id
              const isPlaying = isCurrent && playbackState === 'playing'
              return (
                <div
                  key={song.id}
                  className={`${styles.songItem} ${isCurrent ? styles.songItemActive : ''}`}
                  onClick={() => playSong(song)}
                >
                  <div className={styles.songIndex}>
                    {isPlaying ? (
                      <div className={styles.playingBars}><span /><span /><span /></div>
                    ) : (
                      <span>{i + 1}</span>
                    )}
                  </div>
                  <div className={styles.songCover}>
                    {song.cover_url ? (
                      <LazyImage src={song.cover_url} alt={song.title}
                        style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
                        fallback={<div className={styles.coverPlaceholder}><MusicIcon /></div>} />
                    ) : (
                      <div className={styles.coverPlaceholder}><MusicIcon /></div>
                    )}
                  </div>
                  <div className={styles.songInfo}>
                    <div className={styles.songTitle}>{song.title}</div>
                    <div className={styles.songArtist}>{song.artist} — {song.album}</div>
                  </div>
                  <span className={styles.songDuration}>{formatDuration(song.duration)}</span>
                  <button className={styles.addBtn} title="添加到播放列表"
                    onClick={(e) => { e.stopPropagation(); addToPlaylist(song) }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                    </svg>
                  </button>
                  <button className={`${styles.heartBtn} ${favoriteIds.includes(song.id) ? styles.heartBtnLiked : ''}`}
                    onClick={(e) => { e.stopPropagation(); toggleFavorite(song.id) }}>
                    <HeartIcon filled={favoriteIds.includes(song.id)} />
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ─── 本地歌手 ─── */}
      {results.artists.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <div className={styles.sectionTitle}>
              <ArtistIcon />
              <span>歌手</span>
            </div>
            <span className={styles.sectionCount}>{results.artists.length} 位</span>
          </div>
          <div className={styles.artistList}>
            {results.artists.map((artist) => (
              <div key={artist.name} className={styles.artistItem}>
                <div className={styles.artistAvatar}>{artist.name.charAt(0)}</div>
                <div className={styles.artistInfo}>
                  <div className={styles.artistName}>{artist.name}</div>
                  <div className={styles.artistCount}>{artist.count} 首歌曲</div>
                </div>
                <button className={styles.playAllSmall} onClick={() => playAll(artist.songs)}>
                  <PlayIcon />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ─── 本地专辑 ─── */}
      {results.albums.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <div className={styles.sectionTitle}>
              <AlbumIcon />
              <span>专辑</span>
            </div>
            <span className={styles.sectionCount}>{results.albums.length} 张</span>
          </div>
          <div className={styles.albumList}>
            {results.albums.map((album) => (
              <div key={album.name} className={styles.albumItem}>
                <div className={styles.albumCover}>
                  {album.coverSong?.cover_url ? (
                    <LazyImage src={album.coverSong.cover_url} alt={album.name} />
                  ) : (
                    <AlbumIcon />
                  )}
                </div>
                <div className={styles.albumInfo}>
                  <div className={styles.albumName}>{album.name}</div>
                  <div className={styles.albumCount}>{album.count} 首歌曲</div>
                </div>
                <button className={styles.playAllSmall} onClick={() => playAll(album.songs)}>
                  <PlayIcon />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ─── 在线音乐 ─── */}
      {onlineMusicEnabled && (onlineResults.length > 0 || onlineLoading) && (
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <div className={styles.sectionTitle}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" /><line x1="2" y1="12" x2="22" y2="12" />
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
              </svg>
              <span>在线音乐</span>
            </div>
            {onlineLoading ? (
              <Spin size="small" />
            ) : (
              <span className={styles.sectionCount}>{onlineResults.length} 首</span>
            )}
            {onlineResults.length > 0 && (
              <button className={styles.playAllBtn} onClick={() => playAll(onlineResults)}>
                <PlayIcon />
                <span>播放全部</span>
              </button>
            )}
          </div>
          {onlineResults.length > 0 && (
            <div className={styles.songList}>
              {onlineResults.map((song, i) => {
                const isCurrent = currentSong?.id === song.id
                const isPlaying = isCurrent && playbackState === 'playing'
                return (
                  <div
                    key={`online-${song.id}`}
                    className={`${styles.songItem} ${isCurrent ? styles.songItemActive : ''}`}
                    onClick={() => playSong(song)}
                  >
                    <div className={styles.songIndex}>
                      {isPlaying ? (
                        <div className={styles.playingBars}><span /><span /><span /></div>
                      ) : (
                        <span>{i + 1}</span>
                      )}
                    </div>
                    <div className={styles.songCover}>
                      {song.cover_url ? (
                        <LazyImage src={song.cover_url} alt={song.title}
                          style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
                          fallback={<div className={styles.coverPlaceholder}><MusicIcon /></div>} />
                      ) : (
                        <div className={styles.coverPlaceholder}><MusicIcon /></div>
                      )}
                    </div>
                    <div className={styles.songInfo}>
                      <div className={styles.songTitle}>{song.title}</div>
                      <div className={styles.songArtist}>{song.artist} — {song.album}</div>
                    </div>
                    <span className={styles.sourceTagOnline}>在线</span>
                    <button className={styles.addBtn} title="添加到播放列表"
                      onClick={(e) => { e.stopPropagation(); addToPlaylist(song) }}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                      </svg>
                    </button>
                    <button className={`${styles.heartBtn} ${favoriteIds.includes(song.id) ? styles.heartBtnLiked : ''}`}
                      onClick={(e) => { e.stopPropagation(); toggleFavorite(song.id) }}>
                      <HeartIcon filled={favoriteIds.includes(song.id)} />
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* ─── 无结果 ─── */}
      {!hasResults && (
        <div className={styles.emptyState}>
          <p className={styles.emptyText}>未找到 "{keyword}" 相关结果</p>
          <p className={styles.emptyHint}>试试其他关键词，或先在「设置」中扫描本地目录</p>
        </div>
      )}
    </div>
  )
}

export default SearchView
