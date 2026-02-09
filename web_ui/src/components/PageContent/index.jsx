/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useMemo } from 'react';
import { Loading, EmptyContent } from '..';
import styles from './index.module.less';

/**
 * PageContent Component - Page layout wrapper with optional header and content area
 * 页面内容组件 - 带有可选头部和内容区域的页面布局包装器
 *
 * @param {Object} props - Component props
 * @param {React.ReactNode} [props.Header=null] - Header component to render
 * @param {boolean} [props.loading=false] - Whether the page is loading
 * @param {React.ReactNode} [props.emptyContent=null] - Empty content component to render
 * @param {React.ReactNode} props.children - Main content to render
 * @returns {JSX.Element} Page content component
 */
const PageContent = ({Header = null, loading = false, showEmptyContent = false, emptyContentProps = {}, children }) => {

  const Content = useMemo(() => {
    if (loading) {
      return <Loading size="default" />;
    } else if (showEmptyContent) {
      return <EmptyContent {...emptyContentProps} />;
    } else {
      return children;
    }
  }, [loading, showEmptyContent, emptyContentProps, children]);

  return (
    <div className={styles.wrap}>
      <div className={styles.content}>
        {Header && (
          <div className={styles.headerContainer}>
            {Header}
          </div>
        )}

        <div className={styles.contentContainer}>
          {Content}
        </div>
      </div>
    </div>
  );
}


export default PageContent;

