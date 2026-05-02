import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Switch, Input, Select, Button, Table, Tag, message, Spin } from 'antd';
import {
  SyncOutlined,
  ExperimentOutlined,
  SafetyOutlined,
  ThunderboltOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  DatabaseOutlined,
  RobotOutlined,
  CloudOutlined,
  HomeOutlined,
  BulbOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import Header from '@/components/Header';
import {
  getHabitStats,
  getHabitPatterns,
  getHabitPredictions,
  triggerHabitTraining,
  enableHabitCollector,
  disableHabitCollector,
  enableHabitEngine,
  disableHabitEngine,
  updateHabitConfig,
  getHabitContext,
  getHabitContextEntities,
  saveHabitContextEntities,
  getHabitAllHaEntities,
} from '@/api';
import styles from './index.module.less';

const { Option } = Select;

const HabitLearning = () => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [patterns, setPatterns] = useState([]);
  const [predictions, setPredictions] = useState([]);
  const [training, setTraining] = useState(false);
  const [collectorConfig, setCollectorConfig] = useState({
    flush_interval: 5,
  });
  const [learnerConfig, setLearnerConfig] = useState({
    learn_interval: 3600,
    min_occurrences: 3,
    time_bucket_minutes: 30,
  });
  const [engineConfig, setEngineConfig] = useState({
    enabled: false,
    cycle_interval: 60,
    confidence_threshold: 0.65,
    risk_level_limit: 'HIGH',
  });
  const [envContext, setEnvContext] = useState(null);
  const [contextEntities, setContextEntities] = useState({});
  const [entitySaving, setEntitySaving] = useState(false);
  const [allHaEntities, setAllHaEntities] = useState([]);

  const entitySelectOptions = useMemo(() => {
    const options = [];
    const seen = new Set();
    allHaEntities.forEach((entity) => {
      const entityId = entity.entity_id;
      if (!entityId || seen.has(entityId)) return;
      seen.add(entityId);
      const friendlyName = entity.friendly_name || '';
      const domain = entity.domain || entityId.split('.')[0];
      const label = friendlyName ? `${friendlyName} (${entityId})` : entityId;
      options.push({ label, value: entityId, domain });
    });
    options.sort((a, b) => a.label.localeCompare(b.label));
    return options;
  }, [allHaEntities]);

  const fetchStats = useCallback(async () => {
    try {
      const res = await getHabitStats();
      if (res && res.success !== false) {
        const data = res.data || res.stats || res;
        const statsData = data.stats || data;
        setStats(statsData);
        if (statsData.config) {
          if (statsData.config.collector) {
            setCollectorConfig({
              flush_interval: statsData.config.collector.flush_interval ?? 5,
            });
          }
          if (statsData.config.learner) {
            setLearnerConfig({
              learn_interval: statsData.config.learner.learn_interval ?? 3600,
              min_occurrences: statsData.config.learner.min_occurrences ?? 3,
              time_bucket_minutes: statsData.config.learner.time_bucket_minutes ?? 30,
            });
          }
          if (statsData.config.decision_engine) {
            setEngineConfig({
              enabled: statsData.config.decision_engine.enabled ?? false,
              cycle_interval: statsData.config.decision_engine.cycle_interval ?? 60,
              confidence_threshold: statsData.config.decision_engine.confidence_threshold ?? 0.65,
              risk_level_limit: statsData.config.decision_engine.risk_level_limit ?? 'HIGH',
            });
          }
        }
      }
    } catch (error) {
      console.error('Failed to fetch habit stats:', error);
    }
  }, []);

  const fetchContext = useCallback(async () => {
    try {
      const res = await getHabitContext();
      if (res) {
        setEnvContext(res);
      }
    } catch (error) {
      console.error('Failed to fetch context:', error);
    }
  }, []);

  const fetchContextEntities = useCallback(async () => {
    try {
      const res = await getHabitContextEntities();
      if (res && res.configured) {
        setContextEntities(res.configured);
      }
    } catch (error) {
      console.error('Failed to fetch context entities:', error);
    }
  }, []);

  const fetchAllHaEntities = useCallback(async () => {
    try {
      const res = await getHabitAllHaEntities();
      if (Array.isArray(res)) {
        setAllHaEntities(res);
      } else if (res && res.code === 0) {
        setAllHaEntities(res.data || []);
      }
    } catch (error) {
      console.error('Failed to fetch HA entities:', error);
    }
  }, []);

  const handleSaveContextEntities = useCallback(async () => {
    setEntitySaving(true);
    try {
      const res = await saveHabitContextEntities(contextEntities);
      if (res && res.success) {
        message.success(t('habitLearning.entitySaved', '实体配置已保存'));
        fetchContext();
      } else {
        message.error(t('habitLearning.entitySaveFailed', '保存失败'));
      }
    } catch (error) {
      message.error(t('habitLearning.entitySaveFailed', '保存失败'));
    } finally {
      setEntitySaving(false);
    }
  }, [contextEntities, fetchContext, t]);

  const updateContextEntity = useCallback((key, value) => {
    setContextEntities((prev) => {
      const next = { ...prev };
      if (value) {
        next[key] = value;
      } else {
        delete next[key];
      }
      return next;
    });
  }, []);

  const fetchPatterns = useCallback(async () => {
    try {
      const res = await getHabitPatterns({ min_confidence: 0.3, limit: 50 });
      if (res && res.success !== false) {
        const data = res.data || res;
        setPatterns(data.patterns || []);
      }
    } catch (error) {
      console.error('Failed to fetch patterns:', error);
    }
  }, []);

  const fetchPredictions = useCallback(async () => {
    try {
      const res = await getHabitPredictions();
      if (res && res.success !== false) {
        const data = res.data || res;
        setPredictions(data.predictions || []);
      }
    } catch (error) {
      console.error('Failed to fetch predictions:', error);
    }
  }, []);

  useEffect(() => {
    const loadAll = async () => {
      setLoading(true);
      await Promise.all([fetchStats(), fetchPatterns(), fetchPredictions(), fetchContext(), fetchContextEntities(), fetchAllHaEntities()]);
      setLoading(false);
    };
    loadAll();
  }, [fetchStats, fetchPatterns, fetchPredictions, fetchContext, fetchContextEntities, fetchAllHaEntities]);

  const handleCollectorToggle = async (checked) => {
    try {
      let res;
      if (checked) {
        res = await enableHabitCollector();
      } else {
        res = await disableHabitCollector();
      }
      const msg = res?.data?.message || res?.message || '';
      if (checked) {
        message.success(t('habitLearning.collectorEnabled'));
      } else {
        message.success(t('habitLearning.collectorDisabled'));
      }
      await fetchStats();
    } catch (error) {
      console.error('Failed to toggle collector:', error);
      message.error(t('habitLearning.configSaveFailed'));
    }
  };

  const handleEngineToggle = async (checked) => {
    try {
      let res;
      if (checked) {
        res = await enableHabitEngine();
      } else {
        res = await disableHabitEngine();
      }
      const msg = res?.data?.message || res?.message || '';
      if (checked) {
        message.success(msg || t('habitLearning.engineRunning'));
      } else {
        message.success(msg || t('habitLearning.engineStopped'));
      }
      await fetchStats();
    } catch (error) {
      console.error('Failed to toggle engine:', error);
      message.error(t('habitLearning.configSaveFailed'));
    }
  };

  const handleConfigSave = async (section, key, value) => {
    try {
      const res = await updateHabitConfig({ section, key, value: String(value) });
      if (res && res.success !== false) {
        message.success(t('habitLearning.configSaved'));
        await fetchStats();
      } else {
        message.error(t('habitLearning.configSaveFailed'));
      }
    } catch (error) {
      console.error('Failed to save config:', error);
      message.error(t('habitLearning.configSaveFailed'));
    }
  };

  const handleTrain = async () => {
    setTraining(true);
    try {
      const res = await triggerHabitTraining();
      if (res && res.success !== false) {
        message.success(t('habitLearning.trainSuccess'));
        await Promise.all([fetchStats(), fetchPatterns(), fetchPredictions()]);
      } else {
        message.error(t('habitLearning.trainFailed'));
      }
    } catch (error) {
      console.error('Training failed:', error);
      message.error(t('habitLearning.trainFailed'));
    } finally {
      setTraining(false);
    }
  };

  const collectorStats = stats?.collector || {};
  const learnerStats = stats?.learner || {};
  const engineStats = stats?.engine || {};
  const eventStats = stats?.events || {};
  const isCollectorRunning = !!collectorStats.enabled;
  const isEngineRunning = !!engineStats.running;

  const riskOptions = [
    { value: 'LOW', label: t('habitLearning.riskLevelLow') },
    { value: 'MEDIUM', label: t('habitLearning.riskLevelMedium') },
    { value: 'HIGH', label: t('habitLearning.riskLevelHigh') },
    { value: 'CRITICAL', label: t('habitLearning.riskLevelCritical') },
  ];

  const patternColumns = [
    {
      title: t('habitLearning.entityId'),
      dataIndex: 'entity_name',
      key: 'entity_name',
      ellipsis: true,
      width: 200,
      render: (name, record) => (
        <span title={record.entity_id}>{name || record.entity_id}</span>
      ),
    },
    {
      title: t('habitLearning.patternType'),
      dataIndex: 'pattern_type',
      key: 'pattern_type',
      width: 200,
      ellipsis: true,
      render: (type) => {
        if (!type) return '-';
        const colorMap = {
          time_based: 'blue',
          state_based: 'green',
          sequence: 'orange',
          co_occurrence: 'purple',
          periodic: 'cyan',
          context_based: 'magenta',
        };
        const categoryColors = {
          TIME_BASED: 'blue',
          STATE_BASED: 'green',
          CONTEXTUAL: 'purple',
          UNKNOWN: 'default',
        };
        let displayType = type;
        let color = 'default';
        
        if (colorMap[type]) {
          color = colorMap[type];
        } else if (categoryColors[type]) {
          color = categoryColors[type];
        } else if (type.includes(':')) {
          const parts = type.split(':');
          if (parts.length === 2) {
            displayType = parts[1];
          }
          color = 'default';
        }
        
        return <Tag color={color}>{displayType}</Tag>;
      },
    },
    {
      title: t('habitLearning.confidence'),
      dataIndex: 'confidence',
      key: 'confidence',
      width: 100,
      render: (val) => {
        const percent = ((val || 0) * 100).toFixed(1);
        const color = val >= 0.7 ? 'green' : val >= 0.5 ? 'orange' : 'red';
        return <Tag color={color}>{percent}%</Tag>;
      },
      sorter: (a, b) => (a.confidence || 0) - (b.confidence || 0),
    },
    {
      title: t('habitLearning.occurrenceCount'),
      dataIndex: 'occurrence_count',
      key: 'occurrence_count',
      width: 100,
      sorter: (a, b) => (a.occurrence_count || 0) - (b.occurrence_count || 0),
    },
    {
      title: t('habitLearning.lastOccurrence'),
      dataIndex: 'last_occurrence',
      key: 'last_occurrence',
      width: 180,
      render: (val) => {
        if (!val) return t('habitLearning.never');
        let timestamp = val;
        if (typeof val === 'string' && !isNaN(Date.parse(val))) {
          return new Date(val).toLocaleString();
        }
        if (typeof val === 'number') {
          if (val < 1e12) {
            timestamp = val * 1000;
          }
          const date = new Date(timestamp);
          if (date.getFullYear() > 1970) {
            return date.toLocaleString();
          }
        }
        return t('habitLearning.never');
      },
    },
  ];

  const predictionColumns = [
    {
      title: t('habitLearning.entityId'),
      dataIndex: 'entity_name',
      key: 'entity_name',
      ellipsis: true,
      width: 200,
      render: (name, record) => (
        <span title={record.entity_id}>{name || record.entity_id}</span>
      ),
    },
    {
      title: t('habitLearning.predictedAction'),
      dataIndex: 'predicted_action',
      key: 'predicted_action',
      width: 120,
    },
    {
      title: t('habitLearning.predictedTime'),
      dataIndex: 'predicted_time',
      key: 'predicted_time',
      width: 180,
      render: (val) => (val ? new Date(val).toLocaleString() : '-'),
    },
    {
      title: t('habitLearning.confidence'),
      dataIndex: 'confidence',
      key: 'confidence',
      width: 100,
      render: (val) => {
        const percent = ((val || 0) * 100).toFixed(1);
        const color = val >= 0.7 ? 'green' : val >= 0.5 ? 'orange' : 'red';
        return <Tag color={color}>{percent}%</Tag>;
      },
    },
    {
      title: t('habitLearning.reasoning'),
      dataIndex: 'reasoning',
      key: 'reasoning',
      ellipsis: true,
    },
  ];

  return (
    <div className={styles.habitContainer}>
      <div className={styles.habitContent}>
        <Header title={t('habitLearning.title')} />

        <Spin spinning={loading}>
          {/* System Status */}
          <Card className={styles.habitCard} contentClassName={styles.habitCardContent}>
            <div className={styles.habitCardTitle}>
              {t('habitLearning.systemStatus')}
              <Tag color={stats?.enabled ? 'success' : 'default'}>
                {stats?.enabled ? t('habitLearning.enabled') : t('habitLearning.disabled')}
              </Tag>
            </div>
            <div className={styles.statusGrid}>
              <div className={styles.statusItem}>
                <span className={styles.statusLabel}>{t('habitLearning.totalCollected')}</span>
                <span className={styles.statusValue}>{collectorStats.total_collected ?? 0}</span>
              </div>
              <div className={styles.statusItem}>
                <span className={styles.statusLabel}>{t('habitLearning.totalFlushed')}</span>
                <span className={styles.statusValue}>{collectorStats.total_flushed ?? 0}</span>
              </div>
              <div className={styles.statusItem}>
                <span className={styles.statusLabel}>{t('habitLearning.noiseFiltered')}</span>
                <span className={styles.statusValue}>{collectorStats.noise_filtered ?? 0}</span>
              </div>
              <div className={styles.statusItem}>
                <span className={styles.statusLabel}>{t('habitLearning.patternCount')}</span>
                <span className={styles.statusValue}>{eventStats.total_patterns ?? learnerStats.pattern_count ?? 0}</span>
              </div>
              <div className={styles.statusItem}>
                <span className={styles.statusLabel}>{t('habitLearning.totalEvents')}</span>
                <span className={styles.statusValue}>{eventStats.total_events ?? 0}</span>
              </div>
              <div className={styles.statusItem}>
                <span className={styles.statusLabel}>{t('habitLearning.actionsExecuted')}</span>
                <span className={styles.statusValue}>{engineStats.actions_executed ?? 0}</span>
              </div>
            </div>
          </Card>

          {/* Environment Context */}
          {envContext && (
            <Card className={styles.habitCard} contentClassName={styles.habitCardContent}>
              <div className={styles.habitCardTitle}>
                <CloudOutlined /> {t('habitLearning.environmentContext', '环境上下文')}
                <Button size="small" onClick={fetchContext} style={{ marginLeft: 8 }}>
                  <SyncOutlined /> {t('habitLearning.refresh', '刷新')}
                </Button>
              </div>
              <div className={styles.statusGrid}>
                <div className={styles.statusItem}>
                  <span className={styles.statusLabel}>🌡️ {t('habitLearning.indoorTemp', '室内温度')}</span>
                  <span className={styles.statusValue}>{envContext.temperature != null ? `${envContext.temperature}°C` : '-'}</span>
                </div>
                <div className={styles.statusItem}>
                  <span className={styles.statusLabel}>🌡️ {t('habitLearning.outdoorTemp', '室外温度')}</span>
                  <span className={styles.statusValue}>{envContext.outdoor_temperature != null ? `${envContext.outdoor_temperature}°C` : '-'}</span>
                </div>
                <div className={styles.statusItem}>
                  <span className={styles.statusLabel}>💧 {t('habitLearning.humidity', '湿度')}</span>
                  <span className={styles.statusValue}>{envContext.humidity != null ? `${envContext.humidity}%` : '-'}</span>
                </div>
                <div className={styles.statusItem}>
                  <span className={styles.statusLabel}><BulbOutlined /> {t('habitLearning.lightLevel', '光照')}</span>
                  <span className={styles.statusValue}>{envContext.light_level != null ? envContext.light_level : '-'}</span>
                </div>
                <div className={styles.statusItem}>
                  <span className={styles.statusLabel}><HomeOutlined /> {t('habitLearning.isHome', '有人在家')}</span>
                  <span className={styles.statusValue}>
                    <Tag color={envContext.is_home ? 'success' : 'default'}>
                      {envContext.is_home ? t('habitLearning.yes', '是') : t('habitLearning.no', '否')}
                    </Tag>
                  </span>
                </div>
                <div className={styles.statusItem}>
                  <span className={styles.statusLabel}>👤 {t('habitLearning.anyonePresent', '有人在场')}</span>
                  <span className={styles.statusValue}>
                    <Tag color={envContext.is_anyone_present ? 'success' : 'default'}>
                      {envContext.is_anyone_present ? t('habitLearning.yes', '是') : t('habitLearning.no', '否')}
                    </Tag>
                  </span>
                </div>
                <div className={styles.statusItem}>
                  <span className={styles.statusLabel}><CloudOutlined /> {t('habitLearning.weather', '天气')}</span>
                  <span className={styles.statusValue}>{envContext.weather || '-'}</span>
                </div>
                <div className={styles.statusItem}>
                  <span className={styles.statusLabel}>🌬️ {t('habitLearning.windSpeed', '风速')}</span>
                  <span className={styles.statusValue}>{envContext.wind_speed != null ? envContext.wind_speed : '-'}</span>
                </div>
                <div className={styles.statusItem}>
                  <span className={styles.statusLabel}>🏭 {t('habitLearning.airQuality', '空气质量')}</span>
                  <span className={styles.statusValue}>{envContext.air_quality != null ? envContext.air_quality : '-'}</span>
                </div>
                <div className={styles.statusItem}>
                  <span className={styles.statusLabel}>🌅 {t('habitLearning.timePeriod', '时段')}</span>
                  <span className={styles.statusValue}>{envContext.time_period || '-'}</span>
                </div>
                <div className={styles.statusItem}>
                  <span className={styles.statusLabel}>💧 {t('habitLearning.waterLeak', '水浸检测')}</span>
                  <span className={styles.statusValue}>
                    <Tag color={envContext.water_leak_detected ? 'error' : 'success'}>
                      {envContext.water_leak_detected ? t('habitLearning.detected', '检测到') : t('habitLearning.normal', '正常')}
                    </Tag>
                  </span>
                </div>
                <div className={styles.statusItem}>
                  <span className={styles.statusLabel}>🚗 {t('habitLearning.trafficRestriction', '限行状态')}</span>
                  <span className={styles.statusValue}>
                    {envContext.traffic_restricted ? (
                      <Tag color="warning">{envContext.traffic_restricted}</Tag>
                    ) : (
                      <Tag color="success">{t('habitLearning.normal', '正常')}</Tag>
                    )}
                  </span>
                </div>
              </div>
            </Card>
          )}

          {/* Context Entity Config */}
          <Card className={styles.habitCard} contentClassName={styles.habitCardContent}>
            <div className={styles.habitCardTitle}>
              <SettingOutlined /> {t('habitLearning.contextEntityConfig', '上下文实体配置')}
              <Button
                type="primary"
                size="small"
                loading={entitySaving}
                onClick={handleSaveContextEntities}
                style={{ marginLeft: 'auto' }}
              >
                {t('habitLearning.saveEntities', '保存实体配置')}
              </Button>
            </div>
            <div style={{ marginBottom: 8, color: '#999', fontSize: 12 }}>
              {t('habitLearning.entityConfigHint', '为每个维度指定 HA 实体，留空则自动检测。保存后立即生效。')}
            </div>
            <div className={styles.habitCardItemList}>
              {[
                { key: 'indoor_temperature', label: t('habitLearning.indoorTempEntity', '🌡️ 室内温度传感器') },
                { key: 'humidity', label: t('habitLearning.humidityEntity', '💧 湿度传感器') },
                { key: 'outdoor_temperature', label: t('habitLearning.outdoorTempEntity', '🌡️ 室外温度传感器') },
                { key: 'light_level', label: t('habitLearning.lightLevelEntity', '💡 光照传感器') },
                { key: 'is_home', label: t('habitLearning.isHomeEntity', '🏠 有人在家（person/tracker）') },
                { key: 'is_anyone_present', label: t('habitLearning.anyonePresentEntity', '👤 有人在场（motion/presence）') },
                { key: 'weather', label: t('habitLearning.weatherEntity', '☁️ 天气实体') },
                { key: 'air_quality', label: t('habitLearning.airQualityEntity', '🏭 空气质量传感器') },
                { key: 'water_leak', label: t('habitLearning.waterLeakEntity', '💧 水浸传感器') },
                { key: 'traffic_restriction', label: t('habitLearning.trafficRestrictionEntity', '🚗 限行状态') },
              ].map(({ key, label }) => (
                <div className={styles.habitItem} key={key} style={{ alignItems: 'center' }}>
                  <span className={styles.habitLabel} style={{ minWidth: 200 }}>{label}</span>
                  <Select
                    allowClear
                    showSearch
                    style={{ flex: 1, minWidth: 200 }}
                    placeholder={t('habitLearning.selectEntity', '选择实体（留空自动检测）')}
                    value={contextEntities[key] || undefined}
                    onChange={(val) => updateContextEntity(key, val)}
                    filterOption={(input, option) =>
                      (option?.value ?? '').toLowerCase().includes(input.toLowerCase())
                    }
                    options={entitySelectOptions}
                  />
                </div>
              ))}
            </div>
          </Card>

          {/* Collector Config */}
          <Card className={styles.habitCard} contentClassName={styles.habitCardContent}>
            <div className={styles.habitCardTitle}>{t('habitLearning.collectorConfig')}</div>
            <div className={styles.habitCardItemList}>
              <div className={styles.habitItem}>
                <div className={styles.habitLabel}>
                  <SyncOutlined /> {t('habitLearning.collectorStatus')}
                </div>
                <Switch
                  checked={isCollectorRunning}
                  onChange={handleCollectorToggle}
                  checkedChildren={<CheckCircleOutlined />}
                  unCheckedChildren={<CloseCircleOutlined />}
                />
              </div>
              <div className={styles.habitItem}>
                <div className={styles.habitLabel}>
                  <ClockCircleOutlined /> {t('habitLearning.flushInterval')}
                  <span className={styles.description}>{t('habitLearning.flushIntervalDesc')}</span>
                </div>
                <Input
                  type="number"
                  min={1}
                  max={300}
                  value={collectorConfig.flush_interval}
                  onChange={(e) => setCollectorConfig({ ...collectorConfig, flush_interval: parseInt(e.target.value) || 5 })}
                  onBlur={() => handleConfigSave('collector', 'flush_interval', collectorConfig.flush_interval)}
                  style={{ width: 200 }}
                  suffix="sec"
                />
              </div>
            </div>
          </Card>

          {/* Learner Config */}
          <Card className={styles.habitCard} contentClassName={styles.habitCardContent}>
            <div className={styles.habitCardTitle}>
              {t('habitLearning.learnerConfig')}
              <Button
                type="primary"
                icon={<ExperimentOutlined />}
                loading={training}
                onClick={handleTrain}
                size="small"
              >
                {training ? t('habitLearning.training') : t('habitLearning.trainNow')}
              </Button>
            </div>
            <div className={styles.habitCardItemList}>
              <div className={styles.habitItem}>
                <div className={styles.habitLabel}>
                  <ClockCircleOutlined /> {t('habitLearning.learnInterval')}
                  <span className={styles.description}>{t('habitLearning.learnIntervalDesc')}</span>
                </div>
                <Input
                  type="number"
                  min={60}
                  max={86400}
                  value={learnerConfig.learn_interval}
                  onChange={(e) => setLearnerConfig({ ...learnerConfig, learn_interval: parseInt(e.target.value) || 3600 })}
                  onBlur={() => handleConfigSave('learner', 'learn_interval', learnerConfig.learn_interval)}
                  style={{ width: 200 }}
                  suffix="sec"
                />
              </div>
              <div className={styles.habitItem}>
                <div className={styles.habitLabel}>
                  <DatabaseOutlined /> {t('habitLearning.minOccurrences')}
                  <span className={styles.description}>{t('habitLearning.minOccurrencesDesc')}</span>
                </div>
                <Input
                  type="number"
                  min={1}
                  max={100}
                  value={learnerConfig.min_occurrences}
                  onChange={(e) => setLearnerConfig({ ...learnerConfig, min_occurrences: parseInt(e.target.value) || 3 })}
                  onBlur={() => handleConfigSave('learner', 'min_occurrences', learnerConfig.min_occurrences)}
                  style={{ width: 200 }}
                />
              </div>
              <div className={styles.habitItem}>
                <div className={styles.habitLabel}>
                  <ClockCircleOutlined /> {t('habitLearning.timeBucketMinutes')}
                  <span className={styles.description}>{t('habitLearning.timeBucketMinutesDesc')}</span>
                </div>
                <Input
                  type="number"
                  min={5}
                  max={120}
                  value={learnerConfig.time_bucket_minutes}
                  onChange={(e) => setLearnerConfig({ ...learnerConfig, time_bucket_minutes: parseInt(e.target.value) || 30 })}
                  onBlur={() => handleConfigSave('learner', 'time_bucket_minutes', learnerConfig.time_bucket_minutes)}
                  style={{ width: 200 }}
                  suffix="min"
                />
              </div>
            </div>
          </Card>

          {/* Decision Engine Config */}
          <Card className={styles.habitCard} contentClassName={styles.habitCardContent}>
            <div className={styles.habitCardTitle}>
              {t('habitLearning.decisionEngineConfig')}
              <Tag color={isEngineRunning ? 'processing' : 'default'} icon={isEngineRunning ? <SyncOutlined spin /> : null}>
                {isEngineRunning ? t('habitLearning.engineRunning') : t('habitLearning.engineStopped')}
              </Tag>
            </div>
            <div className={styles.habitCardItemList}>
              <div className={styles.habitItem}>
                <div className={styles.habitLabel}>
                  <RobotOutlined /> {t('habitLearning.engineEnabled')}
                  <span className={styles.description}>{t('habitLearning.engineEnabledDesc')}</span>
                </div>
                <Switch
                  checked={engineConfig.enabled}
                  onChange={(checked) => {
                    setEngineConfig({ ...engineConfig, enabled: checked });
                    handleEngineToggle(checked);
                  }}
                />
              </div>
              <div className={styles.habitItem}>
                <div className={styles.habitLabel}>
                  <ClockCircleOutlined /> {t('habitLearning.cycleInterval')}
                  <span className={styles.description}>{t('habitLearning.cycleIntervalDesc')}</span>
                </div>
                <Input
                  type="number"
                  min={10}
                  max={3600}
                  value={engineConfig.cycle_interval}
                  onChange={(e) => setEngineConfig({ ...engineConfig, cycle_interval: parseInt(e.target.value) || 60 })}
                  onBlur={() => handleConfigSave('decision_engine', 'cycle_interval', engineConfig.cycle_interval)}
                  style={{ width: 200 }}
                  suffix="sec"
                />
              </div>
              <div className={styles.habitItem}>
                <div className={styles.habitLabel}>
                  <ThunderboltOutlined /> {t('habitLearning.confidenceThreshold')}
                  <span className={styles.description}>{t('habitLearning.confidenceThresholdDesc')}</span>
                </div>
                <Input
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  value={engineConfig.confidence_threshold}
                  onChange={(e) => setEngineConfig({ ...engineConfig, confidence_threshold: parseFloat(e.target.value) || 0.65 })}
                  onBlur={() => handleConfigSave('decision_engine', 'confidence_threshold', engineConfig.confidence_threshold)}
                  style={{ width: 200 }}
                />
              </div>
              <div className={styles.habitItem}>
                <div className={styles.habitLabel}>
                  <SafetyOutlined /> {t('habitLearning.riskLevelLimit')}
                  <span className={styles.description}>{t('habitLearning.riskLevelLimitDesc')}</span>
                </div>
                <Select
                  value={engineConfig.risk_level_limit}
                  onChange={(value) => {
                    setEngineConfig({ ...engineConfig, risk_level_limit: value });
                    handleConfigSave('decision_engine', 'risk_level_limit', value);
                  }}
                  style={{ width: 200 }}
                >
                  {riskOptions.map((opt) => (
                    <Option key={opt.value} value={opt.value}>
                      {opt.label}
                    </Option>
                  ))}
                </Select>
              </div>
              {engineStats && (
                <>
                  <div className={styles.habitItem}>
                    <div className={styles.habitLabel}>
                      <ThunderboltOutlined /> {t('habitLearning.cycles')}
                    </div>
                    <span className={styles.habitValue}>{engineStats.total_cycles ?? 0}</span>
                  </div>
                  <div className={styles.habitItem}>
                    <div className={styles.habitLabel}>
                      <ExperimentOutlined /> {t('habitLearning.predictionsMade')}
                    </div>
                    <span className={styles.habitValue}>{engineStats.predictions_made ?? 0}</span>
                  </div>
                  <div className={styles.habitItem}>
                    <div className={styles.habitLabel}>
                      <SafetyOutlined /> {t('habitLearning.actionsBlocked')}
                    </div>
                    <span className={styles.habitValue}>{engineStats.actions_blocked ?? 0}</span>
                  </div>
                  <div className={styles.habitItem}>
                    <div className={styles.habitLabel}>
                      <CloudOutlined /> {t('habitLearning.contextBlocked', '上下文拦截')}
                    </div>
                    <span className={styles.habitValue}>{engineStats.actions_context_blocked ?? 0}</span>
                  </div>
                  <div className={styles.habitItem}>
                    <div className={styles.habitLabel}>
                      <RobotOutlined /> {t('habitLearning.inquiriesSent')}
                    </div>
                    <span className={styles.habitValue}>{engineStats.inquiries_sent ?? 0}</span>
                  </div>
                </>
              )}
            </div>
          </Card>

          {/* Predictions */}
          <Card className={styles.habitCard} contentClassName={styles.habitCardContent}>
            <div className={styles.habitCardTitle}>{t('habitLearning.predictions')}</div>
            <div className={styles.predictionsTable}>
              <Table
                dataSource={predictions}
                columns={predictionColumns}
                rowKey={(record, index) => `${record.entity_id}-${index}`}
                pagination={false}
                size="small"
                locale={{ emptyText: t('habitLearning.noPredictions') }}
              />
            </div>
          </Card>

          {/* Patterns */}
          <Card className={styles.habitCard} contentClassName={styles.habitCardContent}>
            <div className={styles.habitCardTitle}>{t('habitLearning.patterns')}</div>
            <div className={styles.patternsTable}>
              <Table
                dataSource={patterns}
                columns={patternColumns}
                rowKey={(record, index) => `${record.entity_id}-${record.pattern_type}-${index}`}
                pagination={{ pageSize: 10, size: 'small' }}
                size="small"
                locale={{ emptyText: t('habitLearning.noPatterns') }}
              />
            </div>
          </Card>
        </Spin>
      </div>
    </div>
  );
};

export default HabitLearning;
