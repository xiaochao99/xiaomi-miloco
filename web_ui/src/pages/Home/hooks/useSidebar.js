/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useState } from 'react';
import { SIDEBAR_WIDTH } from '@/constants/homeConfigTypes';

/**
 * Sidebar related custom hook
 * Handle sidebar expand/collapse, drag adjustment functions
 * @returns {Object} Sidebar related status and methods
 */
export const useSidebar = () => {
  const { EXPANDED, COLLAPSED, MIN, MAX } = SIDEBAR_WIDTH;
  const [siderWidth, setSiderWidth] = useState(SIDEBAR_WIDTH.EXPANDED);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStartWidth, setDragStartWidth] = useState(SIDEBAR_WIDTH.EXPANDED);
  const [dragDirection, setDragDirection] = useState(null);

  const isCollapsed = siderWidth < 80;

  const expandSidebar = () => {
    setSiderWidth(SIDEBAR_WIDTH.EXPANDED);
  };

  const collapseSidebar = () => {
    setSiderWidth(SIDEBAR_WIDTH.COLLAPSED);
  };

  const toggleSidebar = () => {
    if (isCollapsed) {
      expandSidebar();
    } else {
      collapseSidebar();
    }
  };

  const handleResizeStart = () => {
    setIsDragging(true);
    setDragStartWidth(siderWidth);
    setDragDirection(null);
  };

  /**
   * Drag process handling
   * @param {Array} size drag after size array
   */
  const handleResize = (size) => {
    const newWidth = size[0];

    // detect drag direction
    if (isDragging && dragDirection === null) {
      const newDirection = newWidth > dragStartWidth ? 'right' : 'left';
      setDragDirection(newDirection);
    }

    setSiderWidth(newWidth);
  };

  /**
   * Drag end process handling
   * Automatically locate to maximum or minimum value according to drag direction
   */
  const handleResizeEnd = () => {
    if (dragDirection === 'right') {
      setSiderWidth(SIDEBAR_WIDTH.EXPANDED);
    } else if (dragDirection === 'left') {
      setSiderWidth(SIDEBAR_WIDTH.COLLAPSED);
    }

    // reset drag state
    setIsDragging(false);
    setDragDirection(null);
    setDragStartWidth(SIDEBAR_WIDTH.EXPANDED);
  };

  return {
    siderWidth,
    isCollapsed,
    isDragging,
    expandSidebar,
    collapseSidebar,
    toggleSidebar,
    handleResizeStart,
    handleResize,
    handleResizeEnd,
    SIDEBAR_WIDTH,
  };
};
