import React, { useState, useCallback } from 'react'
import { Empty } from 'antd'
import { useMusicPlayerStore } from '@/stores/musicPlayerStore'
import styles from './index.module.less'

const formatDuration = (seconds) => {
  if (!seconds || isNaN(seconds)) return '--:--'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

const PlayIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
    <path d="M8 5v14l11-7z" />
  </svg>
)

const PauseIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
    <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
  </svg>
)

const DeleteIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
  </svg>
)

const MusicIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <circle cx="12" cy="12" r="10" />
    <circle cx="12" cy="12" r="3" />
  </svg>
)

const CheckIcon = () => (
  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3">
    <polyline points="20 6 9 17 4 12" />
  </svg>
)

const getSongSource = (id) => {
  if (!id) return null
  if (id.startsWith('local_')) return 'local'
  if (id.startsWith('online_')) return 'online'
  return null
}

const PlaylistView = ({ songs, onSongSelect, showSearch }) => {
  const { currentSong, playbackState, playSong, removeFromPlaylist, clearPlaylist } = useMusicPlayerStore()
  const [selected, setSelected] = useState(new Set())
  const [batchMode, setBatchMode] = useState(false)

  const isCurrent = (song) => currentSong?.id === song.id
  const isPlaying = (song) => isCurrent(song) && playbackState === 'playing'

  const handlePlay = (e, song) => {
    e.stopPropagation()
    if (batchMode) return
    if (isCurrent(song)) {
      useMusicPlayerStore.getState().togglePlay()
    } else {
      playSong(song)
      onSongSelect?.(song)
    }
  }

  const handleRemove = (e, songId) => {
    e.stopPropagation()
    removeFromPlaylist(songId)
    setSelected((prev) => { const n = new Set(prev); n.delete(songId); return n })
  }

  // ─── Batch operations ────────────────────────────

  const toggleSelect = (e, songId) => {
    e.stopPropagation()
    setSelected((prev) => {
      const n = new Set(prev)
      if (n.has(songId)) n.delete(songId)
      else n.add(songId)
      return n
    })
  }

  const toggleSelectAll = () => {
    if (selected.size === songs.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(songs.map((s) => s.id)))
    }
  }

  const handleDeleteSelected = () => {
    if (selected.size === 0) return
    const store = useMusicPlayerStore.getState()
    for (const id of selected) {
      store.removeFromPlaylist(id)
    }
    setSelected(new Set())
    setBatchMode(false)
  }

  const handleClearAll = () => {
    clearPlaylist()
    setSelected(new Set())
    setBatchMode(false)
  }

  const enterBatchMode = () => {
    setBatchMode(true)
    setSelected(new Set())
  }

  const cancelBatchMode = () => {
    setBatchMode(false)
    setSelected(new Set())
  }

  // ─── Empty state ─────────────────────────────────

  if (!songs || songs.length === 0) {
    return (
      <div className={styles.emptyState}>
        <Empty
          description={
            <span className={styles.emptyText}>
              {showSearch ? '无搜索结果' : '播放列表为空'}
            </span>
          }
        >
          {!showSearch && (
            <p className={styles.emptyHint}>搜索或扫描本地音乐添加到播放列表</p>
          )}
        </Empty>
      </div>
    )
  }

  return (
    <div className={styles.playlistContainer}>
      {/* ─── Toolbar ─────────────────────────────── */}
      {!showSearch && (
        <div className={styles.toolbar}>
          {batchMode ? (
            <>
              <button className={styles.toolbarBtn} onClick={toggleSelectAll}>
                {selected.size === songs.length ? '取消全选' : '全选'}
              </button>
              <button
                className={styles.toolbarBtnDanger}
                onClick={handleDeleteSelected}
                disabled={selected.size === 0}
              >
                删除选中 ({selected.size})
              </button>
              <button className={styles.toolbarBtn} onClick={cancelBatchMode}>
                取消
              </button>
            </>
          ) : (
            <>
              <span className={styles.songCount}>{songs.length} 首</span>
              <div className={styles.toolbarRight}>
                <button className={styles.toolbarBtn} onClick={enterBatchMode}>
                  批量管理
                </button>
                <button className={styles.toolbarBtnDanger} onClick={handleClearAll}>
                  清空
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* ─── Table Header ────────────────────────── */}
      <div className={styles.tableHeader}>
        {batchMode && <div className={styles.colCheck} />}
        <div className={styles.colIndex}>#</div>
        <div className={styles.colTitle}>歌曲</div>
        <div className={styles.colArtist}>歌手</div>
        <div className={styles.colAlbum}>专辑</div>
        <div className={styles.colDuration}>时长</div>
        <div className={styles.colAction}>操作</div>
      </div>

      {/* ─── Table Body ──────────────────────────── */}
      <div className={styles.tableBody}>
        {songs.map((song, index) => {
          const isSelected = selected.has(song.id)
          return (
            <div
              key={`${song.id}-${index}`}
              className={`${styles.songRow} ${isCurrent(song) ? styles.songRowActive : ''} ${isSelected ? styles.songRowSelected : ''}`}
              onClick={() => !batchMode && onSongSelect?.(song)}
            >
              {/* Checkbox */}
              {batchMode && (
                <div className={styles.colCheck}>
                  <span
                    className={`${styles.checkbox} ${isSelected ? styles.checked : ''}`}
                    onClick={(e) => toggleSelect(e, song.id)}
                  >
                    {isSelected && <CheckIcon />}
                  </span>
                </div>
              )}

              {/* Index / Play indicator */}
              <div className={styles.colIndex}>
                {batchMode ? null : isPlaying(song) ? (
                  <div className={styles.playingBars}>
                    <span /><span /><span />
                  </div>
                ) : isCurrent(song) ? (
                  <button className={styles.playPauseBtn} onClick={(e) => handlePlay(e, song)}>
                    {playbackState === 'paused' ? <PlayIcon /> : <PauseIcon />}
                  </button>
                ) : (
                  <>
                    <span className={styles.indexNum}>{index + 1}</span>
                    <div className={styles.indexPlay}>
                      <PlayIcon />
                    </div>
                  </>
                )}
              </div>

              {/* Title + Source tag */}
              <div className={styles.colTitle}>
                {song.cover_url ? (
                  <img src={song.cover_url} alt="" className={styles.songCover} />
                ) : (
                  <div className={styles.songCoverPlaceholder}>
                    <MusicIcon />
                  </div>
                )}
                <span className={styles.songName}>{song.title}</span>
                {getSongSource(song.id) === 'local' && (
                  <span className={styles.sourceTagLocal}>本地</span>
                )}
                {(getSongSource(song.id) === 'online' || showSearch) && (
                  <span className={styles.sourceTagOnline}>在线</span>
                )}
              </div>

              <div className={styles.colArtist}>{song.artist}</div>
              <div className={styles.colAlbum}>{song.album}</div>
              <div className={styles.colDuration}>
                {formatDuration(song.duration)}
              </div>
              <div className={styles.colAction}>
                {!showSearch && !batchMode && (
                  <button
                    className={styles.removeBtn}
                    onClick={(e) => handleRemove(e, song.id)}
                    title="移除"
                  >
                    <DeleteIcon />
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default PlaylistView
