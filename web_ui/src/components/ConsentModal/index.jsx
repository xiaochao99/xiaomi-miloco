/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState } from 'react';
import { Modal, Button, Checkbox } from 'antd';
import styles from './index.module.less';
import { useSettingStore } from '@/stores/settingStore';

/**
 * Consent Modal Component - Modal for consent agreement
 * @param {Object} props - Component props
 * @param {boolean} props.visible - Whether to show the modal
 * @param {Function} props.onAgree - Agree callback
 * @param {Function} props.onExit - Exit callback
 * @param {Function} props.t - Translation function
 */
const ConsentModal = ({ visible, onAgree, onExit, t }) => {
  const [agreed, setAgreed] = useState(false);
  const language = useSettingStore().getLanguage();
  console.log('language:', language);

  const handleAgree = () => {
    if (agreed) {
      onAgree();
    }
  };

  const handleExit = () => {
    onExit();
  };

  const handleCheckboxChange = (e) => {
    setAgreed(e.target.checked);
  };

  return (
    <Modal
      title={<div className={styles.title}>{t('consent.title')}</div>}
      centered
      open={visible}
      closable={false}
      maskClosable={false}
      footer={null}
      width={700}
      className={styles.consentModal}
    >
      <div className={styles.content}>
        <div className={styles.welcomeText}>
          {t('consent.welcomeMessage')}
        </div>

        <div className={styles.consentSection}>
          <Checkbox
            checked={agreed}
            onChange={handleCheckboxChange}
            className={styles.consentCheckbox}
          >
            <span className={styles.consentText}>
              {t('consent.consentText')}
              <a
                href={language === 'zh' ? 'https://cdn.cnbj1.fds.api.mi-img.com/xiaomi-miloco/protocol/userAgreement-zh.html' : 'https://cdn.cnbj1.fds.api.mi-img.com/xiaomi-miloco/protocol/userAgreement-en.html'}
                target="_blank"
                className={styles.link}
              >
                {t('consent.userAgreement')}
              </a>
              、
              <a
                href={language === 'zh' ? 'https://privacy.mi.com/XiaomiMiloco/zh_CN/' : 'https://privacy.mi.com/XiaomiMiloco/en_GB/'}
                target="_blank"
                className={styles.link}
              >
                {t('consent.privacyPolicy')}
              </a>
            </span>
          </Checkbox>
        </div>

        <div className={styles.buttonGroup}>
          <Button
            onClick={handleExit}
            className={styles.exitButton}
          >
            {t('consent.exit')}
          </Button>
          <Button
            type="primary"
            onClick={handleAgree}
            disabled={!agreed}
            className={styles.agreeButton}
          >
            {t('consent.agree')}
          </Button>
        </div>
      </div>
    </Modal>
  );
};

export default ConsentModal;
