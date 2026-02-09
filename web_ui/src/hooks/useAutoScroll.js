/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useRef, useCallback, useEffect, useState } from 'react';

/**
 * useAutoScroll Hook - Auto scroll management for chat interface
 * 自动滚动管理 Hook - 用于管理聊天界面的自动滚动逻辑
 *
 * @param {Object} options - Configuration options
 * @param {boolean} options.isAnswering - Whether currently answering
 * @param {boolean} options.isScrollToBottom - Whether should scroll to bottom
 * @param {Function} options.setIsScrollToBottom - Function to set scroll state
 * @param {number} options.scrollInterval - Scroll interval time in milliseconds
 * @param {number} options.scrollThreshold - Scroll threshold in pixels
 * @param {number} options.debounceDelay - Debounce delay time in milliseconds
 * @returns {Object} Scroll-related state and methods
 */
export const useAutoScroll = ({
  isAnswering,
  setIsScrollToBottom,
  messages = [],
  scrollInterval = 200,
  scrollThreshold = 30,
  debounceDelay = 50
}) => {
  // reference
  const messagesRef = useRef(null);
  const autoScrollTimerRef = useRef(null);
  const scrollDebounceRef = useRef(null);
  const prevIsAnsweringRef = useRef(isAnswering);
  const prevIsAtBottomRef = useRef(true);

  // state
  const [isNewAnswering, setIsNewAnswering] = useState(false);
  const [userScrolled, setUserScrolled] = useState(false);

  // check if at bottom
  const isAtBottom = useCallback(() => {
    if (!messagesRef.current) {return true;}
    const { scrollTop, scrollHeight, clientHeight } = messagesRef.current;
    return scrollTop + clientHeight >= scrollHeight - scrollThreshold;
  }, [scrollThreshold]);

  // scroll to bottom
  const scrollToBottom = useCallback((behavior = 'smooth') => {
    if (messagesRef.current) {
      messagesRef.current.scrollTo({
        top: messagesRef.current.scrollHeight,
        behavior
      });
    }
  }, []);

  // start auto scroll
  const startAutoScroll = useCallback(() => {
    if (autoScrollTimerRef.current) { return; }

    autoScrollTimerRef.current = setInterval(() => {
      scrollToBottom();
    }, scrollInterval);
  }, [scrollInterval, scrollToBottom]);

  // stop auto scroll
  const stopAutoScroll = useCallback(() => {
    if (autoScrollTimerRef.current) {
      clearInterval(autoScrollTimerRef.current);
      autoScrollTimerRef.current = null;
    }
  }, []);

  // clear auto scroll and scroll to bottom
  const clearAutoScroll = useCallback(() => {
    stopAutoScroll();
    scrollToBottom('auto');
  }, [stopAutoScroll, scrollToBottom]);

  // force start auto scroll (for new message sending)
  const forceStartAutoScroll = useCallback(() => {
    setUserScrolled(false);
    setIsScrollToBottom(true);
    scrollToBottom('auto');
    setTimeout(() => {
      startAutoScroll();
    }, 100);
  }, [setUserScrolled, setIsScrollToBottom, scrollToBottom, startAutoScroll]);

  // handle scroll event (with debounce)
  const handleScroll = useCallback(() => {
    const isAtBot = isAtBottom();
    if (!isAtBot && autoScrollTimerRef.current && isAnswering) {
      stopAutoScroll();
    }

    if (scrollDebounceRef.current) {
      clearTimeout(scrollDebounceRef.current);
    }

    scrollDebounceRef.current = setTimeout(() => {
      const prevIsAtBot = prevIsAtBottomRef.current;
      setIsScrollToBottom(isAtBot);

      if (isAtBot !== prevIsAtBot) {
        prevIsAtBottomRef.current = isAtBot;

        if (!isAtBot && !userScrolled) {
          // user scroll left bottom
          setUserScrolled(true);
        } else if (isAtBot && userScrolled) {
          // user scroll back to bottom
          setUserScrolled(false);
          // if is answering, immediately start auto scroll
          if (isAnswering && !autoScrollTimerRef.current) {
            startAutoScroll();
          }
        }
      }
    }, debounceDelay);
  }, [isAtBottom, userScrolled, setIsScrollToBottom, debounceDelay, stopAutoScroll, isAnswering, startAutoScroll]);

  // new answer start
  useEffect(() => {
    if (!prevIsAnsweringRef.current && isAnswering) {

      setIsNewAnswering(true);
      setUserScrolled(false); // reset user scroll state
    } else if (prevIsAnsweringRef.current && !isAnswering) {
      // answer end
      setIsNewAnswering(false);
    }
    prevIsAnsweringRef.current = isAnswering;
  }, [isAnswering]);

  // auto scroll logic
  useEffect(() => {
    // simplify start condition: just in answering and no user scroll and no auto scroll
    const shouldAutoScroll = isAnswering && !userScrolled && !autoScrollTimerRef.current;
    const shouldStopAutoScroll = autoScrollTimerRef.current && (userScrolled || !isAnswering);

    console.log('auto scroll logic check:', {
      isAnswering,
      userScrolled,
      hasTimer: !!autoScrollTimerRef.current,
      shouldAutoScroll,
      shouldStopAutoScroll
    });

    if (shouldAutoScroll) {
      console.log('start auto scroll');
      startAutoScroll();
    }

    if (shouldStopAutoScroll) {
      console.log('stop auto scroll');
      stopAutoScroll();
    }
  }, [isAnswering, userScrolled, startAutoScroll, stopAutoScroll]);

  // listen message change, trigger auto scroll when streaming
  useEffect(() => {
    if (isAnswering && !userScrolled && messages.length > 0) {
      // if is answering and no user scroll, ensure auto scroll is running
      if (!autoScrollTimerRef.current) {
        startAutoScroll();
      } else {
        // if already auto scroll, immediately scroll to bottom (handle streaming message)
        scrollToBottom('auto');
      }
    }
  }, [messages, isAnswering, userScrolled, startAutoScroll, scrollToBottom]);

  // component unmount, clean up
  useEffect(() => {
    return () => {
      if (autoScrollTimerRef.current) {
        clearInterval(autoScrollTimerRef.current);
      }
      if (scrollDebounceRef.current) {
        clearTimeout(scrollDebounceRef.current);
      }
    };
  }, []);

  return {
    messagesRef,

    isNewAnswering,
    userScrolled,

    scrollToBottom,
    startAutoScroll,
    stopAutoScroll,
    clearAutoScroll,
    forceStartAutoScroll,
    handleScroll,
    isAtBottom
  };
};
