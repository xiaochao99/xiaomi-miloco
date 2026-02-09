/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal } from 'antd';
import { Header, PageContent, RuleForm } from '@/components';
import { useRuleFormUpdates } from '@/hooks/useRuleFormUpdates';
import { useRuleFormOptions } from '@/hooks/useRuleFormOptions';
import EmptyRule from '@/assets/images/empty-rule.png';
import { RuleManagement } from './components';

/**
 * SmartCenter Page - Smart automation rule management page for creating and managing trigger rules
 * 智能中心页面 - 用于创建和管理触发规则的智能自动化规则管理页面
 *
 * @returns {JSX.Element} Smart center page component
 */
const SmartCenter = () => {
  const { t } = useTranslation();
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const { loading, rules, pageLoading, setPageLoading, fetchRules, handleSaveRule, handleUpdateRule, handleDeleteRule, handleToggleRule } = useRuleFormUpdates();

  const {
    cameraOptions,
    actionOptions,
    cameraLoading,
    actionLoading,
    refreshCameras,
    refreshActions,
  } = useRuleFormOptions();

  useEffect(() => {
    const initData = async () => {
      setPageLoading(true);
      await fetchRules();
      setPageLoading(false);
    }
    initData();
  }, []);

  return (
    <>
      <PageContent
        Header={(
          <Header
            title={t('home.menu.triggerRule')}
            buttonText={t('smartCenter.addRule')}
            buttonHandleCallback={() => setCreateModalVisible(true)}
          />
        )}
        loading={pageLoading}
        showEmptyContent={!pageLoading && rules.length === 0}
        emptyContentProps={{
          description: t('smartCenter.noRules'),
          imageStyle: { width: 72, height: 72 },
          image: EmptyRule,
        }}
      >

        <RuleManagement
          rules={rules}
          onEdit={handleUpdateRule}
          onDelete={handleDeleteRule}
          onToggle={handleToggleRule}
          loading={loading}
          cameraOptions={cameraOptions}
          actionOptions={actionOptions}
          enableCameraRefresh={true}
          onRefreshCameras={refreshCameras}
          enableActionRefresh={true}
          onRefreshActions={refreshActions}
          cameraLoading={cameraLoading}
          actionLoading={actionLoading}
        />

      </PageContent>

      <Modal
        title={t('smartCenter.createRule')}
        open={createModalVisible}
        onCancel={() => setCreateModalVisible(false)}
        footer={null}
        destroyOnClose
        width={600}
      >
        <RuleForm
          mode="create"
          onSubmit={async (formData) => {
            const result = await handleSaveRule(formData);
            if (result) {
              setCreateModalVisible(false);
            }
          }}
          loading={loading}
          cameraOptions={cameraOptions}
          actionOptions={actionOptions}
          enableCameraRefresh={true}
          onRefreshCameras={refreshCameras}
          enableActionRefresh={true}
          onRefreshActions={refreshActions}
          cameraLoading={cameraLoading}
          actionLoading={actionLoading}
        />
      </Modal>
    </>

  );
};

export default SmartCenter;
