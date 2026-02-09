/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { Button } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import Icon from '@/components/Icon';
import styles from './index.module.less';

/**
 * Header Component - Page header with title, action button and optional right content
 * 头部组件 - 带有标题、操作按钮和可选右侧内容的页面头部
 *
 * @param {Object} props - Component props
 * @param {string} props.title - Header title text
 * @param {string} [props.buttonText=''] - Action button text
 * @param {Function} [props.buttonHandleCallback=() => {}] - Action button click callback
 * @param {React.ReactNode} [props.rightContent=null] - Custom right side content
 * @returns {JSX.Element} Header component
 */
const Header = ({ title, buttonText = '', buttonHandleCallback = () => { }, rightContent = null }) => {
  return (
    <div className={styles.header}>
      <div className={styles.title}>{title}</div>
      {buttonText && <Button
        type="primary"
        icon={<Icon name="add" size={14} style={{ color: 'white' }} />}
        onClick={() => { buttonHandleCallback() }}
      >
        {buttonText}
      </Button>
      }
      {
        rightContent && rightContent
      }
    </div>
  )
};

export default Header;
