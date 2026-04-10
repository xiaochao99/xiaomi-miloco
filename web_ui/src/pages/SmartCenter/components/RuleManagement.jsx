/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState } from 'react';
import { Button, Switch, Empty, Popconfirm, Pagination, Modal, Tag } from 'antd';
import { useTranslation } from 'react-i18next';
import { EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { Card, ListItem, RuleForm } from '@/components';
import { classNames } from '@/utils/util';
import { useChatStore } from '@/stores/chatStore';
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
  const { haEntityNameMap, fetchHaEntityNameMap } = useChatStore();
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingRule, setEditingRule] = useState(null);

  React.useEffect(() => {
    fetchHaEntityNameMap?.();
  }, [fetchHaEntityNameMap]);

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

  const getConditionTypeLabel = (type) => {
    switch (type) {
      case 'direct':
        return t('smartCenter.directMode');
      case 'hybrid':
        return t('smartCenter.hybridMode');
      case 'detection':
        return t('detection.mode') || '目标检测';
      case 'face_recognition':
        return t('smartCenter.faceRecognitionMode') || '人脸识别';
      case 'llm':
      default:
        return t('smartCenter.llmMode');
    }
  };

  const getCustomInfo = (rule) => {
    const text = [];
    const conditionType = rule?.condition_type || 'llm';
    text.push(
      `${t('smartCenter.conditionType')}: ${getConditionTypeLabel(conditionType)}`
    );

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

    const haDevices = rule?.ha_devices || [];
    if (haDevices.length > 0) {
      const ids = haDevices.map(d => typeof d === 'object' ? d.did : d);
      text.push(`${t('smartCenter.haDevices')}: ${ids.join(', ')}`);
    }

    if (conditionType === 'direct' || conditionType === 'hybrid') {
      if (rule.trigger_entity_id) {
        const friendly = haEntityNameMap?.[rule.trigger_entity_id];
        text.push(`${t('smartCenter.triggerEntity')}: ${friendly ? `${friendly}（${rule.trigger_entity_id}）` : rule.trigger_entity_id}`);
      }
      if (rule.ha_condition) {
        text.push(`${t('smartCenter.haCondition')}: ${rule.ha_condition}`);
      }
      if (conditionType === 'hybrid' && rule.condition) {
        text.push(`${t('smartCenter.cameraCondition')}: ${rule.condition}`);
      }
    } else {
      if (rule.condition) {
        text.push(`${t('smartCenter.triggerCondition')}: ${rule.condition}`);
      }
    }

    const executeInfo = rule.execute_info || {};
    const executeType = executeInfo.ai_recommend_execute_type;
    const allActions = [];
    let mcpActionCount = 0;
    let automationActionCount = 0;
    let notifyCount = 0;

    if (executeType === 'static') {
      const aiRecommendActions = executeInfo.ai_recommend_actions || [];
      if (aiRecommendActions.length > 0) {
        mcpActionCount += aiRecommendActions.length;
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
        mcpActionCount += aiRecommendDescriptions.length;
        const aiDescriptions = aiRecommendDescriptions.map(desc => {
          return `${desc}(${t('smartCenter.deviceControl')})`;
        });
        allActions.push(...aiDescriptions);
      }
    }

    const automationActions = executeInfo.automation_actions || rule.actions || [];
    if (automationActions.length > 0) {
      automationActionCount += automationActions.length;
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

    const notify = executeInfo.notify || rule.notify;
    if (notify?.content) {
      notifyCount += 1;
    }

    if (mcpActionCount || automationActionCount || notifyCount) {
      const summary = [];
      if (mcpActionCount) summary.push(`${t('smartCenter.deviceControl')}: ${mcpActionCount}`);
      if (automationActionCount) summary.push(`${t('smartCenter.automationScene')}: ${automationActionCount}`);
      if (notifyCount) summary.push(`${t('smartCenter.miHomeNotification')}: ${notifyCount}`);
      text.push(`${t('smartCenter.executionAction')}: ${summary.join('；')}`);
    }

    if (allActions.length > 0) {
      const preview = allActions.slice(0, 2).join('；');
      const more = allActions.length > 2 ? `…(+${allActions.length - 2})` : '';
      text.push(`${t('smartCenter.executionPreview') || '动作预览'}: ${preview}${more}`);
    }

    if (notify?.content) {
      const content = String(notify.content);
      const short = content.length > 30 ? `${content.slice(0, 30)}…` : content;
      text.push(`${t('smartCenter.miHomeNotification')}: ${short}`);
    }
    return (
      <div className={styles.customInfo}>
        <div style={{ marginBottom: 8 }}>
          <Tag color={rule.enabled ? 'green' : 'default'}>
            {rule.enabled ? t('common.enabled') : t('common.disabled')}
          </Tag>
          <Tag>{getConditionTypeLabel(conditionType)}</Tag>
        </div>
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
