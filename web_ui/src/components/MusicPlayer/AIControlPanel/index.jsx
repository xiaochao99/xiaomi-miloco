import React, { useState, useRef, useEffect } from 'react'
import { Input, Button, Tag, Space, Typography } from 'antd'
import {
  SendOutlined, RobotOutlined, UserOutlined,
  PlayCircleFilled, PauseCircleFilled, StepForwardFilled,
  StepBackwardFilled, SwapOutlined, SoundOutlined,
  CheckCircleFilled, CloseCircleFilled, BulbOutlined,
  CustomerServiceOutlined
} from '@ant-design/icons'
import { useMusicPlayerStore, REPEAT_MODES } from '@/stores/musicPlayerStore'
import styles from './index.module.less'

const { Text } = Typography

const QUICK_COMMANDS = [
  { label: '播放', icon: <PlayCircleFilled />, command: '播放音乐' },
  { label: '暂停', icon: <PauseCircleFilled />, command: '暂停播放' },
  { label: '下一首', icon: <StepForwardFilled />, command: '下一首' },
  { label: '上一首', icon: <StepBackwardFilled />, command: '上一首' },
  { label: '单曲循环', icon: <SwapOutlined />, command: '切换单曲循环' },
  { label: '列表循环', icon: <SwapOutlined />, command: '切换列表循环' },
  { label: '随机播放', icon: <SwapOutlined />, command: '随机播放' },
]

const COMMAND_EXAMPLES = [
  '播放周杰伦的歌',
  '下一首',
  '暂停',
  '单曲循环',
  '搜索晴天',
]

const AIControlPanel = ({ onClose: _close }) => {
  const {
    aiControl, isControlling, currentSong,
    playbackState, repeatMode, isShuffle,
  } = useMusicPlayerStore()

  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: '你好！我是AI音乐助手，可以用自然语言控制音乐播放。试试说"播放周杰伦的歌"或"下一首"！',
      type: 'welcome',
    },
  ])
  const [inputValue, setInputValue] = useState('')
  const [showExamples, setShowExamples] = useState(true)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleSend = async () => {
    const text = inputValue.trim()
    if (!text) {return}

    const userMessage = { role: 'user', content: text }
    setMessages((prev) => [...prev, userMessage])
    setInputValue('')
    setShowExamples(false)

    const thinkingMessage = {
      role: 'assistant',
      content: '',
      type: 'thinking',
    }
    setMessages((prev) => [...prev, thinkingMessage])

    try {
      const result = await aiControl(text)

      setMessages((prev) => prev.filter(m => m !== thinkingMessage))

      if (result.success) {
        const actionIcons = {
          play: <PlayCircleFilled />,
          pause: <PauseCircleFilled />,
          next: <StepForwardFilled />,
          previous: <StepBackwardFilled />,
          set_repeat: <SwapOutlined />,
          search: <SoundOutlined />,
          toggle_shuffle: <SwapOutlined />,
        }
        const aiMessage = {
          role: 'assistant',
          content: result.message || '操作成功',
          type: 'action',
          action: result.action,
          icon: actionIcons[result.action],
          success: true,
        }
        setMessages((prev) => [...prev, aiMessage])
      } else {
        const errorMessage = {
          role: 'assistant',
          content: result.error || '无法执行该操作',
          type: 'error',
          success: false,
        }
        setMessages((prev) => [...prev, errorMessage])
      }
    } catch (error) {
      setMessages((prev) => prev.filter(m => m !== thinkingMessage))
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: error.message || '发生了错误',
        type: 'error',
        success: false,
      }])
    }
  }

  const handleQuickCommand = (command) => {
    setInputValue(command)
  }

  const handleExampleClick = (example) => {
    setInputValue(example)
    setTimeout(() => inputRef.current?.focus(), 100)
  }

  const getPlaybackStateText = () => {
    switch (playbackState) {
      case 'playing': return '播放中'
      case 'paused': return '已暂停'
      case 'stopped': return '已停止'
      default: return '未知'
    }
  }

  const getRepeatModeText = () => {
    switch (repeatMode) {
      case REPEAT_MODES.SINGLE: return '单曲循环'
      case REPEAT_MODES.LIST: return '列表循环'
      case REPEAT_MODES.SHUFFLE: return '随机播放'
      default: return '列表循环'
    }
  }

  return (
    <div className={styles.panel}>
      <div className={styles.statusBar}>
        <div className={styles.statusGrid}>
          <div className={styles.statusItem}>
            <span className={styles.statusLabel}>歌曲</span>
            <span className={styles.statusValue}>
              {currentSong ? `${currentSong.title} - ${currentSong.artist}` : '未播放'}
            </span>
          </div>
          <div className={styles.statusRow}>
            <div className={styles.statusChip}>
              <span className={styles.chipDot} style={{
                background: playbackState === 'playing' ? '#52c41a' : '#8c8c8c',
              }} />
              {getPlaybackStateText()}
            </div>
            <div className={styles.statusChip}>
              {getRepeatModeText()}
            </div>
            {isShuffle && (
              <div className={styles.statusChip}>
                随机
              </div>
            )}
          </div>
        </div>
      </div>

      <div className={styles.quickCommands}>
        <div className={styles.quickLabel}>
          <BulbOutlined /> 快捷指令
        </div>
        <div className={styles.quickGrid}>
          {QUICK_COMMANDS.map((cmd) => (
            <Button
              key={cmd.label}
              type="text"
              size="small"
              icon={cmd.icon}
              onClick={() => handleQuickCommand(cmd.command)}
              className={styles.quickBtn}
            >
              {cmd.label}
            </Button>
          ))}
        </div>
      </div>

      <div className={styles.messageList}>
        {messages.map((msg, index) => (
          <div
            key={index}
            className={`${styles.message} ${styles[msg.role]} ${msg.type === 'thinking' ? styles.thinking : ''}`}
          >
            <div className={styles.avatar}>
              {msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
            </div>
            <div className={styles.bubble}>
              {msg.type === 'thinking' ? (
                <div className={styles.thinkingDots}>
                  <span className={styles.dot} />
                  <span className={styles.dot} />
                  <span className={styles.dot} />
                </div>
              ) : (
                <>
                  <div className={styles.messageText}>
                    {msg.content.split('\n').map((line, i) => (
                      <React.Fragment key={i}>
                        {line}
                        {i < msg.content.split('\n').length - 1 && <br />}
                      </React.Fragment>
                    ))}
                  </div>
                  {msg.action && (
                    <div className={styles.actionFeedback}>
                      {msg.icon && <span className={styles.actionIcon}>{msg.icon}</span>}
                      <Tag
                        color={msg.success ? 'success' : 'error'}
                        className={styles.actionTag}
                      >
                        {msg.success ? '执行成功' : '执行失败'}
                      </Tag>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {showExamples && messages.length <= 1 && (
        <div className={styles.examples}>
          <Text className={styles.examplesLabel}>试试这些指令：</Text>
          <div className={styles.exampleChips}>
            {COMMAND_EXAMPLES.map((ex, i) => (
              <Tag
                key={i}
                className={styles.exampleChip}
                onClick={() => handleExampleClick(ex)}
              >
                {ex}
              </Tag>
            ))}
          </div>
        </div>
      )}

      <div className={styles.inputBar}>
        <Input
          ref={inputRef}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder="输入指令，如：播放周杰伦的歌..."
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          className={styles.inputField}
          variant="borderless"
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSend}
          loading={isControlling}
          className={styles.sendBtn}
          disabled={!inputValue.trim()}
          style={{ background: !inputValue.trim() ? 'rgba(255,255,255,0.1)' : '#ec4141', borderColor: '#ec4141' }}
        />
      </div>
    </div>
  )
}

export default AIControlPanel
