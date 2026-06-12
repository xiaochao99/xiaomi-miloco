import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Select, Switch, Button, Input, message, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import {
  VideoCameraOutlined,
  SaveOutlined,
  DeleteOutlined,
  PlusOutlined,
  SettingOutlined,
  ClockCircleOutlined,
  CloudServerOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons';
import { getCameraList, getRecordingConfigAll, getRecordingConfig, saveRecordingConfig, getRecordingStorage } from '@/api';
import styles from './index.module.less';

const ALL_DAYS = [0, 1, 2, 3, 4, 5, 6];
const WEEKDAYS = [0, 1, 2, 3, 4];
const WEEKEND = [5, 6];

const DAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

const RecordingConfig = () => {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const [cameras, setCameras] = useState([]);
  const [selectedCamera, setSelectedCamera] = useState(null);
  const [configs, setConfigs] = useState({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [storageStats, setStorageStats] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);

  const config = useMemo(() => {
    if (!selectedCamera) return null;
    return configs[selectedCamera] || null;
  }, [configs, selectedCamera]);

  const fetchCameras = useCallback(async () => {
    try {
      const res = await getCameraList();
      if (res && res.code === 0) {
        setCameras(res.data || []);
      }
    } catch (error) {
      console.error('Failed to fetch cameras:', error);
    }
  }, []);

  const fetchAllConfigs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getRecordingConfigAll();
      if (res && res.code === 0 && Array.isArray(res.data)) {
        const configMap = {};
        res.data.forEach((c) => {
          configMap[c.camera_id] = {
            enabled: c.enabled || false,
            recording_mode: c.mode || c.recording_mode || 'continuous',
            recording_plans: (c.schedule_periods || c.recording_plans || []).map((p) => ({
              start_time: p.start_time,
              end_time: p.end_time,
              days_of_week: p.days_of_week || null,
            })),
            retention_days: c.retention_days || 7,
            segment_duration: c.segment_duration || 300,
            motion_buffer_seconds: c.motion_buffer_seconds ?? 25,
            person_buffer_seconds: c.person_buffer_seconds ?? 30,
            motion_threshold: c.motion_threshold ?? 5,
            motion_check_interval: c.motion_check_interval ?? 1.0,
          };
        });
        setConfigs(configMap);
      }
    } catch (error) {
      console.error('Failed to fetch recording configs:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchCameraConfig = useCallback(async (cameraId) => {
    setLoading(true);
    try {
      const res = await getRecordingConfig(cameraId);
      if (res && res.code === 0 && res.data) {
        const d = res.data;
        setConfigs((prev) => ({
          ...prev,
          [cameraId]: {
            enabled: d.enabled || false,
            recording_mode: d.mode || d.recording_mode || 'continuous',
            recording_plans: (d.schedule_periods || d.recording_plans || []).map((p) => ({
              start_time: p.start_time,
              end_time: p.end_time,
              days_of_week: p.days_of_week || null,
            })),
            retention_days: d.retention_days || 7,
            segment_duration: d.segment_duration || 300,
            motion_buffer_seconds: d.motion_buffer_seconds ?? 25,
            person_buffer_seconds: d.person_buffer_seconds ?? 30,
            motion_threshold: d.motion_threshold ?? 5,
            motion_check_interval: d.motion_check_interval ?? 1.0,
          },
        }));
      } else {
        setConfigs((prev) => ({
          ...prev,
          [cameraId]: {
            enabled: false,
            recording_mode: 'continuous',
            recording_plans: [],
            retention_days: 7,
            segment_duration: 300,
            motion_buffer_seconds: 25,
            person_buffer_seconds: 30,
            motion_threshold: 5,
            motion_check_interval: 1.0,
          },
        }));
      }
    } catch (error) {
      console.error('Failed to fetch recording config:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchStorageStats = useCallback(async () => {
    try {
      const res = await getRecordingStorage();
      if (res && res.code === 0) {
        setStorageStats(res.data);
      }
    } catch (error) {
      console.error('Failed to fetch storage stats:', error);
    }
  }, []);

  useEffect(() => {
    fetchCameras();
    fetchAllConfigs();
    fetchStorageStats();
  }, [fetchCameras, fetchAllConfigs, fetchStorageStats]);

  // Pre-select camera from query parameter
  useEffect(() => {
    const cameraParam = searchParams.get('camera');
    if (cameraParam && cameras.length > 0) {
      const found = cameras.find(c => c.did === cameraParam);
      if (found) {
        setSelectedCamera(cameraParam);
      }
    }
  }, [searchParams, cameras]);

  useEffect(() => {
    if (selectedCamera && !configs[selectedCamera]) {
      fetchCameraConfig(selectedCamera);
    }
  }, [selectedCamera, configs, fetchCameraConfig]);

  const updateConfig = useCallback((field, value) => {
    setConfigs((prev) => ({
      ...prev,
      [selectedCamera]: {
        ...prev[selectedCamera],
        [field]: value,
      },
    }));
    setHasChanges(true);
  }, [selectedCamera]);

  const updatePlan = useCallback((index, field, value) => {
    setConfigs((prev) => {
      const current = prev[selectedCamera];
      const plans = [...current.recording_plans];
      plans[index] = { ...plans[index], [field]: value };
      return { ...prev, [selectedCamera]: { ...current, recording_plans: plans } };
    });
    setHasChanges(true);
  }, [selectedCamera]);

  const addPlan = useCallback(() => {
    setConfigs((prev) => {
      const current = prev[selectedCamera];
      return {
        ...prev,
        [selectedCamera]: {
          ...current,
          recording_plans: [
            ...current.recording_plans,
            { start_time: '09:00', end_time: '18:00', days_of_week: null },
          ],
        },
      };
    });
    setHasChanges(true);
  }, [selectedCamera]);

  const removePlan = useCallback((index) => {
    setConfigs((prev) => {
      const current = prev[selectedCamera];
      const plans = current.recording_plans.filter((_, i) => i !== index);
      return { ...prev, [selectedCamera]: { ...current, recording_plans: plans } };
    });
    setHasChanges(true);
  }, [selectedCamera]);

  const togglePlanDay = useCallback((planIndex, day) => {
    setConfigs((prev) => {
      const current = prev[selectedCamera];
      const plans = [...current.recording_plans];
      const plan = { ...plans[planIndex] };
      let days = plan.days_of_week ? [...plan.days_of_week] : [...ALL_DAYS];
      if (days.includes(day)) {
        days = days.filter((d) => d !== day);
      } else {
        days.push(day);
        days.sort();
      }
      plan.days_of_week = days.length === 7 ? null : days;
      plans[planIndex] = plan;
      return { ...prev, [selectedCamera]: { ...current, recording_plans: plans } };
    });
    setHasChanges(true);
  }, [selectedCamera]);

  const setQuickDays = useCallback((planIndex, days) => {
    setConfigs((prev) => {
      const current = prev[selectedCamera];
      const plans = [...current.recording_plans];
      const plan = { ...plans[planIndex] };
      plan.days_of_week = days.length === 7 ? null : days;
      plans[planIndex] = plan;
      return { ...prev, [selectedCamera]: { ...current, recording_plans: plans } };
    });
    setHasChanges(true);
  }, [selectedCamera]);

  const handleSave = async () => {
    if (!selectedCamera || !config) return;
    setSaving(true);
    try {
      const payload = {
        enabled: config.enabled,
        recording_mode: config.recording_mode,
        recording_plans: config.recording_plans.map((p) => ({
          start_time: p.start_time,
          end_time: p.end_time,
          days_of_week: p.days_of_week,
        })),
        retention_days: config.retention_days,
        segment_duration: config.segment_duration,
        motion_buffer_seconds: config.motion_buffer_seconds,
        person_buffer_seconds: config.person_buffer_seconds,
        motion_threshold: config.motion_threshold,
        motion_check_interval: config.motion_check_interval,
      };
      const res = await saveRecordingConfig(selectedCamera, payload);
      if (res && res.code === 0) {
        message.success(t('recording.config.configSaved'));
        setHasChanges(false);
        fetchStorageStats();
      } else {
        message.error(res?.message || t('recording.config.configSaveFailed'));
      }
    } catch (error) {
      console.error('Failed to save config:', error);
      message.error(t('recording.config.configSaveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const getCameraStatusClass = useCallback((cameraDid) => {
    const c = configs[cameraDid];
    if (!c) return styles.statusDisabled;
    if (c.enabled) return styles.statusActive;
    return styles.statusEnabled;
  }, [configs]);

  const formatFileSize = (bytes) => {
    if (!bytes) return '0 B';
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${sizes[i]}`;
  };

  const getQuickSelectType = (days) => {
    if (!days) return 'all';
    const sorted = [...days].sort();
    if (sorted.length === 7) return 'all';
    if (sorted.length === 5 && sorted.every((d, i) => d === WEEKDAYS[i])) return 'weekdays';
    if (sorted.length === 2 && sorted.every((d, i) => d === WEEKEND[i])) return 'weekend';
    return 'custom';
  };

  return (
    <div className={styles.recordingConfigContainer}>
      <div className={styles.cameraSidebar}>
        <div className={styles.sidebarHeader}>
          <div className={styles.sidebarTitle}>
            <VideoCameraOutlined />
            {t('recording.config.cameras')}
            <span className={styles.sidebarCount}>({cameras.length})</span>
          </div>
        </div>
        <div className={styles.cameraList}>
          {cameras.map((camera) => (
            <div
              key={camera.did}
              className={`${styles.cameraItem} ${selectedCamera === camera.did ? styles.cameraItemActive : ''}`}
              onClick={() => setSelectedCamera(camera.did)}
            >
              <div className={styles.cameraIcon}>
                <VideoCameraOutlined />
              </div>
              <div className={styles.cameraInfo}>
                <div className={styles.cameraName}>{camera.name}</div>
                <div className={styles.cameraId}>{camera.did}</div>
              </div>
              <div className={`${styles.cameraStatus} ${getCameraStatusClass(camera.did)}`} />
            </div>
          ))}
        </div>
      </div>

      <div className={styles.mainContent}>
        {!selectedCamera ? (
          <div className={styles.emptyState}>
            <VideoCameraOutlined className={styles.emptyIcon} />
            <div className={styles.emptyText}>{t('recording.config.selectCameraHint')}</div>
          </div>
        ) : loading && !config ? (
          <div className={styles.emptyState}>
            <div className={styles.emptyText}>{t('recording.common.loading')}...</div>
          </div>
        ) : config ? (
          <div className={styles.configWrapper}>
            <div className={styles.cameraHeader}>
              <div className={styles.cameraHeaderLeft}>
                <div className={styles.cameraHeaderIcon}>
                  <VideoCameraOutlined />
                </div>
                <div className={styles.cameraHeaderInfo}>
                  <div className={styles.cameraHeaderName}>
                    {cameras.find((c) => c.did === selectedCamera)?.name || selectedCamera}
                  </div>
                  <div className={styles.cameraHeaderId}>{selectedCamera}</div>
                </div>
              </div>
              <div className={styles.cameraHeaderRight}>
                <div
                  className={`${styles.enableSwitch} ${config.enabled ? styles.enableSwitchOn : ''}`}
                  onClick={() => updateConfig('enabled', !config.enabled)}
                >
                  <Switch
                    size="small"
                    checked={config.enabled}
                    onChange={(checked) => updateConfig('enabled', checked)}
                    onClick={(e) => e.stopPropagation()}
                  />
                  <span className={styles.switchLabel}>
                    {config.enabled ? t('recording.config.enabled') : t('recording.config.disabled')}
                  </span>
                </div>
              </div>
            </div>

            <div className={styles.section}>
              <div className={styles.sectionTitle}>
                <SettingOutlined className={styles.sectionIcon} />
                {t('recording.config.recordingSettings')}
              </div>
              <div className={styles.settingsGrid}>
                <div className={styles.settingItem}>
                  <div className={styles.settingLabel}>{t('recording.config.recordingMode')}</div>
                  <Select
                    value={config.recording_mode}
                    onChange={(value) => updateConfig('recording_mode', value)}
                    style={{ width: '100%' }}
                    disabled={loading}
                    options={[
                      { value: 'continuous', label: t('recording.config.modeContinuous') },
                      { value: 'person', label: t('recording.config.modePerson') },
                      { value: 'motion', label: t('recording.config.modeMotion') },
                    ]}
                  />
                </div>

                <div className={styles.settingItem}>
                  <div className={styles.settingLabel}>
                    {t('recording.config.retentionDays')}
                    <Tooltip title={t('recording.config.retentionDaysTooltip')}>
                      <QuestionCircleOutlined className={styles.settingTooltip} />
                    </Tooltip>
                  </div>
                  <Input
                    type="number"
                    min={1}
                    max={365}
                    value={config.retention_days}
                    onChange={(e) => updateConfig('retention_days', parseInt(e.target.value) || 7)}
                    disabled={loading}
                  />
                </div>

                <div className={`${styles.settingItem} ${styles.settingFullWidth}`}>
                  <div className={styles.settingLabel}>
                    {t('recording.config.segmentDuration')}
                    <Tooltip title={t('recording.config.segmentDurationTooltip')}>
                      <QuestionCircleOutlined className={styles.settingTooltip} />
                    </Tooltip>
                  </div>
                  <Input
                    type="number"
                    min={60}
                    max={3600}
                    step={60}
                    value={config.segment_duration}
                    onChange={(e) => updateConfig('segment_duration', parseInt(e.target.value) || 300)}
                    style={{ width: 200 }}
                    disabled={loading}
                  />
                </div>
              </div>
            </div>

            {config.recording_mode === 'motion' && (
              <div className={styles.section}>
                <div className={styles.sectionTitle}>
                  <SettingOutlined className={styles.sectionIcon} />
                  {t('recording.config.motionDetection')}
                </div>
                <div className={styles.settingsGrid}>
                  <div className={styles.settingItem}>
                    <div className={styles.settingLabel}>
                      {t('recording.config.motionBufferSeconds')}
                      <Tooltip title={t('recording.config.motionBufferSecondsTooltip')}>
                        <QuestionCircleOutlined className={styles.settingTooltip} />
                      </Tooltip>
                    </div>
                    <Input
                      type="number"
                      min={5}
                      max={300}
                      value={config.motion_buffer_seconds}
                      onChange={(e) => updateConfig('motion_buffer_seconds', parseFloat(e.target.value) || 25)}
                      disabled={loading}
                    />
                  </div>

                  <div className={styles.settingItem}>
                    <div className={styles.settingLabel}>
                      {t('recording.config.motionThreshold')}
                      <Tooltip title={t('recording.config.motionThresholdTooltip')}>
                        <QuestionCircleOutlined className={styles.settingTooltip} />
                      </Tooltip>
                    </div>
                    <Input
                      type="number"
                      min={1}
                      max={20}
                      value={config.motion_threshold}
                      onChange={(e) => updateConfig('motion_threshold', parseInt(e.target.value) || 5)}
                      disabled={loading}
                    />
                  </div>

                  <div className={styles.settingItem}>
                    <div className={styles.settingLabel}>
                      {t('recording.config.motionCheckInterval')}
                      <Tooltip title={t('recording.config.motionCheckIntervalTooltip')}>
                        <QuestionCircleOutlined className={styles.settingTooltip} />
                      </Tooltip>
                    </div>
                    <Input
                      type="number"
                      min={0.5}
                      max={10}
                      step={0.5}
                      value={config.motion_check_interval}
                      onChange={(e) => updateConfig('motion_check_interval', parseFloat(e.target.value) || 1.0)}
                      disabled={loading}
                    />
                  </div>
                </div>
              </div>
            )}

            {config.recording_mode === 'person' && (
              <div className={styles.section}>
                <div className={styles.sectionTitle}>
                  <SettingOutlined className={styles.sectionIcon} />
                  {t('recording.config.personDetection')}
                </div>
                <div className={styles.settingsGrid}>
                  <div className={styles.settingItem}>
                    <div className={styles.settingLabel}>
                      {t('recording.config.personBufferSeconds')}
                      <Tooltip title={t('recording.config.personBufferSecondsTooltip')}>
                        <QuestionCircleOutlined className={styles.settingTooltip} />
                      </Tooltip>
                    </div>
                    <Input
                      type="number"
                      min={5}
                      max={300}
                      value={config.person_buffer_seconds}
                      onChange={(e) => updateConfig('person_buffer_seconds', parseFloat(e.target.value) || 30)}
                      disabled={loading}
                    />
                  </div>
                </div>
              </div>
            )}

            <div className={styles.section}>
              <div className={styles.sectionTitle}>
                <ClockCircleOutlined className={styles.sectionIcon} />
                {t('recording.config.scheduleSettings')}
              </div>
              <div className={styles.weekSchedule}>
                {config.recording_plans.length === 0 ? (
                  <div className={styles.emptyPlan}>{t('recording.config.noPlanHint')}</div>
                ) : (
                  config.recording_plans.map((plan, index) => {
                    const activeDays = plan.days_of_week || ALL_DAYS;
                    const quickType = getQuickSelectType(plan.days_of_week);
                    return (
                      <div key={index} className={styles.planCard}>
                        <div className={styles.planCardHeader}>
                          <div className={styles.planCardHeaderLeft}>
                            <span className={styles.planNumber}>#{index + 1}</span>
                            <div className={styles.planTimeRange}>
                              <input
                                type="time"
                                value={plan.start_time}
                                onChange={(e) => updatePlan(index, 'start_time', e.target.value)}
                                disabled={loading}
                                style={{
                                  padding: '4px 8px',
                                  borderRadius: 6,
                                  border: '1px solid var(--border-color-240)',
                                  fontSize: 13,
                                  fontFamily: 'inherit',
                                  background: 'var(--bg-color-container)',
                                  color: 'var(--text-color-31)',
                                }}
                              />
                              <span className={styles.planTimeSeparator}>—</span>
                              <input
                                type="time"
                                value={plan.end_time}
                                onChange={(e) => updatePlan(index, 'end_time', e.target.value)}
                                disabled={loading}
                                style={{
                                  padding: '4px 8px',
                                  borderRadius: 6,
                                  border: '1px solid var(--border-color-240)',
                                  fontSize: 13,
                                  fontFamily: 'inherit',
                                  background: 'var(--bg-color-container)',
                                  color: 'var(--text-color-31)',
                                }}
                              />
                            </div>
                          </div>
                          <Button
                            type="text"
                            danger
                            icon={<DeleteOutlined />}
                            size="small"
                            onClick={() => removePlan(index)}
                            disabled={loading}
                          />
                        </div>

                        <div className={styles.dayQuickSelect}>
                          {[
                            { key: 'all', label: t('recording.config.allDays'), days: [...ALL_DAYS] },
                            { key: 'weekdays', label: t('recording.config.weekdays'), days: [...WEEKDAYS] },
                            { key: 'weekend', label: t('recording.config.weekend'), days: [...WEEKEND] },
                          ].map((opt) => (
                            <div
                              key={opt.key}
                              className={`${styles.quickSelectBtn} ${quickType === opt.key ? styles.quickSelectBtnActive : ''}`}
                              onClick={() => setQuickDays(index, opt.days)}
                            >
                              {opt.label}
                            </div>
                          ))}
                        </div>

                        <div className={styles.daySelector}>
                          {DAY_KEYS.map((dayKey, dayIndex) => {
                            const isActive = activeDays.includes(dayIndex);
                            return (
                              <div
                                key={dayKey}
                                className={`${styles.dayChip} ${isActive ? styles.dayChipActive : ''}`}
                                onClick={() => togglePlanDay(index, dayIndex)}
                              >
                                {t(`recording.config.${dayKey}`)}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })
                )}
                <Button
                  type="dashed"
                  icon={<PlusOutlined />}
                  onClick={addPlan}
                  className={styles.addPlanButton}
                  disabled={loading}
                >
                  {t('recording.config.addPlan')}
                </Button>
              </div>
            </div>

            {storageStats && (
              <div className={`${styles.section} ${styles.storageSection}`}>
                <div className={styles.sectionTitle}>
                  <CloudServerOutlined className={styles.sectionIcon} />
                  {t('recording.config.storageInfo')}
                </div>
                <div className={styles.storageGrid}>
                  <div className={styles.storageCard}>
                    <div className={styles.storageValue}>{formatFileSize(storageStats.total_size_bytes || 0)}</div>
                    <div className={styles.storageLabel}>{t('recording.config.usedSpace')}</div>
                  </div>
                  <div className={styles.storageCard}>
                    <div className={styles.storageValue}>{storageStats.total_segments || 0}</div>
                    <div className={styles.storageLabel}>{t('recording.config.segmentCount')}</div>
                  </div>
                  <div className={styles.storageCard}>
                    <div className={styles.storageValue}>{storageStats.per_camera?.length || 0}</div>
                    <div className={styles.storageLabel}>{t('recording.config.camera')}</div>
                  </div>
                </div>
              </div>
            )}

            <div className={styles.saveBar}>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={handleSave}
                loading={saving}
                disabled={!hasChanges}
                size="large"
              >
                {t('recording.config.saveConfig')}
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default RecordingConfig;
