import { useEffect } from 'react'
import { useMusicPlayerStore } from '@/stores/musicPlayerStore'

/**
 * Global provider: initializes audio.
 */
const MusicCommandProvider = ({ children }) => {
  const initialize = useMusicPlayerStore((s) => s.initialize)

  useEffect(() => {
    initialize()
  }, [initialize])

  return children
}

export default MusicCommandProvider
