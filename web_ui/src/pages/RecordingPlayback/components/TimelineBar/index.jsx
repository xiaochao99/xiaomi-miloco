import React, { useRef, useEffect, useCallback, useState, useImperativeHandle, forwardRef } from 'react';
import { Spin } from 'antd';
import { useTranslation } from 'react-i18next';

let mpegtsModule = null;

const loadMpegts = async () => {
  if (mpegtsModule) return mpegtsModule;
  const mod = await import('mpegts.js');
  mpegtsModule = mod.default || mod;
  return mpegtsModule;
};

const MpegtsPlayer = forwardRef(({
  src,
  autoPlay = false,
  onPlay,
  onPause,
  onEnded,
  onError,
  onTimeUpdate,
  onDurationChange,
  onSeeked,
  onLoadedData,
}, ref) => {
  const { t } = useTranslation();
  const videoRef = useRef(null);
  const playerRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useImperativeHandle(ref, () => ({
    getVideoElement: () => videoRef.current,
  }));

  const destroyPlayer = useCallback(() => {
    if (playerRef.current) {
      try {
        playerRef.current.pause();
        playerRef.current.detachMediaElement();
        playerRef.current.destroy();
      } catch (e) {
        console.warn('Error destroying mpegts player:', e);
      }
      playerRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!src) return;

    let cancelled = false;

    const init = async () => {
      setLoading(true);
      setError(null);
      destroyPlayer();

      try {
        const mpegts = await loadMpegts();

        if (cancelled) return;

        if (!mpegts.isSupported()) {
          setError(t('recording.playback.mpegtsNotSupported'));
          setLoading(false);
          return;
        }

        const video = videoRef.current;
        if (!video) return;

        const player = mpegts.createPlayer(
          {
            type: 'mpegts',
            isLive: false,
            url: src,
            hasAudio: true,
            hasVideo: true,
          },
          {
            enableWorker: true,
            enableStashBuffer: true,
            stashInitialSize: 128 * 1024,
            lazyLoad: true,
            lazyLoadMaxDuration: 3 * 60,
            deferLoadAfterSourceOpen: true,
          },
        );

        player.attachMediaElement(video);
        player.load();

        player.on(mpegts.Events.ERROR, (errorType, errorDetail) => {
          console.error('mpegts.js error:', errorType, errorDetail);
          if (!cancelled) {
            setError(t('recording.playback.playFailed'));
            onError?.(new Error(`${errorType}: ${errorDetail}`));
          }
        });

        player.on(mpegts.Events.LOADING_COMPLETE, () => {
          if (!cancelled) {
            onEnded?.();
          }
        });

        video.addEventListener('loadeddata', () => {
          if (!cancelled) {
            setLoading(false);
            onLoadedData?.();
          }
        });

        video.addEventListener('canplay', () => {
          if (!cancelled) {
            setLoading(false);
            if (autoPlay) {
              video.play().catch(() => {});
            }
          }
        });

        video.addEventListener('play', () => onPlay?.());
        video.addEventListener('pause', () => onPause?.());
        video.addEventListener('ended', () => onEnded?.());
        video.addEventListener('seeked', () => onSeeked?.());
        video.addEventListener('timeupdate', () => {
          onTimeUpdate?.(video.currentTime);
        });
        video.addEventListener('durationchange', () => {
          onDurationChange?.(video.duration);
        });

        video.addEventListener('error', () => {
          if (!cancelled) {
            const mediaError = video.error;
            console.error('Video element error:', mediaError);
            setError(t('recording.playback.playFailed'));
            onError?.(mediaError);
          }
        });

        playerRef.current = player;
      } catch (err) {
        console.error('Failed to initialize mpegts.js player:', err);
        if (!cancelled) {
          setError(t('recording.playback.playFailed'));
          onError?.(err);
          setLoading(false);
        }
      }
    };

    init();

    return () => {
      cancelled = true;
      destroyPlayer();
    };
  }, [src]);

  const seek = useCallback((time) => {
    const video = videoRef.current;
    if (video) {
      video.currentTime = time;
    }
  }, []);

  const play = useCallback(() => {
    const video = videoRef.current;
    if (video) {
      video.play().catch(() => {});
    }
  }, []);

  const pause = useCallback(() => {
    const video = videoRef.current;
    if (video) {
      video.pause();
    }
  }, []);

  const getVideoElement = useCallback(() => videoRef.current, []);

  if (error) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 40,
        color: '#fff',
        background: '#000',
        borderRadius: 8,
      }}>
        <p style={{ margin: '8px 0' }}>{error}</p>
        <p style={{ fontSize: 12, color: '#aaa' }}>mpegts.js</p>
        <button
          onClick={() => window.location.reload()}
          style={{
            marginTop: 16,
            padding: '8px 24px',
            background: '#00bdc3',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
          }}
        >
          {t('common.retry')}
        </button>
      </div>
    );
  }

  return (
    <div style={{ position: 'relative', width: '100%', background: '#000', borderRadius: 8, overflow: 'hidden' }}>
      <video
        ref={videoRef}
        style={{ width: '100%', height: 'auto', display: 'block' }}
        playsInline
        controls={false}
      />
      {loading && (
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'rgba(0, 0, 0, 0.8)',
          color: '#fff',
        }}>
          <Spin size="large" />
          <p style={{ marginTop: 16, fontSize: 14 }}>{t('common.loading')}</p>
        </div>
      )}
    </div>
  );
});

MpegtsPlayer.displayName = 'MpegtsPlayer';

export default MpegtsPlayer;
