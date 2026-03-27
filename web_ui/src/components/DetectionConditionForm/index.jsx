/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  Form,
  Checkbox,
  Select,
  Slider,
  InputNumber,
  Tooltip,
  Row,
  Col,
  Card,
  Tag,
} from 'antd';
import { listFaceProfiles } from '@/api';
import {
  QuestionCircleOutlined,
  EyeOutlined,
  ClockCircleOutlined,
  BarChartOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styles from './index.module.less';

const { Option } = Select;

/**
 * DetectionConditionForm Component
 * 目标检测触发条件配置组件
 *
 * @param {Object} props - Component props
 * @param {Object} [props.initialValue] - Initial detection condition value
 * @param {Function} [props.onChange] - Change callback function
 * @param {boolean} [props.disabled=false] - Disabled state
 * @param {boolean} [props.readOnly=false] - Read-only state
 * @param {string} [props.conditionType] - Condition type: 'detection' or 'face_recognition'
 */
const DetectionConditionForm = ({
  initialValue = null,
  onChange,
  disabled = false,
  readOnly = false,
  conditionType = null,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();

  // 本地状态 - 目标检测默认启用
  const [selectedTargets, setSelectedTargets] = useState([]);
  const [logicType, setLogicType] = useState('any');
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.5);
  const [sensitivity, setSensitivity] = useState(5);
  const [cooldownSeconds, setCooldownSeconds] = useState(30);
  const [minCount, setMinCount] = useState(1);
  const [minDuration, setMinDuration] = useState(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [faceProfiles, setFaceProfiles] = useState([]);
  const [selectedFaceTarget, setSelectedFaceTarget] = useState(null);
  const [minFaceScore, setMinFaceScore] = useState(0.1);
  const [maxFaces, setMaxFaces] = useState(10);

  // 使用 ref 来跟踪是否已经初始化，以及上一次的 initialValue
  const initializedRef = useRef(false);
  const prevInitialValueRef = useRef(null);

  // 目标类型选项
  const targetOptions = [
    { value: 'person', label: t('detection.targetPerson') || '人', icon: '👤', color: '#1890ff' },
    { value: 'cat', label: t('detection.targetCat') || '猫', icon: '🐱', color: '#722ed1' },
    { value: 'dog', label: t('detection.targetDog') || '狗', icon: '🐶', color: '#eb2f96' },
  ];

  // 逻辑类型选项
  const logicOptions = [
    {
      value: 'any',
      label: t('detection.logicAny') || '任意目标出现',
      description: t('detection.logicAnyDesc') || '任意选定的目标被检测到即触发',
    },
    {
      value: 'all',
      label: t('detection.logicAll') || '所有目标同时出现',
      description: t('detection.logicAllDesc') || '所有选定的目标必须同时被检测到才触发',
    },
    {
      value: 'count',
      label: t('detection.logicCount') || '目标数量达标',
      description: t('detection.logicCountDesc') || '检测到的目标总数达到设定值才触发',
    },
  ];

  // 从initialValue初始化状态（只在组件挂载时执行一次）
  useEffect(() => {
    // 只初始化一次，避免编辑时状态闪动
    if (initializedRef.current) {
      return;
    }

    // 标记已初始化
    initializedRef.current = true;

    if (initialValue) {
      // Backward compatibility: migrate old 'face' target to 'face_recognition'
      let newTargets = (initialValue.targets || []).map((t) => (t === 'face' ? 'face_recognition' : t));
      // 在“目标检测”模式下，过滤掉历史数据里的“人脸识别”目标，避免显示/提交异常
      if (conditionType !== 'face_recognition') {
        newTargets = newTargets.filter((t) => t !== 'face_recognition');
      }
      const newLogic = initialValue.logic || 'any';
      const newConfidence = initialValue.confidence_threshold ?? 0.5;
      const newSensitivity = initialValue.sensitivity ?? 5;
      const newCooldown = initialValue.cooldown_seconds ?? 30;
      const newMinCount = initialValue.min_count ?? 1;
      const newMinDuration = initialValue.min_duration_seconds || null;

      setSelectedTargets(newTargets);
      setLogicType(newLogic);
      setConfidenceThreshold(newConfidence);
      setSensitivity(newSensitivity);
      setCooldownSeconds(newCooldown);
      setMinCount(newMinCount);
      setMinDuration(newMinDuration);

      // 如果有人脸识别相关配置
      if (conditionType === 'face_recognition' && newTargets.includes('face_recognition')) {
        setSelectedFaceTarget(initialValue.face_target || null);
        setMinFaceScore(initialValue.min_face_score ?? 0.1);
        setMaxFaces(initialValue.max_faces ?? 10);
      }

      form.setFieldsValue({
        targets: newTargets,
        logic: newLogic,
        min_count: newMinCount,
        face_target: conditionType === 'face_recognition' ? (initialValue.face_target || null) : undefined,
        min_face_score: conditionType === 'face_recognition' ? (initialValue.min_face_score ?? 0.1) : undefined,
        max_faces: conditionType === 'face_recognition' ? (initialValue.max_faces ?? 10) : undefined,
      });
    } else if (conditionType === 'face_recognition') {
      // 如果是人脸识别模式且没有初始值，自动设置 face_recognition 目标
      setSelectedTargets(['face_recognition']);
      setMinFaceScore(0.1);
      setMaxFaces(10);
      form.setFieldsValue({
        targets: ['face_recognition'],
        min_face_score: 0.1,
        max_faces: 10,
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // 只在挂载时执行

  // 当状态变化时触发onChange（但跳过初始化阶段）
  const initCompletedRef = useRef(false);
  useEffect(() => {
    // 跳过第一次渲染（初始化阶段）
    if (!initCompletedRef.current) {
      initCompletedRef.current = true;
      return;
    }

    let finalTargets = selectedTargets;
    // 如果是人脸识别模式，确保 targets 包含 face_recognition
    if (conditionType === 'face_recognition') {
      if (!finalTargets.includes('face_recognition')) {
        finalTargets = [...finalTargets, 'face_recognition'];
        setSelectedTargets(finalTargets);
      }
    }

    const condition = {
      enabled: true, // 目标检测默认启用
      targets: finalTargets,
      logic: logicType,
      confidence_threshold: confidenceThreshold,
      sensitivity,
      cooldown_seconds: cooldownSeconds,
      min_count: logicType === 'count' ? minCount : null,
      min_duration_seconds: minDuration,
    };

    if (conditionType === 'face_recognition') {
      condition.face_target = selectedFaceTarget;
      condition.min_face_score = minFaceScore;
      condition.max_faces = maxFaces;
    }

    if (onChange) {
      onChange(condition);
    }
  }, [
    selectedTargets,
    logicType,
    confidenceThreshold,
    sensitivity,
    cooldownSeconds,
    minCount,
    minDuration,
    selectedFaceTarget,
    conditionType,
    minFaceScore,
    maxFaces,
    onChange,
  ]);

  // 处理目标类型选择
  const handleTargetChange = (checkedValues) => {
    setSelectedTargets(checkedValues);
  };

  // 获取灵敏度标签
  const getSensitivityLabel = (value) => {
    if (value <= 3) return t('detection.sensitivityLow') || '低';
    if (value <= 7) return t('detection.sensitivityMedium') || '中';
    return t('detection.sensitivityHigh') || '高';
  };

  // 获取置信度标签
  const getConfidenceLabel = (value) => {
    if (value < 0.4) return t('detection.confidenceLow') || '宽松';
    if (value < 0.7) return t('detection.confidenceMedium') || '标准';
    return t('detection.confidenceHigh') || '严格';
  };

  // 加载人脸库列表
  useEffect(() => {
    const loadFaceProfiles = async () => {
      try {
        const res = await listFaceProfiles();
        if (res && res.code === 0) {
          setFaceProfiles(res.data || []);
        }
      } catch (error) {
        console.error('Failed to load face profiles:', error);
      }
    };
    loadFaceProfiles();
  }, []);

  if (readOnly) {
    return (
      <div className={styles.readOnlyContainer}>
        <div className={styles.readOnlyHeader}>
          <EyeOutlined />
          <span>{t('detection.detectionTrigger') || '目标检测触发'}</span>
          <Tag color="success">{t('common.enabled') || '已启用'}</Tag>
        </div>
        <div className={styles.readOnlyContent}>
          <div className={styles.readOnlyItem}>
            <span className={styles.label}>{t('detection.targets') || '检测目标'}:</span>
            <span className={styles.value}>
              {conditionType === 'face_recognition' ? (
                <>
                  {selectedFaceTarget ? (
                    <Tag color="#fa8c16">
                      🧑‍🦰 {selectedFaceTarget === 'unknown' ? (t('detection.unknownFace') || '未知') : selectedFaceTarget}
                    </Tag>
                  ) : (
                    <Tag color="#fa8c16">🧑‍🦰 {t('detection.targetFaceRecognition') || '人脸识别'}</Tag>
                  )}
                </>
              ) : (
                selectedTargets.map((target) => {
                  const option = targetOptions.find((o) => o.value === target);
                  return option ? (
                    <Tag key={target} color={option.color}>
                      {option.icon} {option.label}
                    </Tag>
                  ) : null;
                })
              )}
            </span>
          </div>
          {conditionType !== 'face_recognition' && (
            <>
              <div className={styles.readOnlyItem}>
                <span className={styles.label}>{t('detection.logic') || '触发逻辑'}:</span>
                <span className={styles.value}>
                  {logicOptions.find((o) => o.value === logicType)?.label}
                </span>
              </div>
              <div className={styles.readOnlyItem}>
                <span className={styles.label}>{t('detection.confidence') || '置信度'}:</span>
                <span className={styles.value}>{confidenceThreshold}</span>
              </div>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <Card className={styles.detectionConditionCard} size="small">
      <Form form={form} layout="vertical" disabled={disabled}>
        <div className={styles.configSection}>
            {/* 人脸识别模式：显示人脸库选项和参数 */}
            {conditionType === 'face_recognition' && (
              <>
                <Form.Item
                  label={
                    <span className={styles.sectionLabel}>
                      {t('detection.faceTarget') || '人脸识别目标'}
                    </span>
                  }
                  name="face_target"
                  rules={[
                    {
                      required: true,
                      message: t('detection.pleaseSelectFaceTarget') || '请选择人脸识别目标',
                    },
                  ]}
                >
                  <Select
                    placeholder={t('detection.pleaseSelectFaceTarget') || '请选择人脸识别目标'}
                    value={selectedFaceTarget}
                    onChange={setSelectedFaceTarget}
                    allowClear
                  >
                    <Option value="unknown">
                      <Tag color="default">❓ {t('detection.unknownFace') || '未知'}</Tag>
                    </Option>
                    {faceProfiles.map((profile) => (
                      <Option key={profile.id} value={profile.name}>
                        <Tag color="blue">👤 {profile.name}</Tag>
                      </Option>
                    ))}
                  </Select>
                </Form.Item>

                <Form.Item
                  label={
                    <span className={styles.sectionLabel}>
                      {t('detection.minFaceScore') || '最小人脸置信度'}
                      <Tooltip
                        title={t('detection.minFaceScoreTooltip') || '控制人脸检测的最低置信度分数，值越高检测越严格'}
                      >
                        <QuestionCircleOutlined className={styles.helpIcon} />
                      </Tooltip>
                      <Tag color="blue" className={styles.valueTag}>
                        {minFaceScore}
                      </Tag>
                    </span>
                  }
                >
                  <Slider
                    min={0.0}
                    max={1.0}
                    step={0.05}
                    value={minFaceScore}
                    onChange={setMinFaceScore}
                    marks={{
                      0.0: t('detection.confidenceLow') || '宽松',
                      0.5: t('detection.confidenceMedium') || '标准',
                      1.0: t('detection.confidenceHigh') || '严格',
                    }}
                  />
                </Form.Item>

                <Form.Item
                  label={
                    <span className={styles.sectionLabel}>
                      {t('detection.maxFaces') || '最大检测人脸数'}
                      <Tooltip
                        title={t('detection.maxFacesTooltip') || '每次检测最多识别的人脸数量'}
                      >
                        <QuestionCircleOutlined className={styles.helpIcon} />
                      </Tooltip>
                    </span>
                  }
                >
                  <InputNumber
                    min={1}
                    max={32}
                    value={maxFaces}
                    onChange={setMaxFaces}
                    className={styles.minCountInput}
                  />
                </Form.Item>
              </>
            )}

            {/* 非人脸识别模式：显示目标类型选择 */}
            {conditionType !== 'face_recognition' && (
              <Form.Item
                label={
                  <span className={styles.sectionLabel}>
                    {t('detection.selectTargets') || '选择检测目标'}
                  </span>
                }
                name="targets"
                rules={[
                  {
                    required: true,
                    message: t('detection.pleaseSelectTarget') || '请至少选择一个检测目标',
                  },
                ]}
              >
                <Checkbox.Group
                  value={selectedTargets}
                  onChange={handleTargetChange}
                  className={styles.targetCheckboxGroup}
                >
                  <Row gutter={[16, 16]}>
                    {targetOptions
                      .map((option) => (
                        <Col key={option.value} span={8}>
                          <Checkbox value={option.value} className={styles.targetCheckbox}>
                            <div
                              className={styles.targetItem}
                              style={{ borderColor: option.color }}
                            >
                              <span className={styles.targetIcon}>{option.icon}</span>
                              <span className={styles.targetLabel}>{option.label}</span>
                            </div>
                          </Checkbox>
                        </Col>
                      ))}
                  </Row>
                </Checkbox.Group>
              </Form.Item>
            )}

            {/* 触发逻辑 - 仅非人脸识别模式显示 */}
            {conditionType !== 'face_recognition' && (
              <Form.Item
                label={
                  <span className={styles.sectionLabel}>
                    {t('detection.triggerLogic') || '触发逻辑'}
                  </span>
                }
                name="logic"
              >
                <Select
                  value={logicType}
                  onChange={setLogicType}
                  className={styles.logicSelect}
                  popupClassName={styles.logicDropdown}
                  optionLabelProp="label"
                >
                  {logicOptions.map((option) => (
                    <Option
                      key={option.value}
                      value={option.value}
                      label={option.label}
                    >
                      <div className={styles.logicOption}>
                        <div className={styles.logicLabel}>{option.label}</div>
                        <div className={styles.logicDesc}>{option.description}</div>
                      </div>
                    </Option>
                  ))}
                </Select>
              </Form.Item>
            )}

            {/* COUNT逻辑的最小数量 - 仅非人脸识别模式显示 */}
            {conditionType !== 'face_recognition' && logicType === 'count' && (
              <Form.Item
                label={
                  <span className={styles.sectionLabel}>
                    {t('detection.minCount') || '最小目标数量'}
                  </span>
                }
                name="min_count"
              >
                <InputNumber
                  min={1}
                  max={10}
                  value={minCount}
                  onChange={setMinCount}
                  className={styles.minCountInput}
                  addonAfter={t('detection.targets') || '个'}
                />
              </Form.Item>
            )}

            {/* 置信度阈值 - 仅非人脸识别模式显示 */}
            {conditionType !== 'face_recognition' && (
              <Form.Item
                label={
                  <span className={styles.sectionLabel}>
                    <BarChartOutlined /> {t('detection.confidenceThreshold') || '置信度阈值'}
                    <Tooltip
                      title={t('detection.confidenceTooltip') || '置信度越高，误报越少但可能漏检；置信度越低，检测越灵敏但可能产生误报'}
                    >
                      <QuestionCircleOutlined className={styles.helpIcon} />
                    </Tooltip>
                    <Tag color="blue" className={styles.valueTag}>
                      {confidenceThreshold} ({getConfidenceLabel(confidenceThreshold)})
                    </Tag>
                  </span>
                }
              >
                <Slider
                  min={0.1}
                  max={0.95}
                  step={0.05}
                  value={confidenceThreshold}
                  onChange={setConfidenceThreshold}
                  marks={{
                    0.1: t('detection.confidenceLow') || '宽松',
                    0.5: t('detection.confidenceMedium') || '标准',
                    0.95: t('detection.confidenceHigh') || '严格',
                  }}
                />
              </Form.Item>
            )}

            {/* 检测灵敏度 - 仅非人脸识别模式显示 */}
            {conditionType !== 'face_recognition' && (
              <Form.Item
                label={
                  <span className={styles.sectionLabel}>
                    <EyeOutlined /> {t('detection.sensitivity') || '检测灵敏度'}
                    <Tooltip
                      title={t('detection.sensitivityTooltip') || '灵敏度越高，检测响应越快（需要的连续帧数越少），但可能增加误报'}
                    >
                      <QuestionCircleOutlined className={styles.helpIcon} />
                    </Tooltip>
                    <Tag
                      color={sensitivity >= 8 ? 'red' : sensitivity >= 4 ? 'orange' : 'green'}
                      className={styles.valueTag}
                    >
                      {sensitivity} ({getSensitivityLabel(sensitivity)})
                    </Tag>
                  </span>
                }
              >
                <Slider
                  min={1}
                  max={10}
                  step={1}
                  value={sensitivity}
                  onChange={setSensitivity}
                  marks={{
                    1: t('detection.sensitivityLow') || '低',
                    5: t('detection.sensitivityMedium') || '中',
                    10: t('detection.sensitivityHigh') || '高',
                  }}
                />
              </Form.Item>
            )}

            {/* 冷却时间 */}
            <Form.Item
              label={
                <span className={styles.sectionLabel}>
                  <ClockCircleOutlined /> {t('detection.cooldown') || '触发冷却时间'}
                  <Tooltip
                    title={t('detection.cooldownTooltip') || '两次触发之间的最小间隔，防止过于频繁的触发'}
                  >
                    <QuestionCircleOutlined className={styles.helpIcon} />
                  </Tooltip>
                </span>
              }
            >
              <InputNumber
                min={5}
                max={3600}
                step={5}
                value={cooldownSeconds}
                onChange={setCooldownSeconds}
                className={styles.cooldownInput}
                addonAfter={t('detection.seconds') || '秒'}
              />
            </Form.Item>

            {/* 高级选项 - 仅非人脸识别模式显示（最小持续时长） */}
            {conditionType !== 'face_recognition' && (
              <div className={styles.advancedSection}>
                <div
                  className={styles.advancedToggle}
                  onClick={() => setShowAdvanced(!showAdvanced)}
                >
                  {showAdvanced ? '▼' : '▶'} {t('detection.advancedOptions') || '高级选项'}
                </div>

                {showAdvanced && (
                  <div className={styles.advancedContent}>
                    <Form.Item
                      label={
                        <span className={styles.sectionLabel}>
                          {t('detection.minDuration') || '最小持续时长'}
                          <Tooltip
                            title={t('detection.minDurationTooltip') || '目标必须持续被检测达到该时长才触发，可用于过滤短暂经过的目标'}
                          >
                            <QuestionCircleOutlined className={styles.helpIcon} />
                          </Tooltip>
                        </span>
                      }
                    >
                      <InputNumber
                        min={1}
                        max={300}
                        value={minDuration}
                        onChange={setMinDuration}
                        placeholder={t('detection.optional') || '可选'}
                        className={styles.durationInput}
                        addonAfter={t('detection.seconds') || '秒'}
                      />
                    </Form.Item>
                  </div>
                )}
              </div>
            )}

            {/* 配置摘要 */}
            <div className={styles.configSummary}>
              <div className={styles.summaryTitle}>
                {t('detection.configSummary') || '配置摘要'}
              </div>
              <div className={styles.summaryContent}>
                {conditionType === 'face_recognition' ? (
                  <>
                    {t('detection.whenDetected') || '当检测到'}
                    <strong>
                      {selectedFaceTarget === 'unknown'
                        ? (t('detection.unknownFace') || '未知')
                        : selectedFaceTarget}
                      {t('detection.targetFaceRecognition') || '人脸识别'}
                    </strong>
                    {t('detection.thenTrigger')}
                  </>
                ) : (
                  <>
                    {t('detection.whenDetected') || '当检测到'}
                    <strong>
                      {selectedTargets
                        .map((t) => targetOptions.find((o) => o.value === t)?.label)
                        .join('、')}
                    </strong>
                    {logicType === 'any' && t('detection.anyTrigger')}
                    {logicType === 'all' && t('detection.allTrigger')}
                    {logicType === 'count' && (
                      <>
                        {t('detection.countTrigger', { count: minCount })}
                      </>
                    )}
                    ，
                    {t('detection.withConfidence', { threshold: confidenceThreshold })}
                    {minDuration && t('detection.withDuration', { duration: minDuration })}
                    {t('detection.thenTrigger')}
                  </>
                )}
              </div>
            </div>
          </div>
      </Form>
    </Card>
  );
};

export default DetectionConditionForm;
