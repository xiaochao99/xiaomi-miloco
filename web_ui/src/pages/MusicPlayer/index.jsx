import React, { useEffect, useState, useCallback } from 'react'
import { Spin } from 'antd'
import { useMusicPlayerStore } from '@/stores/musicPlayerStore'
import PlayerBar from '@/components/MusicPlayer/PlayerBar'
import PlaylistView from '@/components/MusicPlayer/PlaylistView'
import DetailView from '@/components/MusicPlayer/DetailView'
import RecommendView from '@/components/MusicPlayer/RecommendView'
import RankingView from '@/components/MusicPlayer/RankingView'
import LocalMusicScanner from '@/components/MusicPlayer/LocalMusicScanner'
import CategoryView from '@/components/MusicPlayer/CategoryView'
import SearchView from '@/components/MusicPlayer/SearchView'
import MusicSettings from '@/components/MusicPlayer/MusicSettings'
import LazyImage from '@/components/MusicPlayer/LazyImage'
import styles from './index.module.less'

// ─── SVG Icons ─────────────────────────────────────

const DiscoverIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="10" />
    <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
  </svg>
)

const RankingIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M18 20V10M12 20V4M6 20v-6" />
  </svg>
)

const SearchIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="11" cy="11" r="8" />
    <path d="M21 21l-4.35-4.35" />
  </svg>
)

const PlaylistNavIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M9 18V5l12-2v13" />
    <circle cx="6" cy="18" r="3" />
    <circle cx="18" cy="16" r="3" />
  </svg>
)



const MusicIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M9 18V5l12-2v13" />
    <circle cx="6" cy="18" r="3" />
    <circle cx="18" cy="16" r="3" />
  </svg>
)

const SettingsIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z" />
  </svg>
)

const NoteIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>
  </svg>
)
const HeartNavIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
  </svg>
)
const DiscIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="2"/>
  </svg>
)

// ─── Sidebar Nav Items ─────────────────────────────

const NAV_ITEMS = [
  { key: 'discover', label: '发现音乐', Icon: DiscoverIcon },
  { key: 'ranking', label: '排行榜', Icon: RankingIcon },
  { key: 'search', label: '搜索', Icon: SearchIcon },
  { key: 'local', label: '歌曲', Icon: NoteIcon },
  { key: 'artists', label: '歌手', Icon: NoteIcon },
  { key: 'albums', label: '专辑', Icon: DiscIcon },
  { key: 'favorites', label: '我的喜欢', Icon: HeartNavIcon },
  { key: 'playlist', label: '播放列表', Icon: PlaylistNavIcon },
]

// ─── MusicPlayer Page ──────────────────────────────

const MusicPlayer = () => {
  const {
    isLoading, error, clearError,
    searchSongs, searchResults, isSearching, searchKeyword, clearSearch,
    songs, currentSong, playbackState,
    activeView, setActiveView,
    showDetail, setShowDetail,
    displayModes, toggleDisplayMode,
  } = useMusicPlayerStore()
  const curMode = displayModes[activeView] || 'list'

  const [searchValue, setSearchValue] = useState('')
  const [showSearchResults, setShowSearchResults] = useState(false)

  // Load persisted songs and favorites from backend on mount
  useEffect(() => {
    const store = useMusicPlayerStore.getState()
    store.loadPlaylistFromBackend()
    store.loadFavorites()
  }, [])

  useEffect(() => {
    if (error) {
      const t = setTimeout(() => clearError(), 4000)
      return () => clearTimeout(t)
    }
  }, [error, clearError])

  // ─── Search ────────────────────────────────────

  const handleSearch = useCallback((value) => {
    setSearchValue(value)
    if (value.trim()) {
      searchSongs(value.trim())
      setShowSearchResults(true)
      setActiveView('search')
    } else {
      clearSearch()
      setShowSearchResults(false)
    }
  }, [searchSongs, clearSearch, setActiveView])

  const handleClearSearch = () => {
    setSearchValue('')
    clearSearch()
    setShowSearchResults(false)
  }

  const handleSongSelect = (song) => {
    useMusicPlayerStore.getState().playSong(song)
  }

  // ─── Navigation ────────────────────────────────

  const handleNavClick = (key) => {
    setActiveView(key)
    if (key !== 'search') {
      handleClearSearch()
    }
    setShowDetail(false)
  }

  const handleShowDetail = () => setShowDetail(true)
  const handleCloseDetail = () => setShowDetail(false)

  // ─── Content Rendering ─────────────────────────

  const renderContent = () => {
    if (showDetail) {
      return <DetailView onClose={handleCloseDetail} />
    }

    switch (activeView) {
      case 'discover':
        return <RecommendView />
      case 'ranking':
        return <RankingView />
      case 'search':
        return <SearchView keyword={searchKeyword} />
      case 'local':
        return <LocalMusicScanner />

      case 'artists':
        return <CategoryView category="artists" />
      case 'albums':
        return <CategoryView category="albums" />
      case 'favorites':
        return <CategoryView category="favorites" />
      case 'settings':
        return <MusicSettings />
      case 'playlist':
        return (
          <PlaylistView
            songs={songs}
            onSongSelect={handleSongSelect}
            showSearch={false}
          />
        )
      default:
        return <RecommendView />
    }
  }

  // ─── Loading State ─────────────────────────────

  if (isLoading) {
    return (
      <div className={styles.loadingScreen}>
        <Spin size="large" />
        <p>加载中...</p>
      </div>
    )
  }

  return (
    <div className={styles.appContainer}>
      {/* Error Toast */}
      {error && (
        <div className={styles.errorBar}>
          <span>{error}</span>
          <button className={styles.errorClose} onClick={clearError}>×</button>
        </div>
      )}

      <div className={styles.mainLayout}>
        {/* Sidebar */}
        <aside className={styles.sidebar}>
          <div className={styles.sidebarHeader}>
            <MusicIcon />
            <span className={styles.sidebarTitle}>音乐中心</span>
          </div>

          <nav className={styles.sidebarNav}>
            {NAV_ITEMS.map(({ key, label, Icon }) => (
              <button
                key={key}
                className={`${styles.navItem} ${activeView === key ? styles.navItemActive : ''}`}
                onClick={() => handleNavClick(key)}
              >
                <Icon />
                <span>{label}</span>
                {key === 'playlist' && songs.length > 0 && (
                  <span className={styles.navBadge}>{songs.length}</span>
                )}
              </button>
            ))}
          </nav>

          {/* Settings Button */}
          <div className={styles.sidebarBottom}>
            <button
              className={`${styles.navItem} ${activeView === 'settings' ? styles.navItemActive : ''}`}
              onClick={() => handleNavClick('settings')}
            >
              <SettingsIcon />
              <span>设置</span>
            </button>
          </div>

          {/* Current Song Mini Info */}
          {currentSong && (
            <div className={styles.sidebarFooter}>
              <div className={styles.miniSongInfo}>
                {currentSong.cover_url ? (
                  <LazyImage src={currentSong.cover_url} alt="" className={styles.miniCover} key={currentSong.cover_url} rootMargin="0px" />
                ) : (
                  <div className={styles.miniCoverPlaceholder}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <circle cx="12" cy="12" r="10" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  </div>
                )}
                <div className={styles.miniSongText}>
                  <div className={styles.miniTitle}>{currentSong.title}</div>
                  <div className={styles.miniArtist}>{currentSong.artist}</div>
                </div>
              </div>
            </div>
          )}
        </aside>

        {/* Content Area */}
        <div className={styles.contentWrapper}>
          {/* Header with Search */}
          <header className={styles.header}>
            <div className={styles.headerSearch}>
              <div className={styles.searchBox}>
                <SearchIcon />
                <input
                  type="text"
                  placeholder="搜索歌曲、歌手、专辑"
                  value={searchValue}
                  onChange={(e) => handleSearch(e.target.value)}
                  className={styles.searchInput}
                />
                {searchValue && (
                  <button className={styles.searchClear} onClick={handleClearSearch}>
                    ×
                  </button>
                )}
                {isSearching && (
                  <div className={styles.searchLoading}>
                    <Spin size="small" />
                  </div>
                )}
              </div>
            </div>
            <button
              className={styles.viewToggle}
              onClick={toggleDisplayMode}
              title={curMode === 'list' ? '切换卡片视图' : '切换列表视图'}
            >
              {curMode === 'list' ? (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="7" height="7" rx="1"/>
                  <rect x="14" y="3" width="7" height="7" rx="1"/>
                  <rect x="3" y="14" width="7" height="7" rx="1"/>
                  <rect x="14" y="14" width="7" height="7" rx="1"/>
                </svg>
              ) : (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="3" y1="6" x2="21" y2="6"/>
                  <line x1="3" y1="12" x2="21" y2="12"/>
                  <line x1="3" y1="18" x2="21" y2="18"/>
                </svg>
              )}
            </button>
          </header>

          {/* Main Content */}
          <main className={styles.contentArea}>
            {renderContent()}
          </main>
        </div>
      </div>

      {/* Player Bar */}
      <PlayerBar
        onShowDetail={handleShowDetail}
        onTogglePlaylist={() => handleNavClick('playlist')}
      />
    </div>
  )
}

export default MusicPlayer
