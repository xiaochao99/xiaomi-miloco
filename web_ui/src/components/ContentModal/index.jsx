/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from "react"
import BgPhoto from '@/assets/images/login-bg.png'
import styles from "./index.module.less"

/**
 * ContentModal Component - A modal container with background image and content overlay
 * 内容模态框组件 - 带有背景图片和内容覆盖层的模态框容器
 *
 * @param {Object} props - Component props
 * @param {React.ReactNode} props.children - Content to be rendered inside the modal
 * @returns {JSX.Element} Modal component with background image and content area
 */
const ContentModal = ({
  children,
}) => {
  return (
    <div className={styles['container']}>
      <img className={styles['bg-photo']} src={BgPhoto} alt="" />
      <div className={styles['content']}>
        {children}
      </div>
    </div>
  )
}


export default ContentModal
