import { useRef, useState, useEffect } from 'react'

/**
 * Only loads the image when it scrolls into the viewport.
 * Uses IntersectionObserver with a rootMargin to preload slightly before visible.
 */
const LazyImage = ({ src, alt = '', className = '', onError, fallback = null, rootMargin = '200px' }) => {
  const imgRef = useRef(null)
  const [shouldLoad, setShouldLoad] = useState(false)
  const [hasError, setHasError] = useState(false)

  useEffect(() => {
    const node = imgRef.current
    if (!node) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShouldLoad(true)
          observer.unobserve(node)
        }
      },
      { rootMargin }
    )

    observer.observe(node)
    return () => observer.disconnect()
  }, [rootMargin])

  if (!shouldLoad) {
    return <div ref={imgRef} className={className} style={{ minHeight: '40px', minWidth: '40px' }} />
  }

  if (hasError && fallback) {
    return fallback
  }

  return (
    <img
      ref={imgRef}
      src={src}
      alt={alt}
      className={className}
      onError={(e) => {
        setHasError(true)
        onError?.(e)
      }}
    />
  )
}

export default LazyImage
