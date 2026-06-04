/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal, Button, Typography, Checkbox } from 'antd';
import ReactMarkdown from 'react-markdown';
import { LoadingScreen, ErrorRetry, ConsentModal, AuthCodeModal } from '@/components';
import { useAuth, useLayout } from './hooks/index';
import { Layout } from './components';

const { Text } = Typography;

/**
 * Home Page - Main application layout with authentication and navigation
 * 首页 - 包含身份验证和导航的主应用布局页面
 *
 * @returns {JSX.Element} Home page component with layout or loading/error states
 */
const Home = () => {
  const { t } = useTranslation();
  const {
    userInfo,
    loading,
    needRetryAuth,
    showConsentModal,
    showAuthCodeModal,
    retryAuth,
    logout,
    handleConsentAgree,
    handleConsentExit,
    handleAuthCodeSubmit,
    handleAuthCodeCancel,
    loginUrl,
    showUpdateNotify,
    updateNotifyData,
    closeUpdateNotify,
    handleApplyUpdate,
  } = useAuth(t)

  const {
    selectedMenuKey,
  } = useLayout()

  const [updateConfigChecked, setUpdateConfigChecked] = useState(false);

  if (loading && !showConsentModal && !showAuthCodeModal) {
    return (
      <LoadingScreen
        title="common.loading"
        size="default"
        loginUrl={loginUrl}
      />
    )
  }

  if (needRetryAuth) {
    return (
      <ErrorRetry
        title="error.authFailed"
        message="error.authFailedMessage"
        onRetry={retryAuth}
        loading={loading}
      />
    )
  }

  if (showConsentModal) {
    return (
      <ConsentModal
        visible={showConsentModal}
        onAgree={handleConsentAgree}
        onExit={handleConsentExit}
        t={t}
      />
    )
  }

  if (showAuthCodeModal) {
    return (
      <AuthCodeModal
        visible={showAuthCodeModal}
        onSubmit={handleAuthCodeSubmit}
        onCancel={handleAuthCodeCancel}
        t={t}
      />
    )
  }

  return (
    <>
      <Layout
        selectedMenuKeys={[selectedMenuKey]}
        userInfo={userInfo}
        onLogout={logout}
      />
      {/* Update Notification Modal - shown after login */}
      <Modal
        title={t('setting.updateContent')}
        open={showUpdateNotify}
        onCancel={closeUpdateNotify}
        footer={[
          <Button key="close" onClick={closeUpdateNotify}>
            {t('setting.updateLater')}
          </Button>,
          <Button
            key="update"
            type="primary"
            onClick={() => handleApplyUpdate(updateConfigChecked)}
          >
            {t('setting.updateNow')}
          </Button>
        ]}
        width={640}
      >
        {updateNotifyData && (
          <div>
            <div style={{ marginBottom: 16 }}>
              <Text strong>
                {t('setting.updateNewVersion', { version: updateNotifyData.latest_version })}
              </Text>
              <br />
              <Text type="secondary">
                {t('setting.updateNewVersionDesc', {
                  current: updateNotifyData.current_version,
                  latest: updateNotifyData.latest_version
                })}
              </Text>
            </div>
            {updateNotifyData.has_config && (
              <div style={{ marginBottom: 12 }}>
                <Checkbox
                  checked={updateConfigChecked}
                  onChange={(e) => setUpdateConfigChecked(e.target.checked)}
                >
                  {t('setting.updateConfigCheckbox')}
                </Checkbox>
              </div>
            )}
            <div style={{
              background: '#f6f8fa',
              border: '1px solid #e1e4e8',
              borderRadius: 6,
              padding: 16,
              maxHeight: 400,
              overflow: 'auto',
              fontSize: 14,
              lineHeight: 1.6
            }}>
              {updateNotifyData.release_body ? (
                <ReactMarkdown>{updateNotifyData.release_body}</ReactMarkdown>
              ) : (
                '-'
              )}
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}

export default Home
