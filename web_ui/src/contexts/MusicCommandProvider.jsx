import { useEffect } from 'react'
import { useMusicPlayerStore } from '@/stores/musicPlayerStore'

/**
 * Global provider: initializes audio and starts MCP command polling.
 * Pauses polling when tab is hidden.
 */
const MusicCommandProvider = ({ children }) => {
  const initialize = useMusicPlayerStore((s) => s.initialize)
  const startCommandPolling = useMusicPlayerStore((s) => s.startCommandPolling)
  const stopCommandPolling = useMusicPlayerStore((s) => s.stopCommandPolling)

  useEffect(() => {
    initialize()
    startCommandPolling()

    const handleVisibility = () => {
      if (document.hidden) {
        stopCommandPolling()
      } else {
        startCommandPolling()
      }
    }

    document.addEventListener('visibilitychange', handleVisibility)
    return () => {
      stopCommandPolling()
      document.removeEventListener('visibilitychange', handleVisibility)
    }
  }, [initialize, startCommandPolling, stopCommandPolling])

  return children
}

export default MusicCommandProvider
