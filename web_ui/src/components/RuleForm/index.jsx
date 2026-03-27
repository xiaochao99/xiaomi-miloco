/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState, useEffect } from 'react';
import { Select, Input, Button, Checkbox, Form, Tooltip, Spin, message, Switch } from 'antd';
const { Option } = Select;
import { QuestionCircleOutlined, ReloadOutlined, UpOutlined, DownOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { refreshHaAutomation } from '@/api';
import TimeSelector from '@/components/TimeSelector';
import DetectionConditionForm from '@/components/DetectionConditionForm';
import {
  TRIGGER_PERIOD_OPTIONS,
  TRIGGER_INTERVAL_OPTIONS,
  formDataUtils,
} from '@/utils/ruleFormUtils';
import { useRuleFormData, convertFormDataToBackend } from '@/hooks/useRuleFormData';
import { useRuleFormActions } from '@/hooks/useRuleFormActions';
import { useLogViewerStore } from '@/stores/logViewerStore';
import styles from './index.module.less';
import { classNames } from '@/utils';
import { useChatStore } from '@/stores/chatStore';
import SelectTagRender from './selectTagRender';

/**
 * RuleForm Component - Unified form component for creating and editing smart automation rules
 * 规则表单组件 - 用于创建和编辑智能自动化规则的统一表单组件
 *
 * @param {Object} props - Component props
 * @param {string} [props.mode='create'] - Form mode: 'create' | 'edit' | 'queryEdit' | 'readonly'
 * @param {Object} [props.initialRule] - Initial rule data (for edit/queryEdit/readonly modes)
 * @param {Function} props.onSubmit - Submit callback function
 * @param {boolean} [props.loading=false] - Loading state for submit button
 * @param {Function} [props.onCancel] - Cancel callback function
 * @param {Array} [props.cameraOptions=[]] - Available camera options
 * @param {Array} [props.haDeviceOptions=[]] - Available HA device options
 * @param {boolean} [props.enableCameraRefresh=false] - Whether to enable camera refresh
 * @param {Function} [props.onRefreshCameras] - Camera refresh callback function
 * @param {boolean} [props.enableActionRefresh=false] - Whether to enable action refresh
 * @param {Function} [props.onRefreshActions] - Action refresh callback function
 * @param {boolean} [props.cameraLoading=false] - Camera loading state
 * @param {boolean} [props.actionLoading=false] - Action loading state
 * @returns {JSX.Element} Rule form component
 */
const RuleForm = ({
  mode = 'create',
  initialRule = null,
  onSubmit,
  loading = false,
  onCancel,
  cameraOptions = [],
  haDeviceOptions: passedHaDeviceOptions = [],
  actionOptions = [],
  onRefreshCameras,
  enableActionRefresh = false,
  onRefreshActions,
  cameraLoading = false,
  actionLoading = false,
}) => {
  const { t } = useTranslation();

// Temporary translation override for debugging
const translations = {
  'smartCenter.conditionType': 'Condition Type'
};

const [form] = Form.useForm();
  const { openModal } = useLogViewerStore();
  const {
    availableMcpServices,
    haDeviceOptions: globalHaDeviceOptions,
    fetchHaDeviceOptions,
    haDeviceLoading: globalHaLoading,
    haDeviceFetched: globalHaFetched
  } = useChatStore();

  const formData = useRuleFormData(initialRule);
  const { aiGeneratedActions, setAiGeneratedActions } = useLogViewerStore();

  const {
    groupedOptions,
    selectedActionKeys: initialSelectedKeys,
    selectedActionObjects,
  } = useRuleFormActions(actionOptions, formData?.automation_actions || []);

  const [selectedActions, setSelectedActions] = useState([]);
  const [sendNotification, setSendNotification] = useState(false);
  const [notificationText, setNotificationText] = useState('');

  const [triggerDeviceOptions, setTriggerDeviceOptions] = useState([]);

  useEffect(() => {
    if (passedHaDeviceOptions?.length === 0 && !globalHaFetched) {
      fetchHaDeviceOptions();
    }
  }, [passedHaDeviceOptions, fetchHaDeviceOptions, globalHaFetched]);

  useEffect(() => {
    const newOptions = [];
    if (cameraOptions?.length > 0) {
      newOptions.push({
        label: t('smartCenter.cameras'),
        options: cameraOptions.map(item => ({
          label: `${item.name}(${item.room_name || ''})`,
          value: item.did,
          _type: 'camera'
        }))
      });
    }

    const haOptions = passedHaDeviceOptions?.length > 0
      ? passedHaDeviceOptions.map(item => ({
          label: `${item.name}${item.room_name ? ` (${item.room_name})` : ''}`,
          value: item.did,
          _type: 'ha'
        }))
      : globalHaDeviceOptions;

    if (haOptions?.length > 0) {
      newOptions.push({
        label: t('smartCenter.haDevices') || 'HA Devices',
        options: haOptions
      });
    }
    setTriggerDeviceOptions(newOptions);
  }, [cameraOptions, passedHaDeviceOptions, globalHaDeviceOptions, t, mode]);

  const [checkedMcpServices, setCheckedMcpServices] = useState([]);
  const [aiRecommendExecuteType, setAiRecommendExecuteType] = useState('dynamic');
  const [aiRecommendActionDescriptions, setAiRecommendActionDescriptions] = useState([]);
  const [aiRecommendActions, setAiRecommendActions] = useState([]);
  const [actionDescriptionError, setActionDescriptionError] = useState(false);

  // Condition type: 'llm', 'direct', 'hybrid', 'detection', or 'face_recognition'
  const [conditionType, setConditionType] = useState('llm');

  // Detection condition state
  const [detectionCondition, setDetectionCondition] = useState(null);

  // 默认检测条件配置
  const getDefaultDetectionCondition = React.useCallback(() => ({
    enabled: true,
    targets: [],
    logic: 'any',
    confidence_threshold: 0.5,
    sensitivity: 5,
    cooldown_seconds: 30,
    min_count: null,
    min_duration_seconds: null,
  }), []);

  // 当切换到目标检测/人脸识别模式时，自动初始化默认检测条件
  useEffect(() => {
    if ((conditionType === 'detection' || conditionType === 'face_recognition') && !detectionCondition) {
      const defaultCondition = getDefaultDetectionCondition();
      if (conditionType === 'face_recognition') {
        defaultCondition.targets = ['face_recognition'];
      }
      setDetectionCondition(defaultCondition);
      form.setFieldsValue({ detection_condition: defaultCondition });
      console.log('Initialized default detection condition:', defaultCondition);
    }
  }, [conditionType, detectionCondition, form, getDefaultDetectionCondition]);

  const [advancedOptionsVisible, setAdvancedOptionsVisible] = useState(false);
  const [triggerPeriod, setTriggerPeriod] = useState('all_day');
  const [triggerIntervalHours, setTriggerIntervalHours] = useState(0);
  const [triggerIntervalMinutes, setTriggerIntervalMinutes] = useState(0);
  const [triggerIntervalSeconds, setTriggerIntervalSeconds] = useState(2);

  useEffect(() => {
    if (mode === 'readonly') {
      return;
    }
    setAiRecommendActions(aiGeneratedActions);
    setAiRecommendExecuteType(aiGeneratedActions.length > 0 ? 'static' : 'dynamic');
  }, [aiGeneratedActions, mode]);

useEffect(() => {
    if (mode === 'create') {
      setAiGeneratedActions([]);
    }
    if (mode !== 'create' && formData) {
      const cameras = formData.cameras?.map(camera =>
        typeof camera === 'object' ? camera.did : camera
      ) || [];
      const ha_devices = formData.ha_devices?.map(device =>
        typeof device === 'object' ? device.did : device
      ) || [];

      form.setFieldsValue({
        name: formData.name,
        condition: formData.condition,
        ha_condition: formData.ha_condition || '',
        trigger_devices: [...cameras, ...ha_devices],
      });

      // Set condition_type from formData
      if (formData.condition_type) {
        setConditionType(formData.condition_type);
        form.setFieldsValue({ condition_type: formData.condition_type });
        console.log('Restoring condition type from formData:', formData.condition_type);
      }

      // Set detection_condition from formData
      if (formData.detection_condition) {
        setDetectionCondition(formData.detection_condition);
        form.setFieldsValue({ detection_condition: formData.detection_condition });
        console.log('Restoring detection condition from formData:', formData.detection_condition);
      }

      // Log all formData for debugging
      console.log('FormData loaded:', {
        name: formData.name,
        condition: formData.condition,
        cameras: formData.cameras,
        ha_devices: formData.ha_devices,
        condition_type: formData.condition_type,
        detection_condition: formData.detection_condition
      });

      if (initialSelectedKeys && initialSelectedKeys.length > 0) {
        setSelectedActions(initialSelectedKeys);
      } else {
        const actionKeys = selectedActionObjects.map(action => {
          const serverName = action.mcp_server_name || 'unknown';
          return `${serverName}#${action.introduction}`;
        });
        setSelectedActions(actionKeys);
      }

      if (formData.notify?.content) {
        setSendNotification(true);
        setNotificationText(formData.notify.content);
      }

      setCheckedMcpServices(formData.mcp_list?.map(mcp => `${mcp?.server_name}#${mcp?.client_id}`) || []);
      setAiRecommendExecuteType(formData.ai_recommend_execute_type || 'static');
      setAiRecommendActionDescriptions(formData.ai_recommend_action_descriptions || []);
      setAiRecommendActions(formData.ai_recommend_actions || []);
      if(formData?.ai_recommend_actions?.length === 0) {
        setAiGeneratedActions([]);
      }
      if (formData.filter) {
        const filterData = formDataUtils.toFormFormat(formData.filter);
        setTriggerPeriod(filterData.triggerPeriod || 'all_day');
        setTriggerIntervalHours(filterData.triggerIntervalHours || 0);
        setTriggerIntervalMinutes(filterData.triggerIntervalMinutes || 0);
        setTriggerIntervalSeconds(filterData.triggerIntervalSeconds || 2);
        // setAdvancedOptionsVisible(true);
      }
    }
  }, [mode, formData, form, initialSelectedKeys, selectedActionObjects, setAiGeneratedActions]);



  const isReadonly = mode === 'readonly';

  const getBtnText = () => {
    if (mode === 'create' || mode === 'queryEdit') {
      return t('smartCenter.saveRule');
    }
    if (mode === 'edit') {
      return t('smartCenter.updateRule');
    }
    return '';
  };

  const refreshMiotInfo = async (refreshFun) => {
    if (!refreshFun) { return; }

    try {
      const res = await refreshFun();
      const { code: refreshCode, message: refreshMessage } = res || {};
      if (refreshCode !== 0) {
        message.error(refreshMessage);
      }
    } catch (error) {
      console.error('Refresh error:', error);
      message.error(t('smartCenter.refreshFailed'));
    }
  };

  const renderDropdownWithRefresh = (loading, text, refreshFun) => {
    if (!refreshFun) {
      return undefined;
    }

    return (menu) => (
      <>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            padding: '8px 12px',
            cursor: loading ? 'not-allowed' : 'pointer',
            color: loading ? '#999' : '#1677ff',
            fontWeight: 500,
            borderBottom: '1px solid #f0f0f0',
            userSelect: 'none',
            transition: 'background 0.2s',
          }}
          onClick={loading ? undefined : () => refreshMiotInfo(refreshFun)}
          onMouseDown={e => e.preventDefault()}
        >
          {loading ? <Spin size="small" style={{ marginRight: 8 }} /> : <ReloadOutlined style={{ marginRight: 8 }} />}
          {text}
        </div>
        {menu}
      </>
    );
  };


  const getBackendData = async (type = 'submit') => {
    const values = await form.validateFields();

    const hasActions = selectedActions.length > 0;
    const hasNotification = sendNotification && notificationText.trim();

    if (type === 'submit') {
      const hasAiRecommendActions = aiRecommendExecuteType === 'dynamic'
        ? aiRecommendActionDescriptions.length > 0
        : aiRecommendActions.length > 0;

      if (!hasAiRecommendActions && !hasActions && !hasNotification) {
        message.error(t('common.pleaseSelectAction'));
        return false;
      }
    }

    const allSelectedActionKeys = selectedActions;
    const automation_actions = allSelectedActionKeys
      .map(key => {
        return actionOptions.find(action => {
          const serverName = action.mcp_server_name || 'unknown';
          return `${serverName}#${action.introduction}` === key;
        });
      })
      .filter(Boolean)
      .map(action => ({
        mcp_client_id: action.mcp_client_id,
        mcp_tool_name: action.mcp_tool_name,
        mcp_tool_input: action.mcp_tool_input,
        mcp_server_name: action.mcp_server_name,
        mcp_tool_description: action.mcp_tool_description,
        introduction: action.introduction || '',
      }));

    // Split trigger_devices into cameras and ha_devices
    const selectedDevices = values.trigger_devices || [];
    const cameras = [];
    const ha_devices = [];

    // Helper to check if ID is camera or HA
    const isCamera = (id) => cameraOptions.some(c => c.did === id);
    const isHaDevice = (id) => (passedHaDeviceOptions?.some(d => d.did === id) || globalHaDeviceOptions.some(d => d.value === id));

    selectedDevices.forEach(id => {
      if (isCamera(id)) {
        const camera = cameraOptions.find(c => c.did === id);
        cameras.push(camera || id);
      } else if (isHaDevice(id)) {
        ha_devices.push(id);
      } else {
        // Fallback
        cameras.push(id);
      }
    });

    const formData = {
      name: values.name,
      cameras,
      ha_devices,
      condition: conditionType === 'direct' ? values.ha_condition : values.condition,
      condition_type: conditionType,
      ha_condition: values.ha_condition,
      detection_condition: (conditionType === 'detection' || conditionType === 'face_recognition') ? detectionCondition : null,
      automation_actions,
      ai_recommend_execute_type: aiRecommendExecuteType,
      ai_recommend_action_descriptions: aiRecommendActionDescriptions,
      ai_recommend_actions: aiRecommendActions || [],
      notify: hasNotification ? {
        id: initialRule?.execute_info?.notify?.id || null,
        content: notificationText.trim(),
      } : null,
      filter: {
        triggerPeriod,
        triggerIntervalHours,
        triggerIntervalMinutes,
        triggerIntervalSeconds,
      },
      mcp_list: checkedMcpServices.map(service => availableMcpServices.find(mcp => `${mcp?.server_name}#${mcp?.client_id}` === service)).filter(Boolean),
      enabled: initialRule?.enabled !== undefined ? initialRule.enabled : true,
    };

    const backendData = convertFormDataToBackend(formData);
    if (mode === 'edit' || mode === 'queryEdit') {
      backendData.id = initialRule?.id;
    }

    console.log('[RuleForm] Submitting data:', JSON.stringify(backendData, null, 2));

    return backendData;
  };

  const handleSubmit = async (type = 'submit') => {
    const backendData = await getBackendData(type);
    if (!backendData) {
      return;
    }
    if (type === 'submit') {
      if (aiRecommendActionDescriptions.length !== 0 && aiRecommendActions.length === 0) {
        setActionDescriptionError(true);
        message.error(t('smartCenter.pleaseEnterActionDescription'));
        return;
      }
      setActionDescriptionError(false);
      await onSubmit(backendData);
    }
    if (type === 'cancel') {
      await onCancel(backendData);
    }
  };

  const handleFormValuesChange = (changedValues) => {
    if ('trigger_devices' in changedValues) {
      setAiRecommendActions([]);
      setAiRecommendExecuteType('dynamic');
    }
  };

  const isSubmitDisabled = isReadonly || loading;
  return (
    <Form form={form} layout="vertical" onValuesChange={handleFormValuesChange}>
      <Form.Item
        className={styles.customFormLabel}
        label={t('smartCenter.serviceName')}
        name="name"
        rules={[{ required: true, message: t('smartCenter.pleaseEnterRuleName') }]}
      >
        <Input
          placeholder={t('smartCenter.exampleService')}
          disabled={isSubmitDisabled}
        />
      </Form.Item>

      <Form.Item
        className={styles.customFormLabel}
        label={t('smartCenter.selectTriggerDevices')}
        name="trigger_devices"
        rules={[{ required: true, message: t('smartCenter.pleaseSelectTriggerDevices') }]}
      >
        <Select
          mode="multiple"
          allowClear
          placeholder={t('smartCenter.pleaseSelectTriggerDevices')}
          disabled={isSubmitDisabled}
          options={triggerDeviceOptions}
          className={styles.select}
          dropdownRender={renderDropdownWithRefresh(
            globalHaLoading || cameraLoading,
            t('common.refresh'),
            async () => {
              if (onRefreshCameras) {
                await refreshMiotInfo(onRefreshCameras);
              }
              await refreshMiotInfo(refreshHaAutomation);
              await fetchHaDeviceOptions(true);
              return { code: 0 };
            }
          )}
        />
      </Form.Item>

      <Form.Item
        className={styles.customFormLabel}
        label={
          <span>
            {t('smartCenter.conditionType') || '条件类型'}
            <Tooltip
              placement="right"
              title={
                <div style={{ padding: '8px', maxWidth: '400px' }}>
                  <div style={{ fontWeight: 'bold', marginBottom: '8px' }}>{t('smartCenter.conditionTypeSelect') || 'Condition Type Selection'}</div>
                  <div style={{ marginTop: '8px' }}>
                    <div style={{ fontWeight: 'bold' }}>{t('smartCenter.llmModeLabel') || 'LLM Mode:'}</div>
                    <div style={{ marginLeft: '8px', marginBottom: '8px' }}>{t('smartCenter.conditionTypeTip2')}</div>
                  </div>
                  <div style={{ marginTop: '8px' }}>
                    <div style={{ fontWeight: 'bold' }}>{t('smartCenter.directModeLabel') || 'Direct Mode:'}</div>
                    <div style={{ marginLeft: '8px', marginBottom: '8px' }}>{t('smartCenter.conditionTypeTip3')}</div>
                  </div>
                  <div style={{ marginTop: '8px' }}>
                    <div style={{ fontWeight: 'bold' }}>{t('smartCenter.hybridModeLabel') || 'Hybrid Mode:'}</div>
                    <div style={{ marginLeft: '8px', marginBottom: '8px' }}>{t('smartCenter.conditionTypeTip4')}</div>
                  </div>
                  <div style={{ marginTop: '8px', fontStyle: 'italic' }}>
                    {t('smartCenter.conditionTypeTip5')}
                  </div>
                </div>
              }>
              <QuestionCircleOutlined style={{ marginLeft: 4, color: '#999' }} />
            </Tooltip>
          </span>}
        name="condition_type"
      >
        {/* Condition Type Selector */}
        <div className={styles.conditionTypeSelector}>
          <Select
            className={styles.conditionTypeSelect}
            value={conditionType}
            onChange={(value) => {
              setConditionType(value);
              const triggerDevices = form.getFieldValue('trigger_devices') || [];
              const hasHaDevice = triggerDevices.some(id => {
                return (passedHaDeviceOptions?.some(d => d.did === id) ||
                  globalHaDeviceOptions.some(d => d.value === id));
              });
              const hasCamera = triggerDevices.some(id => {
                return cameraOptions.some(c => c.did === id);
              });
              console.log('Condition Type changed:', value, 'Has HA:', hasHaDevice, 'Has Camera:', hasCamera);
              if (value === 'direct' && !hasHaDevice) {
                message.info(t('smartCenter.directMode') + ' ' + t('smartCenter.conditionTypeTip3'));
              }
              if (value === 'hybrid' && (!hasHaDevice || !hasCamera)) {
                message.info(t('smartCenter.hybridMode') + ' ' + t('smartCenter.conditionTypeTip4'));
              }
              if ((value === 'detection' || value === 'face_recognition') && !hasCamera) {
                message.info(t('detection.needCamera') || 'Detection mode requires at least one camera');
              }
            }}
            disabled={isSubmitDisabled}
          >
            <Option value="llm">{t('smartCenter.llmMode')}</Option>
            <Option value="direct">{t('smartCenter.directMode')}</Option>
            <Option value="hybrid">{t('smartCenter.hybridMode')}</Option>
            <Option value="detection">{t('detection.mode') || '目标检测'}</Option>
            <Option value="face_recognition">{t('smartCenter.faceRecognitionMode') || '人脸识别'}</Option>
          </Select>
        </div>
      </Form.Item>

      {/* 混合模式：先显示HA设备状态条件（Step 1） */}
      {conditionType === 'hybrid' && (
        <Form.Item
          className={styles.customFormLabel}
          label={
            <span>
              {t('smartCenter.haCondition') || '设备状态'}
              <Tooltip
                placement="right"
                title={
                  <div>
                    <div style={{ fontWeight: 'bold' }}>{t('smartCenter.haConditionTooltipTitle') || 'Device State (Hybrid Mode Step 1)'}</div>
                    <div style={{ marginTop: 8 }}>{t('smartCenter.haConditionTooltipDesc') || 'Use direct mode to quickly check HA device state:'}</div>
                    <div>• {t('smartCenter.haConditionTooltipSkip') || 'If this condition is not met, skip camera analysis'}</div>
                    <div>• {t('smartCenter.haConditionTooltipProceed') || 'If this condition is met, proceed to camera analysis'}</div>
                    <div style={{ marginTop: 8 }}>{t('smartCenter.examples') || 'Examples:'}</div>
                    <div>• state == on</div>
                    <div>• state in [on,open]</div>
                    <div>{'• temperature > 25'}</div>
                  </div>
                }>
                <QuestionCircleOutlined style={{ marginLeft: 4, color: '#999' }} />
              </Tooltip>
            </span>}
          name="ha_condition"
          rules={[{ required: true, message: t('smartCenter.pleaseEnterTriggerCondition') }]}
        >
          <Input
            placeholder="例如：state == on"
            disabled={isReadonly || loading}
          />
        </Form.Item>
      )}

      {/* 直接模式：设备状态 */}
      {conditionType === 'direct' && (
        <Form.Item
          className={styles.customFormLabel}
          label={
            <span>
              {t('smartCenter.haCondition') || '设备状态'}
              <Tooltip
                placement="right"
                title={
                  <div>
                    <div style={{ fontWeight: 'bold' }}>{t('smartCenter.directModeTooltipTitle') || 'Direct Mode - Device State'}</div>
                    <div style={{ marginTop: 8 }}>{t('smartCenter.directModeTooltipDesc') || 'Use direct mode to check device state (zero token):'}</div>
                    <div>• {t('smartCenter.directModeTooltipFast') || 'Fast local state matching without LLM'}</div>
                    <div>• {t('smartCenter.directModeTooltipHaOnly') || 'Only for HA devices (no cameras)'}</div>
                    <div style={{ marginTop: 8 }}>{t('smartCenter.examples') || 'Examples:'}</div>
                    <div>• state == on</div>
                    <div>• state in [on,open]</div>
                    <div>{'• temperature > 25'}</div>
                  </div>
                }>
                <QuestionCircleOutlined style={{ marginLeft: 4, color: '#999' }} />
              </Tooltip>
            </span>}
          name="ha_condition"
          rules={[{ required: true, message: t('smartCenter.pleaseEnterTriggerCondition') }]}
        >
          <Input
            placeholder="例如：state == on"
            disabled={isReadonly || loading}
          />
        </Form.Item>
      )}

      {/* 目标检测模式：检测条件配置 */}
      {(conditionType === 'detection' || conditionType === 'face_recognition') && (
        <Form.Item
          className={styles.customFormLabel}
          label={t('detection.conditionConfig') || '检测条件配置'}
        >
          <DetectionConditionForm
            initialValue={detectionCondition}
            conditionType={conditionType}
            onChange={(value) => {
              setDetectionCondition(value);
              form.setFieldsValue({ detection_condition: value });
            }}
            disabled={isReadonly || loading}
            readOnly={isReadonly}
          />
        </Form.Item>
      )}

      {/* LLM模式和混合模式：触发条件 (检测模式不需要) */}
      {conditionType !== 'direct' && conditionType !== 'detection' && conditionType !== 'face_recognition' && (
        <Form.Item
          className={styles.customFormLabel}
          label={
            <span>
              {conditionType === 'hybrid' 
                ? (t('smartCenter.cameraCondition') || '触发条件') 
                : t('smartCenter.triggerCondition')}
              <Tooltip
                placement="right"
                title={
                  conditionType === 'hybrid' ? (
                    <div>
                      <div style={{ fontWeight: 'bold' }}>{t('smartCenter.cameraConditionTooltipTitle') || 'Trigger Condition (Hybrid Mode Step 2)'}</div>
                      <div style={{ marginTop: 8 }}>{t('smartCenter.cameraConditionTooltipDesc') || 'LLM will use this condition to analyze camera images:'}</div>
                      <div>• {t('smartCenter.cameraConditionTooltipWhen') || 'Only checked when device state condition is met'}</div>
                      <div>• {t('smartCenter.cameraConditionTooltipUse') || 'Used for visual analysis (person detection, behavior, etc.)'}</div>
                      <div style={{ marginTop: 8 }}>{t('smartCenter.examples') || 'Examples:'}</div>
                      <div>• {t('smartCenter.cameraConditionExample1') || 'Is there a person sleeping?'}</div>
                      <div>• {t('smartCenter.cameraConditionExample2') || 'Is there a person moving in the room?'}</div>
                      <div>• {t('smartCenter.cameraConditionExample3') || 'Is there a pet on the sofa?'}</div>
                    </div>
                  ) : (
                    <div>
                      <div>{t('smartCenter.triggerConditionTip1')}</div>
                      <div style={{ marginTop: 8 }}>{t('smartCenter.triggerConditionTip2')}</div>
                      <div style={{ marginTop: 4 }}>• {t('smartCenter.triggerConditionExample1')}</div>
                      <div>• {t('smartCenter.triggerConditionExample2')}</div>
                      <div>• {t('smartCenter.triggerConditionExample3')}</div>
                      <div>• {t('smartCenter.triggerConditionExample4')}</div>
                      <div>• ...</div>
                      <div style={{ marginTop: 8 }}>{t('smartCenter.triggerConditionTip3')}</div>
                    </div>
                  )
                }>
                <QuestionCircleOutlined style={{ marginLeft: 4, color: '#999' }} />
              </Tooltip>
            </span>}
          name="condition"
          rules={[{ required: true, message: t('smartCenter.pleaseEnterTriggerCondition') }]}
        >
          <Input
            placeholder={conditionType === 'hybrid' ? "例如：客厅是否有人？" : t('smartCenter.exampleMove')}
            disabled={isReadonly || loading}
          />
        </Form.Item>
      )}

      <Form.Item
        label={t('smartCenter.executionAction')}
        required
        className={styles.customFormLabel}
        validateStatus={(() => {
          const hasActions = selectedActions.length > 0;
          const hasNotification = sendNotification && notificationText.trim();

          if (!hasActions && !hasNotification &&
            (selectedActions.length > 0 || (sendNotification && notificationText.trim()) ||
              form.getFieldError('name')?.length > 0 || form.getFieldError('condition')?.length > 0)) {
            return 'error';
          }
          return '';
        })()}
      >
        <div className={styles.actionGroup}>
          {mode !== 'readonly' && mode !== 'queryEdit' && (
            <div className={styles.actionItem}>
              <div className={styles.actionLabel}>MCP</div>
              <Select
                disabled={isSubmitDisabled}
                mode="multiple"
                placeholder={t('smartCenter.pleaseSelectMcp')}
                value={checkedMcpServices}
                options={availableMcpServices.map(service => ({
                  label: `${service?.server_name}#${service?.client_id}`,
                  value: `${service?.server_name}#${service?.client_id}`,
                }))}
                onChange={(values) => {
                  setCheckedMcpServices(values)
                  setAiRecommendActions([]);
                  setAiRecommendExecuteType('dynamic');
                }}
              />
            </div>
          )}
          <div className={styles.actionItem}>
            <div className={styles.actionLabel}>
              <span>
                {t('smartCenter.deviceControl')}
              </span>
            </div>
            <div className={classNames(styles.actionControl)}>
              <Select
                mode="tags"
                placeholder={t('smartCenter.pleaseSelectDevice')}
                disabled={isSubmitDisabled}
                value={aiRecommendActionDescriptions}
                status={actionDescriptionError ? 'error' : ''}
                onChange={(values) => {
                  setAiRecommendActionDescriptions(values);
                  setAiRecommendActions([]);
                  setAiRecommendExecuteType('dynamic');
                  setActionDescriptionError(false);
                }}
              />
              <Button
                type='primary'
                danger
                disabled={isSubmitDisabled}
                className={styles.actionControlButton}
                onClick={() => {
                  setActionDescriptionError(false);
                  const cameras = form.getFieldValue('cameras')
                  if (checkedMcpServices.length === 0) {
                    message.error(t('smartCenter.pleaseSelectMcp'));
                    return;
                  }
                  const mcp_list = availableMcpServices.filter(mcp => checkedMcpServices.includes(`${mcp.server_name}#${mcp.client_id}`));
                  const mcp_list_ids = mcp_list.map(mcp => mcp.client_id);
                  if (aiRecommendActionDescriptions.length > 0) {
                    openModal(aiRecommendActionDescriptions, cameras, mcp_list_ids);
                  } else {
                    message.error(t('smartCenter.pleaseEnterActionDescription'));
                  }
                }}
              >
                {t('smartCenter.generateStaticActionList')}
              </Button>
            </div>
            <div className={classNames(styles.actionControl, styles.actionControl2)}>
              <Select
                mode="tags"
                tagRender={(props) => <SelectTagRender aiRecommendActions={aiRecommendActions} {...props} />}
                placeholder={t('smartCenter.pleaseSelectAiRecommendedAction')}
                disabled={true}
                value={aiRecommendActions.map(action => action.introduction)}
                status={actionDescriptionError ? 'error' : ''}
                suffixIcon={null}
              />
            </div>
            <div className={classNames(styles.actionControl, styles.actionControl2)}>
              <span>
                {t('smartCenter.whetherToCache')}
                <Tooltip
                  placement="right"
                  title={
                    <div>
                      <div>{t('smartCenter.deviceControlTip1')}</div>
                      <div style={{ marginTop: 8 }}>{t('smartCenter.deviceControlTip2')}</div>
                    </div>
                  }>
                  <InfoCircleOutlined style={{ marginLeft: 4, color: '#999' }} />
                </Tooltip>
              </span>
              <Switch
                checked={aiRecommendExecuteType === 'static'}
                onChange={(checked) => {
                  setAiRecommendExecuteType(checked ? 'static' : 'dynamic');
                }}
                disabled={isSubmitDisabled || aiRecommendActions.length === 0}
              />
            </div>
          </div>
          <div className={styles.actionItem}>
            <div className={styles.actionLabel}>{t('smartCenter.automationScene')}</div>
            <Select
              mode="multiple"
              allowClear
              placeholder={t('smartCenter.automationSceneDescription')}
              disabled={isSubmitDisabled}
              options={groupedOptions}
              value={selectedActions}
              onChange={(values) => {
                setSelectedActions(values);
              }}
              className={styles.select}
              dropdownRender={enableActionRefresh && onRefreshActions
                ? renderDropdownWithRefresh(actionLoading, t('smartCenter.refreshActions'), onRefreshActions)
                : undefined
              }
            />
          </div>


          <div className={styles.actionItem}>
            <div className={styles.actionLabel}>
              <Checkbox
                checked={sendNotification}
                onChange={(e) => setSendNotification(e.target.checked)}
                disabled={isSubmitDisabled}
              >
                {t('smartCenter.sendMiHomeNotification')}
              </Checkbox>
            </div>
            {sendNotification && (
              <Input.TextArea
                placeholder={t('smartCenter.pleaseEnterNotification')}
                value={notificationText}
                onChange={(e) => setNotificationText(e.target.value)}
                disabled={isSubmitDisabled}
                rows={3}
              />
            )}
          </div>
        </div>
      </Form.Item>

      <div className={styles.advancedOptionsSection}>
        <div
          className={styles.advancedOptionsHeader}
          onClick={() => !isReadonly && setAdvancedOptionsVisible(!advancedOptionsVisible)}
        >
          <span className={styles.advancedOptionsTitle}>{t('smartCenter.moreAdvancedOptions')}</span>
          {advancedOptionsVisible ? <UpOutlined style={{ color: 'var(--text-color-5)' }} /> : <DownOutlined style={{ color: 'var(--text-color-5)' }} />}
        </div>

        {advancedOptionsVisible && (
          <div className={styles.advancedOptionsContent}>
            <div className={styles.advancedOptionItem}>
              <div className={styles.advancedOptionLabel}>{t('smartCenter.triggerPeriod')}:</div>
              <Select
                placeholder={t('smartCenter.nonRequired')}
                value={triggerPeriod}
                onChange={setTriggerPeriod}
                options={TRIGGER_PERIOD_OPTIONS}
                className={styles.advancedSelect}
                allowClear
                disabled={isSubmitDisabled}
              />
            </div>

            <div className={styles.advancedOptionItem}>
              <div className={styles.advancedOptionLabel}>{t('smartCenter.triggerInterval')}:</div>
              <div className={styles.triggerIntervalDescription}>
                {t('smartCenter.triggerIntervalDescription')}
              </div>
              <TimeSelector
                hours={triggerIntervalHours}
                minutes={triggerIntervalMinutes}
                seconds={triggerIntervalSeconds}
                onHoursChange={setTriggerIntervalHours}
                onMinutesChange={setTriggerIntervalMinutes}
                onSecondsChange={setTriggerIntervalSeconds}
                hoursOptions={TRIGGER_INTERVAL_OPTIONS.hours}
                minutesOptions={TRIGGER_INTERVAL_OPTIONS.minutes}
                secondsOptions={TRIGGER_INTERVAL_OPTIONS.seconds}
                className={styles.triggerIntervalSelector}
                disabled={isSubmitDisabled}
              />
            </div>
          </div>
        )}
      </div>

      {!isReadonly && (
        <div className={styles.saveBtnWrap}>
          {(mode === 'edit' || mode === 'queryEdit') && onCancel && (
            <Button onClick={() => handleSubmit('cancel')} disabled={isSubmitDisabled}>{t('common.cancel')}</Button>
          )}
          <Tooltip
            title={t('smartCenter.pleaseEnterActionDescription')}
            placement="top"
          >
            <Button
              type='primary'
              disabled={isSubmitDisabled}
              className={mode === 'create' ? styles.saveBtn : ''}
              block={mode === 'create'}
              onClick={() => handleSubmit('submit')}
              loading={loading}
            >
              {getBtnText()}
            </Button>

          </Tooltip>

        </div>
      )}
    </Form>
  );
};

export default RuleForm;
