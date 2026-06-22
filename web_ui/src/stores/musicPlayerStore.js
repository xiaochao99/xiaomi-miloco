import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import * as musicApi from '@/api/musicApi'
import * as api from '@/api/index'

const REPEAT_MODES = { LIST: 'list', SINGLE: 'single', SHUFFLE: 'shuffle' }
const REPEAT_ORDER = [REPEAT_MODES.LIST, REPEAT_MODES.SINGLE, REPEAT_MODES.SHUFFLE]
const REPEAT_LABELS = {
  [REPEAT_MODES.LIST]: { label: '列表循环', next: REPEAT_MODES.SINGLE },
  [REPEAT_MODES.SINGLE]: { label: '单曲循环', next: REPEAT_MODES.SHUFFLE },
  [REPEAT_MODES.SHUFFLE]: { label: '随机播放', next: REPEAT_MODES.LIST },
}

export const useMusicPlayerStore = create(
  persist(
    (set, get) => ({
      playbackState: 'stopped',
      currentSong: null,
      currentIndex: -1,
      position: 0,
      duration: 0,
      volume: 0.7,
      isMuted: false,
      repeatMode: REPEAT_MODES.LIST,

      songs: [],       // playlist / play queue (cleared by user)
      library: [],     // all songs ever added (persistent, never auto-cleared)
      searchResults: [],
      searchKeyword: '',
      isSearching: false,

      lyrics: [],
      currentLyricIndex: -1,

      isLoading: false,
      isControlling: false,
      error: null,

      // View state
      activeView: 'discover',
      showDetail: false,
      displayModes: {},
      _defaultDisplayModes: { local: 'list', artists: 'card', albums: 'card', favorites: 'list', playlist: 'list' },

      // Recommendation data
      recommendSeeds: [],
      recommendLoading: false,
      currentRecommendKey: '',
      recommendCache: {},

      // Favorites & Categories
      favoriteIds: [],
      categories: { artists: [], albums: [] },
      categoriesLoading: false,

      // Online music feature toggle
      onlineMusicEnabled: false,

      // Local scanner state
      scanDirs: [],
      scanDirsLoading: false,
      scanLoading: false,
      scanResult: null,
      scanError: null,
      watcherStatus: null,

      // DLNA state
      dlnaDevices: [],
      selectedDLNADevice: null,
      isDLNACasting: false,
      dlnaPlayState: 'stopped', // 'playing' | 'paused' | 'stopped'
      dlnaLoading: false,

      _audio: null,
      _positionTimer: null,

      initialize: () => {
        // If audio already exists, reuse it — don't create a duplicate
        if (get()._audio) {
          set({ isLoading: false })
          return
        }
        try {
          set({ isLoading: true, error: null })
          const audio = new Audio()
          audio.volume = get().volume
          audio.preload = 'auto'
          audio.crossOrigin = 'anonymous'

          audio.addEventListener('play', () => {
            set({ playbackState: 'playing' })
            get()._startPositionUpdate()
          })
          audio.addEventListener('pause', () => {
            if (get().playbackState !== 'stopped') set({ playbackState: 'paused' })
            get()._stopPositionUpdate()
          })
          audio.addEventListener('ended', () => {
            get()._stopPositionUpdate()
            get()._handleEnded()
          })
          audio.addEventListener('loadedmetadata', () => {
            set({ duration: audio.duration })
          })
          audio.addEventListener('error', () => {
            set({ playbackState: 'stopped', error: '音频加载失败' })
          })

          set({ _audio: audio, isLoading: false })
        } catch (e) {
          set({ error: e.message, isLoading: false })
        }
      },

      destroy: () => {
        const audio = get()._audio
        if (audio) {
          audio.pause()
          audio.removeAttribute('src')
          audio.load()
        }
        get()._stopPositionUpdate()
        set({ _audio: null, playbackState: 'stopped', position: 0 })
      },

      loadPlaylistFromBackend: async () => {
        try {
          const res = await api.getMusicSongs()
          if (res?.code === 0 && Array.isArray(res.data)) {
            // Sync local songs with backend: replace all local_ entries,
            // keep online songs intact (they don't come from the backend)
            const library = get().library
            const onlineSongs = library.filter(s => !String(s.id).startsWith('local_'))
            const syncedLocalSongs = res.data.map(s => get()._trimSong(s))
            set({ library: [...onlineSongs, ...syncedLocalSongs] })
          }
        } catch {
          // Silent fail — backend may not have songs yet
        }
      },

      searchSongs: async (keyword) => {
        if (!keyword?.trim()) {
          set({ searchResults: [], searchKeyword: '', isSearching: false })
          return
        }
        const kw = keyword.trim()
        set({ isSearching: true, searchKeyword: kw })
        try {
          // Load categories if not loaded yet (needed for SearchView)
          if (get().categories.artists.length === 0) {
            get().loadCategories()
          }
          // Search local library (sync, fast)
          const kwLower = kw.toLowerCase()
          const localResults = get().library.filter(s =>
            (s.title || '').toLowerCase().includes(kwLower) ||
            (s.artist || '').toLowerCase().includes(kwLower) ||
            (s.album || '').toLowerCase().includes(kwLower)
          ).map(s => get()._trimSong(s))
          // Search online (async) — only if online music is enabled
          let onlineResults = []
          if (get().onlineMusicEnabled) {
            try {
              onlineResults = await musicApi.searchSongs(kw)
            } catch { /* ignore online search errors */ }
          }
          set({ searchResults: [...localResults, ...onlineResults] })
        } catch (e) {
          console.error('Search failed:', e)
          set({ error: '搜索失败' })
        } finally {
          set({ isSearching: false })
        }
      },

      clearSearch: () => {
        set({ searchResults: [], searchKeyword: '' })
      },

      playSong: async (song) => {
        try {
          set({ isControlling: true })
          const audio = get()._audio
          if (!audio) {
            get().initialize()
          }

          // Always add to library
          get()._addToLibrary(song)
          const trimmed = get()._trimSong(song)

          const songs = get().songs
          let idx = songs.findIndex(s => s.id === song.id)
          if (idx < 0) {
            const newSongs = [...songs, trimmed]
            idx = newSongs.length - 1
            set({ songs: newSongs })
          }

          let enriched = { ...trimmed }
          if (!enriched.audio_url) {
            // Online song — enrich from external API
            enriched = await musicApi.enrichSong(enriched)
            const updatedSongs = [...get().songs]
            updatedSongs[idx] = enriched
            set({ songs: updatedSongs })
          }

          // Set current song and start audio loading IMMEDIATELY
          set({
            currentSong: enriched,
            currentIndex: idx,
            position: 0,
            currentLyricIndex: -1,
            playbackState: 'playing',
          })

          if (enriched.cover_url) {
            get()._setFavicon(enriched.cover_url)
          }

          const targetAudio = get()._audio
          targetAudio.src = enriched.audio_url
          targetAudio.load()
          await targetAudio.play()

          // Auto-sync DLNA: if casting, update the DLNA device with the new song
          if (get().isDLNACasting && get().selectedDLNADevice) {
            const deviceId = get().selectedDLNADevice.udn || get().selectedDLNADevice.id
            api.castToDLNA(deviceId, enriched.id, enriched.audio_url).catch(() => {})
          }

          // Fetch lyrics asynchronously AFTER starting playback (non-blocking)
          if (enriched.audio_url?.startsWith('/api/music/stream/') && !enriched.lyrics?.length) {
            fetch(`/api/music/lyric/${enriched.id}`)
              .then(resp => resp.ok ? resp.json() : null)
              .then(lrcData => {
                if (Array.isArray(lrcData) && lrcData.length > 0) {
                  const updatedSongs = [...get().songs]
                  const songIdx = updatedSongs.findIndex(s => s.id === enriched.id)
                  if (songIdx >= 0) {
                    updatedSongs[songIdx] = { ...updatedSongs[songIdx], lyrics: lrcData }
                    set({ songs: updatedSongs })
                  }
                  if (get().currentSong?.id === enriched.id) {
                    set({ lyrics: lrcData })
                  }
                }
              })
              .catch(() => {})
          } else if (enriched.lyrics) {
            set({ lyrics: enriched.lyrics })
          } else {
            set({ lyrics: [] })
          }
        } catch (e) {
          console.error('Play failed:', e)
          set({ error: '播放失败', playbackState: 'stopped' })
        } finally {
          set({ isControlling: false })
        }
      },

      play: async () => {
        const audio = get()._audio
        if (!audio) return
        if (get().currentSong) {
          try {
            await audio.play()
          } catch (e) {
            console.error('Play failed:', e)
          }
        } else {
          const songs = get().songs
          if (songs.length > 0) await get().playSong(songs[0])
        }
      },

      pause: () => {
        const audio = get()._audio
        if (audio && !audio.paused) audio.pause()
        set({ playbackState: 'paused' })
      },

      togglePlay: () => {
        if (get().playbackState === 'playing') {
          get().pause()
        } else {
          get().play()
        }
      },

      stop: () => {
        const audio = get()._audio
        if (audio) {
          audio.pause()
          audio.currentTime = 0
        }
        get()._stopPositionUpdate()
        set({ playbackState: 'stopped', position: 0, currentLyricIndex: -1 })
      },

      next: () => {
        const { songs, currentIndex, repeatMode } = get()
        if (songs.length === 0) return
        let nextIdx
        if (repeatMode === REPEAT_MODES.SHUFFLE) {
          nextIdx = Math.floor(Math.random() * songs.length)
        } else {
          nextIdx = (currentIndex + 1) % songs.length
        }
        if (songs[nextIdx]) get().playSong(songs[nextIdx])
      },

      previous: () => {
        const { songs, currentIndex } = get()
        if (songs.length === 0) return
        const prevIdx = currentIndex <= 0 ? songs.length - 1 : currentIndex - 1
        if (songs[prevIdx]) get().playSong(songs[prevIdx])
      },

      seek: (position) => {
        const audio = get()._audio
        if (audio) {
          audio.currentTime = position
          set({ position })
        }
      },

      setVolume: (volume) => {
        const v = Math.max(0, Math.min(1, volume))
        const audio = get()._audio
        if (audio) {
          audio.volume = v
          audio.muted = false
        }
        set({ volume: v, isMuted: false })
      },

      toggleMute: () => {
        const newMuted = !get().isMuted
        const audio = get()._audio
        if (audio) audio.muted = newMuted
        set({ isMuted: newMuted })
      },

      cycleRepeatMode: () => {
        const current = get().repeatMode
        const idx = REPEAT_ORDER.indexOf(current)
        const nextMode = REPEAT_ORDER[(idx + 1) % REPEAT_ORDER.length]
        set({ repeatMode: nextMode })
      },

      setRepeatMode: (mode) => {
        set({ repeatMode: mode })
      },

      // ── Library helpers ────────────────────────────

      _trimSong: (song) => {
        const trimmed = {
          id: song.id,
          title: song.title || '未知歌曲',
          artist: song.artist || '未知歌手',
          album: song.album || '未知专辑',
          duration: song.duration || 0,
          picId: song.picId || '',
          lyricId: song.lyricId || '',
          source: song.source || '',
          audio_url: song.audio_url || '',
        }
        // Local songs: cover from backend endpoint
        if (song.id?.startsWith('local_')) {
          trimmed.cover_url = `/api/music/cover/${song.id}`
          // Don't include lyrics — fetched from /api/music/lyric/{id} on demand
        } else {
          // Online songs: keep lyrics and non-base64 covers
          trimmed.lyrics = song.lyrics || null
          if (song.cover_url && !song.cover_url.startsWith('data:')) {
            trimmed.cover_url = song.cover_url
          }
        }
        return trimmed
      },

      _addToLibrary: (song) => {
        const library = get().library
        const existing = library.find(s => s.id === song.id)
        const trimmed = get()._trimSong(song)
        if (!existing) {
          set({ library: [...library, trimmed] })
        } else if (existing.artist === '未知歌手' || existing.album === '未知专辑' || existing.duration === 0) {
          // Update stale entry with fresh metadata
          set({ library: library.map(s => s.id === song.id ? trimmed : s) })
        }
      },

      _addAllToLibrary: (newSongs) => {
        if (!newSongs?.length) return
        const library = get().library
        // Build a map for O(1) lookup and update
        const songMap = new Map(library.map(s => [s.id, s]))
        let changed = false
        for (const song of newSongs) {
          const trimmed = get()._trimSong(song)
          const existing = songMap.get(song.id)
          // Update if not present or if the existing entry has stale metadata
          if (!existing || existing.artist === '未知歌手' || existing.album === '未知专辑' || existing.duration === 0) {
            songMap.set(song.id, trimmed)
            changed = true
          }
        }
        if (changed) {
          set({ library: [...songMap.values()] })
        }
      },

      // ── Playlist operations (songs = play queue only) ─

      addToPlaylist: (song) => {
        get()._addToLibrary(song)
        const trimmed = get()._trimSong(song)
        const songs = get().songs
        if (!songs.find(s => s.id === song.id)) {
          set({ songs: [...songs, trimmed] })
        }
      },

      addAllToPlaylist: (newSongs) => {
        if (!newSongs?.length) return
        get()._addAllToLibrary(newSongs)
        const existing = get().songs
        const existingIds = new Set(existing.map(s => s.id))
        const toAdd = newSongs
          .filter(s => !existingIds.has(s.id))
          .map(s => get()._trimSong(s))
        if (toAdd.length > 0) {
          set({ songs: [...existing, ...toAdd] })
        }
      },

      playAll: async (newSongs) => {
        if (!newSongs?.length) return
        get()._addAllToLibrary(newSongs)
        const existing = get().songs
        const existingIds = new Set(existing.map(s => s.id))
        const toAdd = newSongs
          .filter(s => !existingIds.has(s.id))
          .map(s => get()._trimSong(s))
        const merged = [...existing, ...toAdd]
        set({ songs: merged })
        const firstNew = newSongs[0]
        const idx = merged.findIndex(s => s.id === firstNew.id)
        if (idx >= 0) {
          await get().playSong(merged[idx])
        }
      },

      removeFromPlaylist: (songId) => {
        // Only remove from play queue, NOT from library
        const songs = get().songs.filter(s => s.id !== songId)
        const currentSong = get().currentSong
        if (currentSong?.id === songId) {
          get().stop()
          set({ currentSong: null, currentIndex: -1 })
        }
        set({ songs })
      },

      clearPlaylist: () => {
        // Only clear play queue, NOT library
        get().stop()
        set({ songs: [], currentSong: null, currentIndex: -1, lyrics: [] })
      },

      clearError: () => set({ error: null }),

      // ── Favorites ───────────────────────────────

      loadFavorites: async () => {
        try {
          const res = await api.getMusicFavorites()
          if (res?.code === 0 && Array.isArray(res.data)) {
            set({ favoriteIds: res.data })
          }
        } catch { /* ignore */ }
      },

      toggleFavorite: async (songId) => {
        try {
          const res = await api.toggleMusicFavorite(songId)
          if (res?.code === 0 && res.data) {
            const ids = get().favoriteIds
            if (res.data.liked) {
              set({ favoriteIds: [...ids, songId] })
            } else {
              set({ favoriteIds: ids.filter(id => id !== songId) })
            }
            return res.data.liked
          }
        } catch { /* ignore */ }
        return false
      },

      isFavorite: (songId) => get().favoriteIds.includes(songId),

      getFavoriteSongs: () => {
        const ids = new Set(get().favoriteIds)
        return get().library.filter(s => ids.has(s.id))
      },

      // ── Categories ──────────────────────────────

      loadCategories: async () => {
        set({ categoriesLoading: true })
        try {
          const res = await api.getMusicCategories()
          if (res?.code === 0 && res.data) {
            set({ categories: res.data, categoriesLoading: false })
          }
        } catch {
          set({ categoriesLoading: false })
        }
      },

      // Online music toggle
      setOnlineMusicEnabled: (enabled) => set({ onlineMusicEnabled: enabled }),

      // View management
      setActiveView: (view) => set({ activeView: view }),
      toggleDetail: () => set((s) => ({ showDetail: !s.showDetail })),
      toggleDisplayMode: () => set(s => {
        const key = s.activeView
        const defaults = s._defaultDisplayModes
        const current = s.displayModes[key] || defaults[key] || 'list'
        return { displayModes: { ...s.displayModes, [key]: current === 'list' ? 'card' : 'list' } }
      }),
      toggleDetail: () => set((s) => ({ showDetail: !s.showDetail })),
      setShowDetail: (show) => set({ showDetail: show }),

      // Recommendation
      loadRecommendSeeds: () => {
        const seeds = musicApi.getRecommendSeeds()
        set({ recommendSeeds: seeds })
        // Auto-load the first seed
        if (seeds.length > 0 && !get().currentRecommendKey) {
          get().loadRecommendSongs(seeds[0].keyword)
        }
      },

      loadRecommendSongs: async (keyword) => {
        const cache = get().recommendCache
        if (cache[keyword]) {
          set({ currentRecommendKey: keyword })
          return cache[keyword]
        }
        set({ recommendLoading: true, currentRecommendKey: keyword })
        try {
          const songs = await musicApi.getRecommendSongs(keyword, { count: 30 })
          const withCovers = await musicApi.batchBuildCoverUrls(songs.slice(0, 10))
          const finalSongs = [...withCovers, ...songs.slice(10)]
          set({
            recommendCache: { ...get().recommendCache, [keyword]: finalSongs },
            recommendLoading: false,
          })
          return finalSongs
        } catch (e) {
          console.error('Load recommend failed:', e)
          set({ recommendLoading: false })
          return []
        }
      },

      getActiveRecommendSongs: () => {
        const { currentRecommendKey, recommendCache } = get()
        return recommendCache[currentRecommendKey] || []
      },

      // ─── Local Scanner ─────────────────────────────

      scanLocalMusicPath: async (path, recursive = true) => {
        if (!path?.trim()) return
        set({ scanLoading: true, scanError: null, scanResult: null })
        try {
          const res = await api.scanLocalMusic(path.trim(), recursive)
          if (res?.code === 0 && res.data) {
            const result = res.data
            set({ scanResult: result })
            if (result.songs?.length > 0) {
              // Add to library (persistent)
              get()._addAllToLibrary(result.songs)
              // Add to play queue (trimmed)
              const existing = get().songs
              const newSongs = result.songs
                .filter((s) => !existing.find((e) => e.id === s.id))
                .map((s) => get()._trimSong(s))
              if (newSongs.length > 0) {
                set({ songs: [...existing, ...newSongs] })
              }
            }
          } else {
            set({ scanError: res?.message || '扫描失败' })
          }
        } catch (e) {
          console.error('Scan failed:', e)
          set({ scanError: e.message || '扫描失败' })
        } finally {
          set({ scanLoading: false })
        }
      },

      loadScanDirs: async () => {
        set({ scanDirsLoading: true })
        try {
          const res = await api.getMusicScanDirs()
          if (res?.code === 0) {
            set({ scanDirs: res.data || [] })
          }
        } catch (e) {
          console.error('Load scan dirs failed:', e)
        } finally {
          set({ scanDirsLoading: false })
        }
      },

      addScanDir: async (data) => {
        try {
          const res = await api.addMusicScanDir(data)
          if (res?.code === 0) {
            await get().loadScanDirs()
            return true
          }
          set({ error: res?.message || '添加失败' })
          return false
        } catch (e) {
          set({ error: e.message || '添加失败' })
          return false
        }
      },

      removeScanDir: async (dirId) => {
        try {
          const res = await api.removeMusicScanDir(dirId)
          if (res?.code === 0) {
            await get().loadScanDirs()
            return true
          }
          set({ error: res?.message || '删除失败' })
          return false
        } catch (e) {
          set({ error: e.message || '删除失败' })
          return false
        }
      },

      updateScanDir: async (dirId, data) => {
        try {
          const res = await api.updateMusicScanDir(dirId, data)
          if (res?.code === 0) {
            await get().loadScanDirs()
            return true
          }
          set({ error: res?.message || '更新失败' })
          return false
        } catch (e) {
          set({ error: e.message || '更新失败' })
          return false
        }
      },

      loadWatcherStatus: async () => {
        try {
          const res = await api.getMusicWatcherStatus()
          if (res?.code === 0) {
            set({ watcherStatus: res.data })
          }
        } catch (e) {
          console.error('Load watcher status failed:', e)
        }
      },

      startWatcher: async () => {
        try {
          const res = await api.startMusicWatcher()
          if (res?.code === 0) {
            await get().loadWatcherStatus()
            return true
          }
          return false
        } catch {
          return false
        }
      },

      stopWatcher: async () => {
        try {
          const res = await api.stopMusicWatcher()
          if (res?.code === 0) {
            await get().loadWatcherStatus()
            return true
          }
          return false
        } catch {
          return false
        }
      },

      clearScanResults: () => set({ scanResult: null, scanError: null }),

      // ─── DLNA ─────────────────────────────────────

      loadDLNADevices: async () => {
        set({ dlnaLoading: true })
        try {
          const res = await api.getDLNADevices()
          if (res?.code === 0) {
            set({ dlnaDevices: res.data || [] })
          }
        } catch (e) {
          console.error('Load DLNA devices failed:', e)
        } finally {
          set({ dlnaLoading: false })
        }
      },

      discoverDLNADevices: async (timeout = 5) => {
        set({ dlnaLoading: true })
        try {
          const res = await api.discoverDLNADevices(timeout)
          if (res?.code === 0) {
            // Backend returns { devices: [...], total: N }, extract the devices array
            set({ dlnaDevices: res.data?.devices || res.data || [] })
          }
        } catch (e) {
          console.error('Discover DLNA failed:', e)
        } finally {
          set({ dlnaLoading: false })
        }
      },

      selectDLNADevice: (device) => {
        set({ selectedDLNADevice: device })
      },

      castToDLNA: async (deviceId, songId, audioUrl) => {
        try {
          set({ dlnaLoading: true })
          const res = await api.castToDLNA(deviceId, songId, audioUrl)
          if (res?.code === 0) {
            set({ isDLNACasting: true, dlnaPlayState: 'playing' })
            return true
          }
          set({ error: res?.message || '投屏失败' })
          return false
        } catch (e) {
          set({ error: e.message || '投屏失败' })
          return false
        } finally {
          set({ dlnaLoading: false })
        }
      },

      stopDLNACast: async (deviceId) => {
        try {
          set({ dlnaLoading: true })
          const res = await api.stopDLNACast(deviceId)
          if (res?.code === 0) {
            set({ isDLNACasting: false, dlnaPlayState: 'stopped' })
            return true
          }
          return false
        } catch (e) {
          console.error('Stop DLNA cast failed:', e)
          return false
        } finally {
          set({ dlnaLoading: false })
        }
      },

      pauseDLNA: async (deviceId) => {
        try {
          const res = await api.pauseDLNA(deviceId)
          if (res?.code === 0) {
            set({ dlnaPlayState: 'paused' })
            return true
          }
          return false
        } catch (e) {
          console.error('Pause DLNA failed:', e)
          return false
        }
      },

      playDLNA: async (deviceId) => {
        try {
          const res = await api.playDLNA(deviceId)
          if (res?.code === 0) {
            set({ dlnaPlayState: 'playing' })
            return true
          }
          return false
        } catch (e) {
          console.error('Play DLNA failed:', e)
          return false
        }
      },

      _handleEnded: () => {
        const { repeatMode, songs, currentIndex } = get()
        if (repeatMode === REPEAT_MODES.SINGLE) {
          const audio = get()._audio
          if (audio) {
            audio.currentTime = 0
            audio.play().catch(() => {})
          }
          return
        }
        if (songs.length === 0) return
        let nextIdx
        if (repeatMode === REPEAT_MODES.SHUFFLE) {
          nextIdx = Math.floor(Math.random() * songs.length)
        } else {
          nextIdx = currentIndex + 1
          if (nextIdx >= songs.length) nextIdx = 0
        }
        if (songs[nextIdx]) get().playSong(songs[nextIdx])
      },

      _startPositionUpdate: () => {
        get()._stopPositionUpdate()
        const timer = setInterval(() => {
          const audio = get()._audio
          if (audio && !audio.paused) {
            const pos = audio.currentTime
            set({ position: pos })
            get().updateCurrentLyric(pos)
          }
        }, 200)
        set({ _positionTimer: timer })
      },

      _stopPositionUpdate: () => {
        const timer = get()._positionTimer
        if (timer) {
          clearInterval(timer)
          set({ _positionTimer: null })
        }
      },

      updateCurrentLyric: (currentTime) => {
        const { lyrics } = get()
        if (!lyrics || lyrics.length === 0) {
          if (get().currentLyricIndex !== -1) set({ currentLyricIndex: -1 })
          return
        }
        let index = -1
        for (let i = lyrics.length - 1; i >= 0; i--) {
          if (currentTime >= lyrics[i].time) { index = i; break }
        }
        if (index !== get().currentLyricIndex) set({ currentLyricIndex: index })
      },

      _setFavicon: (url) => {
        try {
          let link = document.querySelector("link[rel~='icon']")
          if (!link) {
            link = document.createElement('link')
            link.rel = 'icon'
            document.head.appendChild(link)
          }
          link.href = url
        } catch {}
      },
    }),
    {
      name: 'music-player-v2',
      partialize: (state) => ({
        volume: state.volume,
        isMuted: state.isMuted,
        repeatMode: state.repeatMode,
        activeView: state.activeView,
        displayModes: state.displayModes,
        favoriteIds: state.favoriteIds || [],
        onlineMusicEnabled: state.onlineMusicEnabled,
        library: state.library.map((s) => ({
          id: s.id,
          title: s.title,
          artist: s.artist,
          album: s.album,
          duration: s.duration || 0,
          cover_url: s.cover_url || '',
          picId: s.picId || '',
          lyricId: s.lyricId || '',
          source: s.source || '',
          audio_url: s.audio_url || '',
        })),
      }),
      merge: (persisted, current) => {
        // Fix cover URLs for local songs on load
        const library = (persisted.library || []).map((s) => {
          if (s.id?.startsWith('local_') && !s.cover_url) {
            return { ...s, cover_url: `/api/music/cover/${s.id}` }
          }
          return s
        })
        return {
          ...current,
          ...persisted,
          library,
          songs: [], // Always start with empty play queue
          onlineMusicEnabled: persisted.onlineMusicEnabled ?? false,
        }
      },
    }
  )
)

export { REPEAT_MODES, REPEAT_LABELS }
