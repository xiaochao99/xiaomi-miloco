/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState } from 'react';
import { Button, Switch, Empty, Popconfirm, Pagination, Modal } from 'antd';
import { useTranslation } from 'react-i18next';
import { EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { Card, ListItem, RuleForm } from '@/components';
import { classNames } from '@/utils/util';
import styles from '../index.module.less';

/**
 * RuleManagement Component - Rule management component
 * 规则管理组件
 *
 * @returns {JSX.Element} RuleManagement component
 */
const RuleManagement = ({
  rules = [],
  onEdit,
  onDelete,
  onToggle,
  loading = false,
  cameraOptions = [],
  actionOptions = [],
  enableCameraRefresh = false,
  onRefreshCameras,
  enableActionRefresh = false,
  onRefreshActions,
  cameraLoading = false,
  actionLoading = false,
}) => {
  const { t } = useTranslation();
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingRule, setEditingRule] = useState(null);

  const handleEdit = (rule) => {
    setEditingRule(rule);
    setEditModalOpen(true);
  };

  const handleEditSubmit = async (formData) => {
    await onEdit(editingRule, formData);
    handleModalClose();
  };

  const handleModalClose = () => {
    setEditModalOpen(false);
    setEditingRule(null);
  };

  const getCustomInfo = (rule) => {
    const text = []
    const cameras = rule?.cameras || [];
    if (cameras.length > 0) {
      const cameraNames = cameras.map(camera => {
        if (typeof camera === 'object') {
          return `${camera.name}(${camera.room_name || ''})`;
        }
        return camera;
      });
      text.push(`${t('smartCenter.cameras')}: ${cameraNames.join(', ') || t('smartCenter.noCameras')}`);
    }

    if (rule.condition) {
      text.push(`${t('smartCenter.triggerCondition')}: ${rule.condition}`);
    }

    const executeInfo = rule.execute_info || {};
    const executeType = executeInfo.ai_recommend_execute_type;
    const allActions = [];

    if (executeType === 'static') {
      const aiRecommendActions = executeInfo.ai_recommend_actions || [];
      if (aiRecommendActions.length > 0) {
        const aiActions = aiRecommendActions.map(action => {
          if (action.introduction) {
            return `${action.introduction}(${t('smartCenter.deviceControl')})`;
          }
          return '';
        }).filter(Boolean);
        allActions.push(...aiActions);
      }
    } else if (executeType === 'dynamic') {
      const aiRecommendDescriptions = executeInfo.ai_recommend_action_descriptions || [];
      if (aiRecommendDescriptions.length > 0) {
        const aiDescriptions = aiRecommendDescriptions.map(desc => {
          return `${desc}(${t('smartCenter.deviceControl')})`;
        });
        allActions.push(...aiDescriptions);
      }
    }

    const automationActions = executeInfo.automation_actions || rule.actions || [];
    if (automationActions.length > 0) {
      const manualActions = automationActions.map(action => {
        if (action.mcp_client_id === 'miot_manual_scenes') {
          return `${action.introduction}(${t('smartCenter.miHomeAutomationExecution')})`;
        } else if (action.mcp_client_id === 'ha_automations') {
          return `${action.introduction}(${t('smartCenter.haAutomationExecution')})`;
        }
        return '';
      }).filter(Boolean);
      allActions.push(...manualActions);
    }

    if (allActions.length > 0) {
      text.push(`${t('smartCenter.executionAction')}: ${allActions.join('; ') || t('smartCenter.noAction')}`);
    }

    const notify = executeInfo.notify || rule.notify;
    if (notify?.content) {
      text.push(`${t('smartCenter.miHomeNotification')}: ${notify.content}`);
    }
    return (
      <div className={styles.customInfo}>
        {text.map((item, index) => (
          <div key={index} className={styles.customInfoItem}>{item}</div>
        ))}
      </div>
    )
  }

  return (
    <div className={classNames(styles.gridContainer, styles.columns2)}>
      {rules?.map?.((rule, index) => {
        return (
          <Card
            key={index}
          >
            <ListItem
              title={rule.name}
              // description={rule.condition}
              // meta={getMeta(rule)}
              customInfo={getCustomInfo(rule)}
              showSwitch={true}
              switchValue={rule.enabled}
              onSwitchChange={checked => onToggle(rule, checked)}
              showEdit={true}
              showDelete={true}
              onEdit={() => handleEdit(rule)}
              onDelete={() => onDelete(rule)}
            />
          </Card>
        )
      }
      )
      }

      <Modal
        open={editModalOpen}
        title={t('smartCenter.editRule')}
        onCancel={handleModalClose}
        footer={null}
        destroyOnClose
        width={600}
      >
        {editingRule && (
          <RuleForm
            mode="edit"
            initialRule={editingRule}
            onSubmit={handleEditSubmit}
            onCancel={handleModalClose}
            loading={loading}
            cameraOptions={cameraOptions}
            actionOptions={actionOptions}
            enableCameraRefresh={enableCameraRefresh}
            onRefreshCameras={onRefreshCameras}
            enableActionRefresh={enableActionRefresh}
            onRefreshActions={onRefreshActions}
            cameraLoading={cameraLoading}
            actionLoading={actionLoading}
          />
        )}
      </Modal>
    </div>
  );
};

export default RuleManagement;
