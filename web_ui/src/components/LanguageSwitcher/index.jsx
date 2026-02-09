/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { Select, message } from 'antd';
import { GlobalOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useSettingStore } from '@/stores/settingStore';
import styles from './index.module.less';

const { Option } = Select;

/**
 * LanguageSwitcher Component - Language selection dropdown with flag icons
 * 语言切换器组件 - 带有国旗图标的下拉语言选择器
 *
 * @param {Object} props - Component props
 * @param {string} [props.size='default'] - Select component size
 * @param {boolean} [props.showIcon=true] - Whether to show global icon
 * @param {boolean} [props.showLabel=false] - Whether to show language label
 * @param {string} [props.className=''] - Additional CSS class
 * @returns {JSX.Element} Language switcher component
 */
const LanguageSwitcher = ({
  size = 'default',
  showIcon = true,
  showLabel = false,
  className = ''
}) => {
  const { i18n, t } = useTranslation();
  const { setLanguage: setStoreLanguage } = useSettingStore();

  // language options
  const languageOptions = [
    { key: 'zh', label: '简体中文' },
    { key: 'en', label: 'English' },
  ];

  // handle language change
  const handleLanguageChange = (value) => {
    // use settingStore to manage language setting
    setStoreLanguage(value);
    i18n.changeLanguage(value);

    const languageName = languageOptions.find(opt => opt.key === value)?.label;
    message.success(`${t('setting.languageChanged')} ${languageName}`);
  };

  // get current language
  const currentLanguage = i18n?.language || 'zh';

  return (
    <div className={styles.languageSwitcherContainer}>
      <div className={`${styles.languageSwitcher} ${className}`}>
        {showLabel && (
          <span className={styles.label}>
            {showIcon && <GlobalOutlined />}
            {t('common.language')}:
          </span>
        )}
        <Select
          value={currentLanguage}
          onChange={handleLanguageChange}
          size={size}
          className={styles.select}
          suffixIcon={showIcon ? <GlobalOutlined /> : null}
        >
          {languageOptions.map(option => (
            <Option key={option.key} value={option.key}>
              <span className={styles.option}>
                <span className={styles.label}>{option.label}</span>
              </span>
            </Option>
          ))}
        </Select>
      </div>
    </div>

  );
};

export default LanguageSwitcher;
