/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react'
import styles from './index.module.less'

/**
 * Card Component - A reusable card container with optional title and content
 * 卡片组件 - 一个可复用的卡片容器，包含可选的标题和内容
 *
 * @param {Object} props - Component props
 * @param {string} [props.className] - Additional CSS class for the card container
 * @param {string} [props.contentClassName] - Additional CSS class for the card content area
 * @param {string} [props.title=''] - Optional title text displayed in the card header
 * @param {React.ReactNode} props.children - Content to be rendered inside the card
 * @returns {JSX.Element} Card component with optional header and content
 */
const Card = ({ className,contentClassName, title = '', children }) => {
  return (
    <div className={`${styles.card} ${className}`}>
      {
        title && (
          <div className={styles.cardHeader}>
            <div className={styles.cardTitle}>{title}</div>
          </div>
        )
      }

      <div className={`${styles.cardContent} ${contentClassName}`}>
        {children}
      </div>
    </div>
  )
}

export default Card
