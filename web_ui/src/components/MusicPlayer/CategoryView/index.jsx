import React, { useEffect, useState } from 'react'
import { Spin } from 'antd'
import { useMusicPlayerStore } from '@/stores/musicPlayerStore'
import LazyImage from '@/components/MusicPlayer/LazyImage'
import styles from './index.module.less'

const formatDuration = (seconds) => {
  if (!seconds || isNaN(seconds)) return '--:--'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

const HeartIcon = ({ filled }) => filled ? (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="#ec4141"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>
) : (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
)

const MusicIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/>
  </svg>
)

const SongRow = ({ song, index, isPlaying, onPlay, onToggleFavorite, isLiked, onAddToPlaylist }) => (
  <div className={styles.songRow} onClick={() => onPlay(song)}>
    {index != null && <span className={styles.rowIndex}>{index}</span>}
    <div className={styles.rowCover}>
      {song.cover_url ? (
        <LazyImage src={song.cover_url} alt={song.title} className={styles.rowCoverImg}
          fallback={<div className={styles.rowCoverPlaceholder}><MusicIcon/></div>} />
      ) : (
        <div className={styles.rowCoverPlaceholder}><MusicIcon/></div>
      )}
    </div>
    <div className={styles.rowInfo}>
      <span className={`${styles.rowTitle} ${isPlaying ? styles.rowTitleActive : ''}`}>{song.title}</span>
      <span className={styles.rowArtist}>{song.artist} — {song.album}</span>
    </div>
    <span className={styles.rowDuration}>{formatDuration(song.duration)}</span>
    {onAddToPlaylist && (
      <button className={styles.addBtn} title="添加到播放列表"
        onClick={(e) => { e.stopPropagation(); onAddToPlaylist(song) }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
      </button>
    )}
    <button className={`${styles.heartBtn} ${isLiked ? styles.heartBtnLiked : ''}`}
      onClick={(e) => { e.stopPropagation(); onToggleFavorite(song.id) }}>
      <HeartIcon filled={isLiked}/>
    </button>
  </div>
)

const PlayAllIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
    <path d="M8 5v14l11-7z" />
  </svg>
)

const CategoryView = ({ category }) => {
  const { library, favoriteIds, currentSong, playbackState, playSong, playAll, toggleFavorite, addToPlaylist, loadCategories, categories, categoriesLoading, displayModes } = useMusicPlayerStore()
  const [expanded, setExpanded] = useState(null)
  const isCard = (displayModes[category] || 'list') === 'card'

  useEffect(() => {
    if (category !== 'songs') loadCategories()
  }, [category, loadCategories])

  const handlePlay = (song) => playSong(song)
  const handleToggleFav = async (songId) => { await toggleFavorite(songId) }
  const localSongs = library.filter(s => String(s.id).startsWith('local_'))

  if (categoriesLoading && category !== 'songs') {
    return <div className={styles.loadingWrap}><Spin/><p>加载分类中...</p></div>
  }

  // ── 全部歌曲 ──
  if (category === 'songs') {
    return (
      <div className={styles.container}>
        <div className={styles.header}><h3>全部歌曲</h3><span className={styles.count}>{localSongs.length} 首</span></div>
        {isCard ? (
          <div className={styles.cardGrid}>
            {localSongs.map((s) => {
              const isCurrent = currentSong?.id === s.id && playbackState === 'playing'
              return (
                <div key={s.id} className={`${styles.cardItem} ${isCurrent ? styles.cardItemActive : ''}`} onClick={() => handlePlay(s)}>
                  <div className={styles.cardCover}>
                    {s.cover_url ? <LazyImage src={s.cover_url} alt={s.title} fallback={<div className={styles.cardCoverPlaceholder}><MusicIcon/></div>} />
                      : <div className={styles.cardCoverPlaceholder}><MusicIcon/></div>}
                  </div>
                  <div className={styles.cardInfo}><div className={styles.cardTitle}>{s.title}</div><div className={styles.cardArtist}>{s.artist}</div></div>
                  <div className={styles.cardActions}>
                    <button className={styles.cardAddBtn} title="添加到播放列表"
                      onClick={(e) => { e.stopPropagation(); addToPlaylist(s) }}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                    </button>
                    <button className={`${styles.cardHeart} ${favoriteIds.includes(s.id) ? styles.cardHeartLiked : ''}`}
                      onClick={(e) => { e.stopPropagation(); handleToggleFav(s.id) }}><HeartIcon filled={favoriteIds.includes(s.id)}/></button>
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
        <div className={styles.list}>
          {localSongs.map((s, i) => (
            <SongRow key={s.id} song={s} index={i + 1}
              isPlaying={currentSong?.id === s.id && playbackState === 'playing'}
              onPlay={handlePlay} onToggleFavorite={handleToggleFav}
              onAddToPlaylist={addToPlaylist}
              isLiked={favoriteIds.includes(s.id)} />
          ))}
        </div>
        )}
      </div>
    )
  }

  // ── 我的喜欢 ──
  if (category === 'favorites') {
    const favSongs = library.filter(s => favoriteIds.includes(s.id))
    return (
      <div className={styles.container}>
        <div className={styles.header}>
          <h3>我的喜欢</h3>
          <span className={styles.count}>{favSongs.length} 首</span>
          {favSongs.length > 0 && (
            <button className={styles.playAllBtn} onClick={() => playAll(favSongs)}>
              <PlayAllIcon /> 全部播放
            </button>
          )}
        </div>
        {favSongs.length === 0 ? (
          <div className={styles.empty}><p>暂无收藏歌曲</p><p className={styles.hint}>点击歌曲右侧的 ♡ 按钮收藏</p></div>
        ) : isCard ? (
          <div className={styles.cardGrid}>
            {favSongs.map((s) => {
              const isCurrent = currentSong?.id === s.id && playbackState === 'playing'
              return (
                <div key={s.id} className={`${styles.cardItem} ${isCurrent ? styles.cardItemActive : ''}`} onClick={() => handlePlay(s)}>
                  <div className={styles.cardCover}>
                    {s.cover_url ? <LazyImage src={s.cover_url} alt={s.title} fallback={<div className={styles.cardCoverPlaceholder}><MusicIcon/></div>} />
                      : <div className={styles.cardCoverPlaceholder}><MusicIcon/></div>}
                  </div>
                  <div className={styles.cardInfo}><div className={styles.cardTitle}>{s.title}</div><div className={styles.cardArtist}>{s.artist}</div></div>
                  <div className={styles.cardActions}>
                    <button className={styles.cardAddBtn} title="添加到播放列表"
                      onClick={(e) => { e.stopPropagation(); addToPlaylist(s) }}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                    </button>
                    <button className={`${styles.cardHeart} ${styles.cardHeartLiked}`}
                      onClick={(e) => { e.stopPropagation(); handleToggleFav(s.id) }}><HeartIcon filled={true}/></button>
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className={styles.list}>
          {favSongs.map((s, i) => (
            <SongRow key={s.id} song={s} index={i + 1}
              isPlaying={currentSong?.id === s.id && playbackState === 'playing'}
              onPlay={handlePlay} onToggleFavorite={handleToggleFav}
              onAddToPlaylist={addToPlaylist}
              isLiked={true} />
          ))}
          </div>
        )}
      </div>
    )
  }

  // ── 歌手分类 ──
  if (category === 'artists') {
    const artists = (categories.artists || []).map(a => ({
      ...a,
      songs: localSongs.filter(s => (s.artist || '未知艺术家') === a.name)
    }))
    return (
      <div className={styles.container}>
        <div className={styles.header}><h3>歌手</h3><span className={styles.count}>{artists.length} 位</span></div>
        <div className={isCard ? styles.grid : styles.list}>
          {artists.map((a) => {
            const isExpanded = expanded === a.name
            const content = (
              <div key={a.name} className={`${isCard ? styles.gridItem : styles.listItem} ${isCard && isExpanded ? styles.gridItemExpanded : ''}`} onClick={() => setExpanded(isExpanded ? null : a.name)}>
                {isCard ? (
                  <div className={styles.artistAvatar}>{a.name.charAt(0)}</div>
                ) : (
                  <div className={styles.listAvatar}>{a.name.charAt(0)}</div>
                )}
                <div className={isCard ? styles.artistName : styles.listName}>{a.name}</div>
                <div className={styles.artistCount}>{a.count} 首</div>
                {isExpanded && (
                  <div className={styles.expandedList} onClick={(e) => e.stopPropagation()}>
                    <button className={styles.expandedPlayAll} onClick={() => playAll(a.songs)}>
                      <PlayAllIcon /> 全部播放
                    </button>
                    {a.songs.map((s, i) => (
                      <SongRow key={s.id} song={s} index={i + 1}
                        isPlaying={currentSong?.id === s.id && playbackState === 'playing'}
                        onPlay={handlePlay} onToggleFavorite={handleToggleFav}
                        onAddToPlaylist={addToPlaylist}
                        isLiked={favoriteIds.includes(s.id)} />
                    ))}
                  </div>
                )}
              </div>
            )
            return content
          })}
        </div>
      </div>
    )
  }

  // ── 专辑分类 ──
  if (category === 'albums') {
    const albums = (categories.albums || []).map(a => ({
      ...a,
      songs: localSongs.filter(s => (s.album || '未知专辑') === a.name),
      coverSong: localSongs.find(s => (s.album || '未知专辑') === a.name && s.cover_url)
    }))
    return (
      <div className={styles.container}>
        <div className={styles.header}><h3>专辑</h3><span className={styles.count}>{albums.length} 张</span></div>
        <div className={isCard ? styles.grid : styles.list}>
          {albums.map((a) => {
            const isExpanded = expanded === a.name
            return (
              <div key={a.name} className={`${isCard ? styles.gridItem : styles.listItem} ${isCard && isExpanded ? styles.gridItemExpanded : ''}`} onClick={() => setExpanded(isExpanded ? null : a.name)}>
                {isCard ? (
                  <div className={styles.albumCover}>
                    {a.coverSong?.cover_url ? <LazyImage src={a.coverSong.cover_url} alt={a.name} className={styles.albumCoverImg} /> : <MusicIcon />}
                  </div>
                ) : (
                  <div className={styles.listThumb}>
                    {a.coverSong?.cover_url ? <LazyImage src={a.coverSong.cover_url} alt={a.name} /> : <MusicIcon />}
                  </div>
                )}
                <div className={isCard ? styles.albumName : styles.listName}>{a.name}</div>
                <div className={styles.albumCount}>{a.count} 首</div>
                {isExpanded && (
                  <div className={styles.expandedList} onClick={(e) => e.stopPropagation()}>
                    <button className={styles.expandedPlayAll} onClick={() => playAll(a.songs)}>
                      <PlayAllIcon /> 全部播放
                    </button>
                    {a.songs.map((s, i) => (
                      <SongRow key={s.id} song={s} index={i + 1}
                        isPlaying={currentSong?.id === s.id && playbackState === 'playing'}
                        onPlay={handlePlay} onToggleFavorite={handleToggleFav}
                        onAddToPlaylist={addToPlaylist}
                        isLiked={favoriteIds.includes(s.id)} />
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  return null
}

export default CategoryView
