import React, { useEffect, useState } from 'react'
import { List, Button, Tag, Empty, Typography, Input } from 'antd'
import {
  PlayCircleFilled, PauseCircleFilled,
  ClockCircleOutlined, CustomerServiceOutlined,
  SearchOutlined, ClearOutlined
} from '@ant-design/icons'
import { useMusicPlayerStore } from '@/stores/musicPlayerStore'
import styles from './index.module.less'

const { Text } = Typography

const PlaylistPanel = ({ visible, onClose: _onClose }) => {
  const {
    songs, currentSong, playbackState, playSong,
    loadPlaylists,
  } = useMusicPlayerStore()

  const [filterText, setFilterText] = useState('')

  useEffect(() => {
    if (visible) {
      loadPlaylists()
    }
  }, [visible, loadPlaylists])

  const formatDuration = (seconds) => {
    if (!seconds || isNaN(seconds)) {return '00:00'}
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  const handlePlaySong = async (songId) => {
    await playSong(songId)
  }

  const isCurrentSong = (song) => currentSong && currentSong.id === song.id
  const isPlaying = (song) => isCurrentSong(song) && playbackState === 'playing'

  const filteredSongs = filterText
    ? songs.filter(s =>
        (s.title?.toLowerCase().includes(filterText.toLowerCase())) ||
        (s.artist?.toLowerCase().includes(filterText.toLowerCase()))
      )
    : songs

  if (!visible) {return null}

  return (
    <div className={styles.panel}>
      <div className={styles.filterBar}>
        <Input
          placeholder="筛选列表..."
          prefix={<SearchOutlined />}
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
          variant="borderless"
          className={styles.filterInput}
          allowClear
        />
        <Text className={styles.songCount}>{songs.length} 首</Text>
      </div>

      <div className={styles.listContainer}>
        {filteredSongs.length === 0 ? (
          <Empty
            description={filterText ? '无匹配结果' : '暂无歌曲'}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            className={styles.empty}
          />
        ) : (
          <List
            className={styles.songList}
            dataSource={filteredSongs}
            renderItem={(song) => (
              <List.Item
                className={`${styles.songItem} ${isCurrentSong(song) ? styles.active : ''}`}
                onClick={() => handlePlaySong(song.id)}
                actions={[
                  <span key="time" className={styles.duration}>
                    <ClockCircleOutlined className={styles.durationIcon} />
                    {formatDuration(song.duration)}
                  </span>
                ]}
              >
                <div className={styles.songAvatar}>
                  {isPlaying(song) ? (
                    <PauseCircleFilled className={styles.playingIcon} />
                  ) : (
                    <PlayCircleFilled className={styles.playIcon} />
                  )}
                </div>
                <div className={styles.songMeta}>
                  <div className={styles.songTitleRow}>
                    <span className={styles.songTitle}>{song.title}</span>
                    {isCurrentSong(song) && (
                      <Tag className={styles.playingTag}>
                        {playbackState === 'playing' ? '播放中' : '已暂停'}
                      </Tag>
                    )}
                  </div>
                  <div className={styles.songInfoRow}>
                    <span className={styles.artist}>{song.artist || '未知歌手'}</span>
                    {song.album && (
                      <>
                        <span className={styles.separator}>·</span>
                        <span className={styles.album}>{song.album}</span>
                      </>
                    )}
                  </div>
                </div>
              </List.Item>
            )}
          />
        )}
      </div>
    </div>
  )
}

export default PlaylistPanel
