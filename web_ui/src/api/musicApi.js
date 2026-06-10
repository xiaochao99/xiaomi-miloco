const BASE_URL = 'https://music-api.gdstudio.xyz/api.php'
const DEFAULT_SOURCE = 'netease'

const buildUrl = (params) => {
  const url = new URL(BASE_URL)
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null) url.searchParams.set(k, v)
  })
  return url.toString()
}

const fetchJson = async (params) => {
  const url = buildUrl(params)
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`API error: ${resp.status}`)
  const text = await resp.text()
  try { return JSON.parse(text) } catch { throw new Error('Invalid JSON') }
}

export const searchSongs = async (keyword, { count = 20, pages = 1, source = DEFAULT_SOURCE } = {}) => {
  if (!keyword?.trim()) return []
  const data = await fetchJson({ types: 'search', source, name: keyword.trim(), count, pages })
  if (!Array.isArray(data)) return []
  return data.map((item) => ({
    id: String(item.id),
    title: item.name || '未知歌曲',
    artist: Array.isArray(item.artist) ? item.artist.join(' / ') : (item.artist || '未知歌手'),
    album: item.album || '未知专辑',
    picId: item.pic_id || '',
    lyricId: item.lyric_id || String(item.id),
    source: item.source || source,
    audio_url: null,
    cover_url: null,
    lyrics: null,
  }))
}

export const getSongUrl = async (trackId, { source = DEFAULT_SOURCE, br = 320 } = {}) => {
  const data = await fetchJson({ types: 'url', source, id: trackId, br })
  return data?.url || null
}

export const getSongPic = async (picId, { source = DEFAULT_SOURCE, size = 300 } = {}) => {
  if (!picId) return null
  const data = await fetchJson({ types: 'pic', source, id: picId, size })
  return data?.url || null
}

export const getSongLyric = async (trackId, { source = DEFAULT_SOURCE } = {}) => {
  const data = await fetchJson({ types: 'lyric', source, id: trackId })
  return {
    lyric: data?.lyric || '',
    tlyric: data?.tlyric || '',
  }
}

export const parseLRC = (lrcText) => {
  if (!lrcText || typeof lrcText !== 'string') return []
  const lines = lrcText.split('\n')
  const result = []
  const timeRegex = /\[(\d{2}):(\d{2})\.(\d{2,3})\]/

  for (const line of lines) {
    const match = timeRegex.exec(line)
    if (!match) continue
    const minutes = parseInt(match[1], 10)
    const seconds = parseInt(match[2], 10)
    const ms = parseInt(match[3].padEnd(3, '0'), 10)
    const time = minutes * 60 + seconds + ms / 1000
    const text = line.replace(/\[\d{2}:\d{2}\.\d{2,3}\]/g, '').trim()
    if (text) {
      result.push({ time, text })
    }
  }
  return result.sort((a, b) => a.time - b.time)
}

export const enrichSong = async (song) => {
  const enriched = { ...song }
  try {
    if (!enriched.audio_url && enriched.id) {
      enriched.audio_url = await getSongUrl(enriched.id, { source: enriched.source })
    }
  } catch (e) { console.warn('Failed to get URL:', e) }

  try {
    if (!enriched.cover_url && enriched.picId) {
      enriched.cover_url = await getSongPic(enriched.picId, { source: enriched.source })
    }
  } catch (e) { console.warn('Failed to get pic:', e) }

  try {
    if (!enriched.lyrics && enriched.lyricId) {
      const lyricData = await getSongLyric(enriched.lyricId, { source: enriched.source })
      if (lyricData?.lyric) {
        enriched.lyrics = parseLRC(lyricData.lyric)
      }
    }
  } catch (e) { console.warn('Failed to get lyrics:', e) }

  return enriched
}

export const buildCoverUrl = (picId, source = DEFAULT_SOURCE, size = 300) => {
  if (!picId) return null
  return buildUrl({ types: 'pic', source, id: picId, size })
}

// ─── Discovery & Charts ────────────────────────────────────────

/**
 * Get hot/trending search terms
 */
export const getHotSearch = async ({ source = DEFAULT_SOURCE } = {}) => {
  try {
    const data = await fetchJson({ types: 'hot', source })
    if (!Array.isArray(data)) return []
    return data.map((item, idx) => ({
      rank: idx + 1,
      keyword: item.name || item.keyword || String(item),
      score: item.score || 0,
    }))
  } catch {
    return []
  }
}

/**
 * Get playlist detail (song list) by playlist ID
 */
export const getPlaylistDetail = async (playlistId, { source = DEFAULT_SOURCE } = {}) => {
  try {
    const data = await fetchJson({ types: 'playlist', source, id: playlistId })
    if (!data?.playlist) return null
    const playlist = data.playlist
    return {
      id: String(playlist.id),
      name: playlist.name || '未知歌单',
      cover: playlist.coverImgUrl || playlist.cover || '',
      description: playlist.description || '',
      songs: (playlist.tracks || []).map((item) => ({
        id: String(item.id),
        title: item.name || '未知歌曲',
        artist: Array.isArray(item.artist) ? item.artist.join(' / ') : (item.artist || '未知歌手'),
        album: item.album || '未知专辑',
        picId: item.pic_id || item.al?.picId || '',
        lyricId: item.lyric_id || String(item.id),
        source: item.source || source,
        duration: item.duration ? Math.round(item.duration / 1000) : 0,
        audio_url: null,
        cover_url: null,
        lyrics: null,
      })),
    }
  } catch {
    return null
  }
}

/**
 * Curated recommendation data (since the API doesn't have a recommend endpoint)
 * Uses popular Chinese songs as seed data for the discovery page.
 */
export const getRecommendSeeds = () => [
  { keyword: '周杰伦', label: '周杰伦', color: '#1a3a5c' },
  { keyword: '林俊杰', label: '林俊杰', color: '#3a1a5c' },
  { keyword: '陈奕迅', label: '陈奕迅', color: '#5c1a3a' },
  { keyword: '薛之谦', label: '薛之谦', color: '#1a5c3a' },
  { keyword: '邓紫棋', label: '邓紫棋', color: '#5c3a1a' },
  { keyword: '毛不易', label: '毛不易', color: '#3a5c1a' },
  { keyword: '李荣浩', label: '李荣浩', color: '#1a5c5c' },
  { keyword: '华语流行', label: '华语流行', color: '#5c1a1a' },
]

/**
 * Get recommended songs for a given keyword (used by discovery page)
 */
export const getRecommendSongs = async (keyword, { count = 20, source = DEFAULT_SOURCE } = {}) => {
  return searchSongs(keyword, { count, source })
}

/**
 * Build multiple cover URLs in parallel for a list of songs
 */
export const batchBuildCoverUrls = async (songs, source = DEFAULT_SOURCE) => {
  const results = await Promise.allSettled(
    songs.map(async (song) => {
      if (song.cover_url) return song
      if (song.picId) {
        const url = await getSongPic(song.picId, { source: song.source || source })
        return { ...song, cover_url: url }
      }
      return song
    })
  )
  return results.map((r, i) => (r.status === 'fulfilled' ? r.value : songs[i]))
}
