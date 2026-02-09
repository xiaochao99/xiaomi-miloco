/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useTranslation } from 'react-i18next';
import { Header, PageContent } from '@/components';
import RuleRecord from './components/RuleRecord';
import styles from './index.module.less';

/**
 * LogManage Page - Log management page for viewing rule execution logs and records
 * 日志管理页面 - 用于查看规则执行日志和记录的页面
 *
 * @returns {JSX.Element} Log management page component
 */
const LogManage = () => {
  const { t } = useTranslation();

  return (
    <PageContent
      Header={(
        <Header
          title={t('home.menu.logManage')}
        />
      )}
    >
      <RuleRecord />
    </PageContent>
  );
}

export default LogManage;
