/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useEffect, useRef, useState } from 'react'
import { Spin, message } from 'antd'
import { useTranslation } from 'react-i18next';
import { isFirefox, isEdge, sleep } from '@/utils/util';
import DefaultCameraBg from '@/assets/images/default-camera-bg.png'

/**
 * Detect video codec from binary data
 * 从二进制数据中检测视频编码格式
 *
 * @param {Uint8Array} data - Binary video data
 * @returns {string} Detected codec type ('h264', 'h265', or 'unknown')
 */
const detectCodec = (data) => {
  let i = 0;
  while (i < data.length - 6) {
    if (
      data[i] === 0x00 && data[i + 1] === 0x00 &&
      ((data[i + 2] === 0x00 && data[i + 3] === 0x01) || data[i + 2] === 0x01)
    ) {
      const nalStart = data[i + 2] === 0x01 ? i + 3 : i + 4;
      const byte = data[nalStart];
      const h264Type = byte & 0x1f;
      // H.265 Type is bits 1-6. Bit 0 must be 0 for LayerId=0 (Base layer).
      // Also Bit 7 (Forbidden) must be 0.
      const isH265Candidate = (byte & 0x81) === 0;
      const h265Type = (byte >> 1) & 0x3f;

      if ([5, 7, 8].includes(h264Type)) {
          console.log(`Detected H.264: Byte=${byte.toString(16)}, Type=${h264Type}`);
          return 'h264';
      }
      if (isH265Candidate && [32, 33, 34, 19, 20].includes(h265Type)) {
          console.log(`Detected H.265: Byte=${byte.toString(16)}, Type=${h265Type}`);
          return 'h265';
      }
    }
    i++;
  }
  return 'unknown';
}

/**
 * VideoPlayer Component - WebCodecs-based video player for camera streams
 * 视频播放器组件 - 基于WebCodecs的摄像头流视频播放器
 *
 * @param {Object} props - Component props
 * @param {string} [props.codec='avc1.42E01E'] - Video codec format
 * @param {string} [props.poster] - Poster image URL
 * @param {Object} [props.style] - Custom style object
 * @param {string} props.cameraId - Camera device ID
 * @param {number} [props.channel=0] - Camera channel number
 * @param {Function} [props.onCanvasRef] - Canvas ref callback function
 * @returns {JSX.Element} Video player component
 */
const VideoPlayer = ({ codec = 'avc1.42E01E', poster, style, cameraId, channel, onCanvasRef, onPlay }) => {
  const { t } = useTranslation();
  const canvasRef = useRef(null)
  const wsRef = useRef(null)
  const decoderRef = useRef(null)
  const detectedCodecRef = useRef(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [show, setShow] = useState(false)
  const [isSupported, setIsSupported] = useState(null)

  // detect WebCodecs support and codec capabilities
  useEffect(() => {
    const checkSupport = async () => {
      console.log('Current environment:', {
        userAgent: navigator.userAgent,
        isSecureContext: window.isSecureContext,
        location: window.location.href,
        hasWindow: typeof window !== 'undefined',
        windowType: typeof window
      })

      const hasWebCodecs = (
        typeof window !== 'undefined' &&
        'VideoDecoder' in window &&
        'VideoFrame' in window &&
        'ImageBitmap' in window
      )

      console.log('WebCodecs API detection:', {
        hasWindow: typeof window !== 'undefined',
        hasVideoDecoder: typeof window !== 'undefined' && 'VideoDecoder' in window,
        hasVideoFrame: typeof window !== 'undefined' && 'VideoFrame' in window,
        hasImageBitmap: typeof window !== 'undefined' && 'ImageBitmap' in window,
        supported: hasWebCodecs
      })

      // Check codec support if WebCodecs is available
      if (hasWebCodecs && typeof window.VideoDecoder.isConfigSupported === 'function') {
        const codecsToCheck = [
          { codec: 'avc1.42E01E' },  // H.264 Baseline
          { codec: 'avc1.640028' },  // H.264 High
          { codec: 'hev1.1.6.L93.B0' }, // H.265 Main10
          { codec: 'hvc1.1.6.L93.B0' }, // H.265 Main10 (alternative)
        ]

        console.log('Checking codec support...');
        for (const config of codecsToCheck) {
          try {
            const support = await window.VideoDecoder.isConfigSupported(config);
            console.log(`Codec config ${support.supported ? 'supported' : 'not supported'}:`, config);
          } catch (e) {
            console.log(`Codec config check failed for ${JSON.stringify(config)}:`, e.message);
          }
        }
      }

      if (!hasWebCodecs) {
        console.warn('⚠️ WebCodecs not supported, possible reasons:')
        console.warn('1. WebCodecs is not supported in this browser (Chrome 94+, Edge 94+)')
        console.warn('2. Vite hot update environment limit, please try to force refresh the page (F5)')
        console.warn('3. WebCodecs needs to be enabled in chrome://flags')
        console.warn('4. Needs HTTPS or localhost environment')
      }

      setIsSupported(hasWebCodecs)
      return hasWebCodecs
    }

    checkSupport()
  }, [])

  /**
   * Helper to convert byte to hex string
   */
  const toHex = (v) => {
    return v.toString(16).padStart(2, '0').toUpperCase();
  }

  /**
   * Check if the data is a key frame
   * @param {Uint8Array} data - Binary video data
   * @param {string} codec - Video codec format
   * @returns {boolean} Whether the data is a key frame
   */
  const isKeyFrame = (data, codec) => {
    if (codec.startsWith('avc1') || codec.startsWith('h264')) {
      // H264
      let i = 0;
      while (i < data.length - 4) {
        if (
          data[i] === 0x00 && data[i + 1] === 0x00 &&
          ((data[i + 2] === 0x00 && data[i + 3] === 0x01) || data[i + 2] === 0x01)
        ) {
          const nalUnitType = data[i + 2] === 0x01 ? data[i + 3] & 0x1f : data[i + 4] & 0x1f;
          // SPS(7), PPS(8), IDR(5) are all critical for decoding start
          if (nalUnitType === 5 || nalUnitType === 7 || nalUnitType === 8) {
            return true;
          }
        }
        i++;
      }
      return false;
    } else if (codec.startsWith('hvc1') || codec.startsWith('hev1') || codec.startsWith('h265')) {
      // H265/HEVC
      let i = 0;
      while (i < data.length - 6) {
        if (
          data[i] === 0x00 && data[i + 1] === 0x00 &&
          ((data[i + 2] === 0x00 && data[i + 3] === 0x01) || data[i + 2] === 0x01)
        ) {
          const nalStart = data[i + 2] === 0x01 ? i + 3 : i + 4;
          const nalUnitType = (data[nalStart] >> 1) & 0x3f;
          if ([16, 17, 18, 19, 20].includes(nalUnitType)) {return true;}
        }
        i++;
      }
      return false;
    }
    // default to handle key frame
    return true;
  }

  useEffect(() => {
    if (onCanvasRef && canvasRef.current) {
      onCanvasRef(canvasRef)
    }
  }, [onCanvasRef, show])

  useEffect(() => {
    /**
     * Parse SPS to get H.264 codec string
     * @param {Uint8Array} data
     * @returns {string|null}
     */
    const getH264CodecString = (data) => {
      let i = 0;
      while (i < data.length - 4) {
        if (
          data[i] === 0x00 && data[i + 1] === 0x00 &&
          ((data[i + 2] === 0x00 && data[i + 3] === 0x01) || data[i + 2] === 0x01)
        ) {
          const nalStart = data[i + 2] === 0x01 ? i + 3 : i + 4;
          const nalUnitType = data[nalStart] & 0x1f;
          if (nalUnitType === 7) { // SPS
            const profileIdc = data[nalStart + 1];
            const constraintSet = data[nalStart + 2];
            const levelIdc = data[nalStart + 3];
            return `avc1.${toHex(profileIdc)}${toHex(constraintSet)}${toHex(levelIdc)}`;
          }
        }
        i++;
      }
      return null;
    }

    /**
     * Extract H.264 SPS and PPS data for VideoDecoderConfig description
     * @param {Uint8Array} data - Binary video data containing SPS/PPS
     * @returns {Uint8Array|null} Concatenated SPS and PPS data in AVCC format
     */
    const getH264Description = (data) => {
      let sps = null;
      let pps = null;
      let i = 0;

      while (i < data.length - 4) {
        if (
          data[i] === 0x00 && data[i + 1] === 0x00 &&
          ((data[i + 2] === 0x00 && data[i + 3] === 0x01) || data[i + 2] === 0x01)
        ) {
          const nalStart = data[i + 2] === 0x01 ? i + 3 : i + 4;
          const nalUnitType = data[nalStart] & 0x1f;

          if (nalUnitType === 7 && !sps) { // SPS
            // Find next NAL unit boundary
            let j = nalStart + 1;
            while (j < data.length - 3) {
              if (data[j] === 0x00 && data[j + 1] === 0x00 &&
                  ((data[j + 2] === 0x00 && data[j + 3] === 0x01) || data[j + 2] === 0x01)) {
                break;
              }
              j++;
            }
            sps = data.slice(nalStart, j);
          } else if (nalUnitType === 8 && !pps) { // PPS
            let j = nalStart + 1;
            while (j < data.length - 3) {
              if (data[j] === 0x00 && data[j + 1] === 0x00 &&
                  ((data[j + 2] === 0x00 && data[j + 3] === 0x01) || data[j + 2] === 0x01)) {
                break;
              }
              j++;
            }
            pps = data.slice(nalStart, j);
          }

          if (sps && pps) {
            // AVCC format: version(1) + profile(1) + compatibility(1) + level(1) + reserved(1) + NALULengthSizeMinusOne(1) + numSPS(1) + SPS length(2) + SPS + numPPS(1) + PPS length(2) + PPS
            const result = new Uint8Array(6 + 2 + sps.length + 1 + 2 + pps.length);
            let offset = 0;

            // AVCC header
            result[offset++] = 0x01; // version
            result[offset++] = sps[1]; // profile
            result[offset++] = sps[2]; // compatibility
            result[offset++] = sps[3]; // level
            result[offset++] = 0xFF; // reserved (6 bits) + NALULengthSizeMinusOne (2 bits) = 11111111
            result[offset++] = 0xE1; // reserved (3 bits) + numSPS (5 bits) = 11100001

            // SPS
            result[offset++] = (sps.length >> 8) & 0xFF;
            result[offset++] = sps.length & 0xFF;
            result.set(sps, offset);
            offset += sps.length;

            // PPS
            result[offset++] = 0x01; // numPPS
            result[offset++] = (pps.length >> 8) & 0xFF;
            result[offset++] = pps.length & 0xFF;
            result.set(pps, offset);

            console.log('Generated AVCC description:', result);
            return result;
          }
        }
        i++;
      }

      return null;
    }

    const init = async () => {
      if (!cameraId || isSupported === null) {return} // wait for support detection to complete

      if (isFirefox()) {
        setError(t('instant.deviceList.browserNotSupport'))
        message.error(t('instant.deviceList.browserNotSupport'))
        onPlay && onPlay()
        return
      }

      if (!isSupported) {
        setError(t('instant.deviceList.deviceNotSupport'))
        message.error(t('instant.deviceList.deviceNotSupport'))
        onPlay && onPlay()
        return
      }

      if (wsRef.current) {
        try {
          wsRef.current.close && wsRef.current.close();
        } catch (e) {
          console.error('Close WebSocket exception:', e);
        }
        wsRef.current = null;
      }
      if (decoderRef.current) {
        try {
          decoderRef.current.close && decoderRef.current.close();
        } catch (e) {
          if (e.name !== 'InvalidStateError') {
            console.error('Close VideoDecoder exception:', e);
          }
        }
        decoderRef.current = null;
      }
      const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const wsUrl = `${wsProtocol}://${window.location.host}${import.meta.env.VITE_API_BASE || ''}/api/miot/ws/video_stream?camera_id=${encodeURIComponent(cameraId)}&channel=${encodeURIComponent(channel)}`
      setLoading(true)
      setError(null)
      setShow(false)
      let ready = false
      const canvas = canvasRef.current
      const ctx = canvas.getContext('2d')
      await sleep(1000)

      // here assume wsUrl pushes H264 AnnexB format
      wsRef.current = new window.WebSocket(wsUrl)
      wsRef.current.binaryType = 'arraybuffer'

      // connection failed handling
      wsRef.current.onerror = (err) => {
        console.log('video player: WebSocket connection failed', err)
        setError(t('instant.deviceList.deviceConnectFailed'))
        message.error(t('instant.deviceList.deviceConnectFailed'))
        wsRef.current && wsRef.current?.close?.()
        onPlay && onPlay()
      }
      // connection closed handling
      wsRef.current.onclose = (event) => {
        console.log('video player: WebSocket connection closed')
        if (!error) {
          setError(t('instant.deviceList.deviceConnectClosed'))
          // message.error(t('instant.deviceList.deviceConnectClosed'))
        }
        const { reason = '' } = event;
        if (reason !== 'close_by_user') {
          onPlay && onPlay()
        }
      }

      /**
       * Get fallback codecs for a given codec type
       * @param {string} targetCodec - Original codec
       * @returns {string[]} List of fallback codecs to try
       */
      const getFallbackCodecs = (targetCodec) => {
        const fallbacks = [];

        // H.265/HEVC fallbacks - also include H.264 as fallback when H.265 fails
        if (targetCodec.startsWith('hev1') || targetCodec.startsWith('hvc1') || targetCodec.includes('h265')) {
          // For Edge, prioritize H.264 first since Edge has limited H.265 support
          if (isEdge()) {
            fallbacks.push(
              'avc1.640028',  // H.264 High profile
              'avc1.42E01E',  // H.264 Baseline profile
              'avc1.4D401E',  // H.264 Main profile
              'hev1.1.6.L93.B0',
              'hvc1.1.6.L93.B0',
              'hev1.1.4.L93.B0',
              'hvc1.1.4.L93.B0',
            );
          } else {
            fallbacks.push(
              'hev1.1.6.L93.B0',
              'hvc1.1.6.L93.B0',
              'hev1.1.4.L93.B0',
              'hvc1.1.4.L93.B0',
              // Fallback to H.264 codecs when H.265 is not supported
              'avc1.640028',  // H.264 High profile
              'avc1.42E01E',  // H.264 Baseline profile
              'avc1.4D401E',  // H.264 Main profile
            );
          }
        }

        // H.264 fallbacks
        if (targetCodec.startsWith('avc1') || targetCodec.includes('h264')) {
          fallbacks.push(
            'avc1.640028',  // High profile
            'avc1.42E01E',  // Baseline profile
            'avc1.4D401E',  // Main profile
            'avc1.58A01E',  // Extended profile
            'avc1.64001E',  // High profile level 3
            'avc1.640032'   // High profile level 5
          );
        }

        // Remove duplicates and the original codec
        return [...new Set(fallbacks.filter(c => c !== targetCodec))];
      }

      decoderRef.current = new window.VideoDecoder({
        output: frame => {
          createImageBitmap(frame).then(bitmap => {
            // Get container dimensions (CSS display size)
            const containerWidth = canvas.clientWidth || frame.codedWidth
            const containerHeight = canvas.clientHeight || frame.codedHeight

            // Get video frame actual dimensions
            const frameWidth = frame.codedWidth
            const frameHeight = frame.codedHeight

            // Calculate scaled dimensions using "contain" strategy (完整显示)
            // This ensures the entire video frame is visible within the container
            const frameAspect = frameWidth / frameHeight
            const containerAspect = containerWidth / containerHeight

            let renderWidth, renderHeight
            if (frameAspect > containerAspect) {
              // Video is wider than container, fit to width (letterbox on top/bottom)
              renderWidth = containerWidth
              renderHeight = containerWidth / frameAspect
            } else {
              // Video is taller than container, fit to height (letterbox on sides)
              renderHeight = containerHeight
              renderWidth = containerHeight * frameAspect
            }

            // Ensure render dimensions don't exceed container
            renderWidth = Math.min(renderWidth, containerWidth)
            renderHeight = Math.min(renderHeight, containerHeight)

            // Set canvas pixel size to match display size for sharp rendering
            canvas.width = containerWidth
            canvas.height = containerHeight

            // Clear canvas and draw centered image (黑色背景填充)
            ctx.fillStyle = '#000'
            ctx.fillRect(0, 0, containerWidth, containerHeight)

            // Draw video frame centered, maintaining aspect ratio
            const x = (containerWidth - renderWidth) / 2
            const y = (containerHeight - renderHeight) / 2
            ctx.drawImage(bitmap, x, y, renderWidth, renderHeight)

            frame.close()
            bitmap.close && bitmap.close()
            if (!ready) {
              setLoading(false)
              setShow(true)
              if (onCanvasRef && canvasRef.current) {
                onCanvasRef(canvasRef)
              }
              // handleReady()
              ready = true
            }
          })
        },
        error: (e) => {
          console.error('VideoDecoder error:', e);
          if (e.message?.includes('Unsupported configuration')) {
            console.error('Decoder configuration issue - trying to reset decoder');
          }
        }
      })

      let lastConfiguredCodec = codec;
      let h264Description = null;
      let pendingData = [];
      let decoderConfigured = false;
      let detectedCodecType = null;
      let decoderErrorCount = 0;
      const MAX_DECODER_ERRORS = 3;

      const resetDecoder = () => {
        if (decoderRef.current) {
          try {
            decoderRef.current.close();
          } catch (e) {
            if (e.name !== 'InvalidStateError') {
              console.error('Close decoder on reset error:', e);
            }
          }
        }

        decoderRef.current = new window.VideoDecoder({
          output: frame => {
            createImageBitmap(frame).then(bitmap => {
              const containerWidth = canvas.clientWidth || frame.codedWidth
              const containerHeight = canvas.clientHeight || frame.codedHeight
              const frameWidth = frame.codedWidth
              const frameHeight = frame.codedHeight
              const frameAspect = frameWidth / frameHeight
              const containerAspect = containerWidth / containerHeight

              let renderWidth, renderHeight
              if (frameAspect > containerAspect) {
                renderWidth = containerWidth
                renderHeight = containerWidth / frameAspect
              } else {
                renderHeight = containerHeight
                renderWidth = containerHeight * frameAspect
              }
              renderWidth = Math.min(renderWidth, containerWidth)
              renderHeight = Math.min(renderHeight, containerHeight)

              canvas.width = containerWidth
              canvas.height = containerHeight

              ctx.fillStyle = '#000'
              ctx.fillRect(0, 0, containerWidth, containerHeight)

              const x = (containerWidth - renderWidth) / 2
              const y = (containerHeight - renderHeight) / 2
              ctx.drawImage(bitmap, x, y, renderWidth, renderHeight)

              frame.close()
              bitmap.close && bitmap.close()
              if (!ready) {
                setLoading(false)
                setShow(true)
                if (onCanvasRef && canvasRef.current) {
                  onCanvasRef(canvasRef)
                }
                ready = true
              }
            })
          },
          error: (e) => {
            console.error('VideoDecoder error (recovered):', e);
          }
        });

        decoderConfigured = false;
        detectedCodecRef.current = null;
        detectedCodecType = null;
        h264Description = null;
        pendingData = [];

        console.log('Decoder reset complete, waiting for next key frame to reconfigure');
        return true;
      };

      /**
       * Check if a codec type is supported by the browser
       * @param {string} codecType - 'h264' or 'h265'
       * @returns {boolean} Whether the codec type is supported
       */
      const isCodecTypeSupported = async (codecType) => {
        const codecs = codecType === 'h265' ? [
          { codec: 'hev1.1.6.L93.B0' },
          { codec: 'hvc1.1.6.L93.B0' },
          { codec: 'hev1.1.4.L93.B0' },
          { codec: 'hvc1.1.4.L93.B0' },
        ] : [
          { codec: 'avc1.42E01E' },
          { codec: 'avc1.640028' },
          { codec: 'avc1.4D401E' },
        ];

        for (const config of codecs) {
          try {
            const support = await window.VideoDecoder.isConfigSupported(config);
            if (support.supported) {
              return true;
            }
          } catch (e) {
            console.log(`Check failed for ${codecType}:`, e.message);
          }
        }
        return false;
      }

      /**
       * Configure decoder with detected codec
       * Note: We intentionally do NOT pass `description` for Annex-B streams.
       * When `description` is provided, WebCodecs expects AVCC format (length-prefixed),
       * but our WebSocket sends Annex-B format (start-code prefixed).
       * Omitting `description` lets the decoder handle Annex-B natively.
       *
       * @param {string} detectedCodec - Detected codec string
       * @param {string} detectedCodecType - Detected codec type ('h264' or 'h265')
       * @returns {boolean} Whether configuration succeeded
       */
      const configureDecoderWithData = async (detectedCodec, detectedCodecType) => {
        if (!decoderRef.current) return false;

        console.log(`Configuring decoder with codec: ${detectedCodec}, type: ${detectedCodecType}`);

        const typeSupported = await isCodecTypeSupported(detectedCodecType);
        if (!typeSupported) {
          console.error(`Codec type ${detectedCodecType} is not supported in this browser.`);
          console.error(`Suggestion: Configure your camera to output H.264 video instead of H.265.`);
          setError(t('instant.deviceList.deviceDecodeFailed'));
          message.error(`${t('instant.deviceList.deviceDecodeFailed')} (${detectedCodecType} not supported)`);
          return false;
        }

        const fallbackCodecs = getFallbackCodecs(detectedCodec);
        const codecsToTry = [detectedCodec, ...fallbackCodecs];

        for (const codecToTry of codecsToTry) {
          if (detectedCodecType === 'h265' && codecToTry.startsWith('avc1')) {
            console.log(`Skipping H.264 codec ${codecToTry} for H.265 stream`);
            continue;
          }
          if (detectedCodecType === 'h264' && (codecToTry.startsWith('hev1') || codecToTry.startsWith('hvc1'))) {
            console.log(`Skipping H.265 codec ${codecToTry} for H.264 stream`);
            continue;
          }

          const baseOptions = isEdge() ? [
            { codec: codecToTry },
            { codec: codecToTry, hardwareAcceleration: 'prefer-software' },
            { codec: codecToTry, hardwareAcceleration: 'prefer-hardware' },
          ] : [
            { codec: codecToTry },
            { codec: codecToTry, hardwareAcceleration: 'prefer-hardware' },
            { codec: codecToTry, hardwareAcceleration: 'prefer-software' },
          ];

          for (const config of baseOptions) {
            try {
              if (typeof window.VideoDecoder.isConfigSupported === 'function') {
                const support = await window.VideoDecoder.isConfigSupported(config);
                if (!support.supported) {
                  console.log(`Codec config not supported:`, config);
                  continue;
                }
              }

              decoderRef.current.configure(config);
              console.log('Decoder configured successfully with:', config);
              lastConfiguredCodec = codecToTry;
              detectedCodecRef.current = codecToTry;
              decoderConfigured = true;

              processPendingData();

              return true;
            } catch (e) {
              console.log(`Failed to configure with ${JSON.stringify(config)}:`, e.message);
            }
          }
        }

        console.error(`Failed to configure decoder with any codec. Tried: ${codecsToTry.join(', ')}`);
        return false;
      }

      /**
       * Process buffered data that was received before decoder configuration
       */
      const processPendingData = () => {
        if (pendingData.length === 0 || !decoderRef.current || decoderRef.current.state === 'closed') {
          return;
        }

        console.log(`Processing ${pendingData.length} pending data chunks`);
        
        for (const item of pendingData) {
          try {
            decoderRef.current.decode(new EncodedVideoChunk({
              type: item.isKey ? 'key' : 'delta',
              timestamp: item.timestamp,
              data: item.data
            }));
          } catch (err) {
            console.error('Error processing pending data:', err);
          }
        }
        
        pendingData = [];
      }

      wsRef.current.onmessage = e => {
        if (e.data instanceof ArrayBuffer) {
          const uint8 = new Uint8Array(e.data);
          let currentCodec = detectedCodecRef.current;

          // Detect codec from data if not yet detected
          if (!currentCodec) {
            const detected = detectCodec(uint8);
            if (detected !== 'unknown') {
              console.log('Initial codec detection:', detected);
              detectedCodecType = detected; // Store codec type
              if (detected === 'h264') {
                const spsCodec = getH264CodecString(uint8);
                currentCodec = spsCodec || 'avc1.640028';
                // Extract H.264 SPS/PPS for description
                h264Description = getH264Description(uint8);
                if (h264Description) {
                  console.log(`Extracted H.264 SPS/PPS description (${h264Description.length} bytes)`);
                }
              } else {
                currentCodec = 'hev1.1.6.L93.B0'; // Use hev1 for Annex-B
              }
              detectedCodecRef.current = currentCodec;
              
              configureDecoderWithData(currentCodec, detectedCodecType);
            }
          }

          // Try to update H.264 codec from SPS if we find a better one
          if (currentCodec && currentCodec.startsWith('avc1')) {
             const spsCodec = getH264CodecString(uint8);
             if (spsCodec && spsCodec !== currentCodec) {
                console.log(`Updating H.264 codec from SPS: ${currentCodec} -> ${spsCodec}`);
                currentCodec = spsCodec;
                detectedCodecRef.current = currentCodec;
             }
             // Update description if we don't have one yet
             if (!h264Description) {
               h264Description = getH264Description(uint8);
               if (h264Description) {
                 console.log(`Extracted H.264 SPS/PPS description (${h264Description.length} bytes)`);
                 if (!decoderConfigured && detectedCodecRef.current) {
                   configureDecoderWithData(detectedCodecRef.current, detectedCodecType || 'h264');
                 }
               }
             }
          }

          const useCodec = currentCodec || codec;
          const isKey = isKeyFrame(uint8, useCodec);

          // If decoder is not yet configured, buffer the data
          if (!decoderConfigured) {
            console.log(`Buffering data (${uint8.length} bytes) - decoder not yet configured`);
            pendingData.push({
              data: uint8,
              isKey,
              timestamp: performance.now()
            });
            
            // Limit buffer size to prevent memory issues
            if (pendingData.length > 50) {
              pendingData.shift();
            }
            return;
          }

          // Decoder is configured, decode the data
          try {
            if (!decoderRef.current || decoderRef.current.state === 'closed') {
              console.warn('Decoder is closed, attempting recovery');
              if (isKey && decoderErrorCount < MAX_DECODER_ERRORS) {
                decoderErrorCount++;
                resetDecoder();
              }
              return;
            }
            decoderRef.current.decode(new EncodedVideoChunk({
              type: isKey ? 'key' : 'delta',
              timestamp: performance.now(),
              data: uint8
            }));
            decoderErrorCount = 0;
          } catch (err) {
            console.error('Decode error:', err);
            if (decoderErrorCount < MAX_DECODER_ERRORS) {
              decoderErrorCount++;
              console.log(`Attempting decoder recovery (${decoderErrorCount}/${MAX_DECODER_ERRORS})`);
              resetDecoder();
            } else {
              setError(t('instant.deviceList.deviceDecodeFailed'));
            }
          }
        }
      }
    }
    init()
    return () => {
      if (wsRef.current) {
        try {
          wsRef.current.close && wsRef.current.close(1000, 'close_by_user');
        } catch (e) {
          console.error('Close WebSocket exception:', e);
        }
        wsRef.current = null;
      }
      if (decoderRef.current) {
        try {
          decoderRef.current.close && decoderRef.current.close();
        } catch (e) {
          if (e.name !== 'InvalidStateError') {
            console.error('Close VideoDecoder exception:', e);
          }
        }
        decoderRef.current = null;
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codec, isSupported, cameraId, channel, onCanvasRef, t])

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', ...style }}>
      {loading && (
        <div style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          zIndex: 10
        }}>
          <Spin size="large" />
        </div>
      )}
      {error && (
        <div style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          zIndex: 10,
          color: '#ff4d4f',
          textAlign: 'center'
        }}>
          {error}
        </div>
      )}
      <canvas
        ref={canvasRef}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'contain',
          background: '#000',
          display: show ? 'block' : 'none'
        }}
      />
      {!show && !loading && !error && (
        <img
          src={poster || DefaultCameraBg}
          alt="Camera"
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover'
          }}
        />
      )}
    </div>
  )
}

export default VideoPlayer