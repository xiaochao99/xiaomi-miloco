/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState, useEffect } from 'react';
import {Select, Switch, Button, Form, Input, Modal, message, Divider, Space, Typography, Segmented, Table, Popconfirm, Tag, Tooltip, Alert} from 'antd';
import { useTranslation } from 'react-i18next';
import { SettingOutlined, GlobalOutlined, BulbOutlined, KeyOutlined, ToolOutlined, PlusOutlined, CopyOutlined, DeleteOutlined, EyeOutlined, VideoCameraOutlined } from '@ant-design/icons';
import { setHAAuth, getHAAuth, getLanguage, setLanguage, getAPITokenList, createAPIToken, deleteAPIToken, getCameraConfig, setCameraConfig as saveCameraConfig, getRTSPServerConfig, setRTSPServerConfig, getXiaoAIConfig, updateXiaoAIConfig, restartXiaoAI } from '@/api';
import { useTheme } from '@/contexts/ThemeContext';
import { useSettingStore } from '@/stores/settingStore';
import { Card, Header } from '@/components';
import styles from './index.module.less';

const { Title, Text } = Typography;
const { Option } = Select;

/**
 * Setting Page - Application settings page for language, theme, and authorization configuration
 * 设置页面 - 用于语言、主题和授权配置的应用设置页面
 *
 * @returns {JSX.Element} Settings page component
 */
const Setting = () => {
  const { i18n, t } = useTranslation();
  const { themeMode, changeTheme } = useTheme();
  const {
    language: storeLanguage,
    themeMode: storeThemeMode,
    setLanguage: setStoreLanguage,
    setThemeMode: setStoreThemeMode
  } = useSettingStore();
  const [form] = Form.useForm();
  const [haModalVisible, setHaModalVisible] = useState(false);
  const [haFormValues, setHaFormValues] = useState({
    base_url: '',
    token: ''
  });

  // API Token states
  const [apiTokens, setApiTokens] = useState([]);
  const [tokenModalVisible, setTokenModalVisible] = useState(false);
  const [tokenForm] = Form.useForm();
  const [createdToken, setCreatedToken] = useState(null);
  const [tokenDetailModalVisible, setTokenDetailModalVisible] = useState(false);
  const [loadingTokens, setLoadingTokens] = useState(false);

  // Camera config states
  const [cameraConfig, setCameraConfig] = useState({
    video_quality: 'HIGH',
    vision_img_resolution: 640,
    frame_interval: 500
  });
  const [loadingCameraConfig, setLoadingCameraConfig] = useState(false);

  // RTSP server config states
  const [rtspServerConfig, setRtspServerConfigState] = useState({
    enabled: true,
    port: 8554
  });
  const [loadingRtspServerConfig, setLoadingRtspServerConfig] = useState(false);

  // Xiaomi Bridge config states
  const [bridgeConfig, setBridgeConfig] = useState({
    enabled: false,
    vad: {
      threshold: 0.10,
      min_speech_duration_ms: 250,
      min_silence_duration_ms: 500,
      model_path: 'models/vad/silero_vad.onnx'
    },
    kws: {
      keywords: ['小米同学'],
      keywords_score: 2.0,
      keywords_threshold: 0.2,
      model_dir: 'models/kws/sherpa-onnx-kws'
    },
    asr: {
      model: 'sense_voice',
      int8: true,
      model_dir: 'models/asr/sense-voice',
      num_threads: 2
    },
    tts: {
      engine: 'doubao',
      app_id: '',
      access_key: '',
      api_key: '',
      api_base_url: 'https://api.xiaomimimo.com',
      default_speaker: 'zh_female_vv_uranus_bigtts',
      audio_format: 'pcm',
      stream: true,
      speed: 1.0
    },
    audio_input: {
      gain: 1.0
    },
    exit_keywords: ['退出', '结束对话', '停止'],
    wakeup_timeout: 20,
    wakeup_opening_reply: '',
    sample_rate: 16000,
    ws_port: 4399,
    ws_host: '0.0.0.0'
  });
  const [loadingBridgeConfig, setLoadingBridgeConfig] = useState(false);
  const [expandedSections, setExpandedSections] = useState({
    vad: false,
    kws: false,
    asr: false,
    tts: false,
    audio: false,
    dialog: false,
    ws: false
  });

  // language options
  const languageOptions = [
    { key: 'zh', label: '简体中文' },
    { key: 'en', label: 'English' },
  ];

  // theme mode options
  const themeOptions = [
    { key: 'light', label: t('setting.lightMode'), icon: '☀️' },
    { key: 'dark', label: t('setting.darkMode'), icon: '🌙' },
    { key: 'system', label: t('setting.systemMode'), icon: '🔄' },
  ];


  useEffect(() => {
    const fetchServerLanguage = async () => {
      try {
        const res = await getLanguage();
        if (res && res?.code === 0) {
          const serverLanguage = res?.data?.language;
          if (serverLanguage && serverLanguage !== i18n.language) {
            setStoreLanguage(serverLanguage);
            i18n.changeLanguage(serverLanguage);
          }
        }
      } catch (error) {
        console.warn('Failed to get server language setting:', error);
        if (storeLanguage && storeLanguage !== i18n.language) {
          i18n.changeLanguage(storeLanguage);
        }
      }
    };
    fetchServerLanguage();
  }, []); 

  useEffect(() => {
    if (storeLanguage && storeLanguage !== i18n.language) {
      i18n.changeLanguage(storeLanguage);
    }
  }, [storeLanguage, i18n]);

  // get Home Assistant authorization information
  useEffect(() => {
    const fetchHAAuth = async () => {
      try {
        const res = await getHAAuth();
        if (res && res?.code === 0) {
          setHaFormValues(res?.data || {});
        }
      } catch (error) {
        console.error(t('setting.getHAAuthFailed'), error);
      }
    };
    fetchHAAuth();
  }, []);

  // Load API Tokens
  useEffect(() => {
    fetchAPITokens();
  }, []);

  // Load Camera Config
  useEffect(() => {
    fetchCameraConfig();
  }, []);

  // Load RTSP Server Config
  useEffect(() => {
    fetchRtspServerConfig();
  }, []);

  // Load Xiaomi Bridge Config
  useEffect(() => {
    fetchBridgeConfig();
  }, []);

  const fetchBridgeConfig = async () => {
    setLoadingBridgeConfig(true);
    try {
      const res = await getXiaoAIConfig();
      if (res && res.code === 0) {
        setBridgeConfig(res.data);
      }
    } catch (error) {
      console.error('Failed to load Xiaomi Bridge config:', error);
    } finally {
      setLoadingBridgeConfig(false);
    }
  };

  const handleBridgeConfigChange = (section, key, value) => {
    setBridgeConfig(prev => {
      if (section) {
        return {
          ...prev,
          [section]: {
            ...prev[section],
            [key]: value
          }
        };
      }
      return {
        ...prev,
        [key]: value
      };
    });
  };

  const handleBridgeConfigSave = async () => {
    setLoadingBridgeConfig(true);
    try {
      const res = await updateXiaoAIConfig(bridgeConfig);
      if (res && res.code === 0) {
        message.success(t('setting.xiaoaiServiceConfigSaved'));
        if (res.data) {
          setBridgeConfig(res.data);
        }
      } else {
        message.error(res?.message || t('setting.xiaoaiServiceConfigSaveFailed'));
      }
    } catch (error) {
      console.error('Failed to save XiaoAI Service config:', error);
      message.error(t('setting.xiaoaiServiceConfigSaveFailed'));
    } finally {
      setLoadingBridgeConfig(false);
    }
  };

  const handleBridgeRestart = async () => {
    setLoadingBridgeConfig(true);
    try {
      const res = await restartXiaoAI();
      if (res && res.code === 0) {
        message.success(t('setting.xiaoaiServiceRestartSuccess'));
      } else {
        message.error(res?.message || t('setting.xiaoaiServiceRestartFailed'));
      }
    } catch (error) {
      console.error('Failed to restart XiaoAI Service:', error);
      message.error(t('setting.xiaoaiServiceRestartFailed'));
    } finally {
      setLoadingBridgeConfig(false);
    }
  };

  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  const fetchCameraConfig = async () => {
    try {
      const res = await getCameraConfig();
      if (res && res.code === 0) {
        setCameraConfig(res.data);
      }
    } catch (error) {
      console.error('Failed to load camera config:', error);
    }
  };

  const fetchRtspServerConfig = async () => {
    try {
      const res = await getRTSPServerConfig();
      if (res && res.code === 0) {
        setRtspServerConfigState(res.data);
      }
    } catch (error) {
      console.error('Failed to load RTSP server config:', error);
    }
  };

  const fetchAPITokens = async () => {
    setLoadingTokens(true);
    try {
      const res = await getAPITokenList();
      if (res && res.code === 0) {
        setApiTokens(res.data?.tokens || []);
      }
    } catch (error) {
      console.error('Failed to load API tokens:', error);
    } finally {
      setLoadingTokens(false);
    }
  };


  // handle language change
  const handleLanguageChange = async (value) => {
    try {
      setStoreLanguage(value);
      i18n.changeLanguage(value);

      const res = await setLanguage({ language: value });
      if (res && res?.code === 0) {
        const languageName = languageOptions.find(opt => opt.key === value)?.label;
        message.success(`${t('setting.languageChanged')} ${languageName}`);
      } else {
        message.error(res?.message || t('setting.languageChangeFailed'));
      }
    } catch (error) {
      console.error('Failed to change language:', error);
      message.error(t('setting.languageChangeFailed'));
    }
  };

  // handle theme mode change
  const handleThemeChange = (value) => {
    setStoreThemeMode(value);
    changeTheme(value);
    message.success(`${t('setting.themeChanged')} ${themeOptions.find(opt => opt.key === value)?.label} ${t('setting.mode')}`);
  };

  // handle Home Assistant authorization configuration
  const handleHaAuthConfig = () => {
    setHaModalVisible(true);
  };

  // handle Home Assistant authorization confirm
  const handleHaAuthConfirm = async () => {
    try {
      const values = await form.validateFields();
      const res = await setHAAuth(values);
      if (res && res?.code === 0) {
        message.success(t('setting.haAuthConfigSavedSuccess'));
        setHaModalVisible(false);
        form.resetFields();
        setHaFormValues(values);
      } else {
        message.error(res?.message || t('setting.haAuthConfigSavedFailed'));
      }
    } catch (error) {
      console.error('handleHaAuthConfirm failed:', error);
    }
  };

  // handle Home Assistant authorization cancel
  const handleHaAuthCancel = () => {
    setHaModalVisible(false);
    form.resetFields();
  };

  // API Token handlers
  const handleCreateToken = () => {
    setTokenModalVisible(true);
  };

  const handleTokenModalConfirm = async () => {
    try {
      const values = await tokenForm.validateFields();
      const res = await createAPIToken(values);
      if (res && res.code === 0) {
        message.success(t('setting.tokenCreateSuccess'));
        setCreatedToken(res.data);
        setTokenModalVisible(false);
        setTokenDetailModalVisible(true);
        tokenForm.resetFields();
        fetchAPITokens();
      } else {
        message.error(res?.message || t('setting.tokenCreateFailed'));
      }
    } catch (error) {
      console.error('Create token failed:', error);
    }
  };

  const handleTokenModalCancel = () => {
    setTokenModalVisible(false);
    tokenForm.resetFields();
  };

  const handleDeleteToken = async (tokenId) => {
    try {
      const res = await deleteAPIToken({ token_id: tokenId });
      if (res && res.code === 0) {
        message.success(t('setting.tokenDeleteSuccess'));
        fetchAPITokens();
      } else {
        message.error(res?.message || t('setting.tokenDeleteFailed'));
      }
    } catch (error) {
      console.error('Delete token failed:', error);
      message.error(t('setting.tokenDeleteFailed'));
    }
  };

  const handleCopyToken = (text) => {
    navigator.clipboard.writeText(text).then(() => {
      message.success(t('setting.tokenCopied'));
    }).catch(() => {
      message.error(t('setting.tokenCopyFailed'));
    });
  };

  const formatDate = (dateString) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  // Handle camera config change - video quality
  const handleVideoQualityChange = async (value) => {
    const newConfig = { ...cameraConfig, video_quality: value };
    setCameraConfig(newConfig);
    
    setLoadingCameraConfig(true);
    try {
      const payload = {
        video_quality: value,
        vision_img_resolution: Number(newConfig.vision_img_resolution) || 0
      };
      console.log('Saving camera config (quality):', payload);
      const res = await saveCameraConfig(payload);
      console.log('Save response:', res);
      if (res && res.code === 0) {
        message.success(t('setting.cameraConfigSaved'));
        if (res.data) {
          setCameraConfig(res.data);
        }
      } else {
        console.error('Save failed:', res);
        message.error(res?.message || t('setting.cameraConfigSaveFailed'));
      }
    } catch (error) {
      console.error('Failed to save camera config:', error);
      message.error(t('setting.cameraConfigSaveFailed'));
    } finally {
      setLoadingCameraConfig(false);
    }
  };

  // Handle camera config change - resolution (on blur)
  const handleResolutionChange = (value) => {
    setCameraConfig(prev => ({ ...prev, vision_img_resolution: value }));
  };

  // Handle resolution save on blur
  const handleResolutionBlur = async () => {
    const value = Number(cameraConfig.vision_img_resolution) || 0;
    if (value < 0) {
      message.error(t('setting.pleaseEnterResolution'));
      return;
    }
    
    setLoadingCameraConfig(true);
    try {
      const payload = {
        video_quality: cameraConfig.video_quality,
        vision_img_resolution: value
      };
      console.log('Saving camera config (resolution):', payload);
      const res = await saveCameraConfig(payload);
      console.log('Save response:', res);
      if (res && res.code === 0) {
        message.success(t('setting.cameraConfigSaved'));
        if (res.data) {
          setCameraConfig(res.data);
        }
      } else {
        console.error('Save failed:', res);
        message.error(res?.message || t('setting.cameraConfigSaveFailed'));
      }
    } catch (error) {
      console.error('Failed to save camera config:', error);
      message.error(t('setting.cameraConfigSaveFailed'));
    } finally {
      setLoadingCameraConfig(false);
    }
  };

  const handleRtspEnabledChange = async (checked) => {
    const nextConfig = { ...rtspServerConfig, enabled: checked };
    setRtspServerConfigState(nextConfig);

    setLoadingRtspServerConfig(true);
    try {
      const payload = { enabled: !!checked, port: Number(nextConfig.port) || 8554 };
      const res = await setRTSPServerConfig(payload);
      if (res && res.code === 0) {
        message.success(t('setting.rtspServerConfigSaved'));
        if (res.data) {
          setRtspServerConfigState(res.data);
        }
      } else {
        message.error(res?.message || t('setting.rtspServerConfigSaveFailed'));
      }
    } catch (error) {
      console.error('Failed to save RTSP server config:', error);
      message.error(t('setting.rtspServerConfigSaveFailed'));
    } finally {
      setLoadingRtspServerConfig(false);
    }
  };

  const handleRtspPortChange = (value) => {
    setRtspServerConfigState(prev => ({ ...prev, port: value }));
  };

  const handleRtspPortBlur = async () => {
    const port = Number(rtspServerConfig.port);
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
      message.error(t('setting.pleaseEnterRtspPort'));
      return;
    }

    setLoadingRtspServerConfig(true);
    try {
      const payload = { enabled: !!rtspServerConfig.enabled, port };
      const res = await setRTSPServerConfig(payload);
      if (res && res.code === 0) {
        message.success(t('setting.rtspServerConfigSaved'));
        if (res.data) {
          setRtspServerConfigState(res.data);
        }
      } else {
        message.error(res?.message || t('setting.rtspServerConfigSaveFailed'));
      }
    } catch (error) {
      console.error('Failed to save RTSP server config:', error);
      message.error(t('setting.rtspServerConfigSaveFailed'));
    } finally {
      setLoadingRtspServerConfig(false);
    }
  };


  return (
    <div className={styles.settingContainer}>
      <div className={styles.settingContent}>
        <Header title={t('home.menu.setting')} />

        {/* regular setting */}
        <Card className={styles.settingCard} contentClassName={styles.settingCardContent}>
          <div className={styles.settingCardTitle}>{t('setting.regularSetting')}</div>
          <div className={styles.settingCardItemList}>
          <div className={styles.settingItem}>
            <div className={styles.settingLabel}>
              <GlobalOutlined /> {t('setting.language')}
            </div>
            <Select
              value={storeLanguage || i18n.language}
              onChange={handleLanguageChange}
              style={{ width: 382 }}
              placeholder={t('setting.pleaseSelectLanguage')}
            >
              {languageOptions.map(option => (
                <Option key={option.key} value={option.key}>
                  {option.label}
                </Option>
              ))}
            </Select>
          </div>

          <div className={styles.settingItem}>
            <div className={styles.settingLabel}>
              <BulbOutlined /> {t('setting.themeMode')}
            </div>
            <Segmented
              value={storeThemeMode || themeMode}
              onChange={handleThemeChange}
              options={themeOptions.map(option => ({
                label: (
                  <div className={styles.segmentedOption}>
                    {/* <span className={styles.segmentedIcon}>{option.icon}</span> */}
                    <span>{option.label}</span>
                  </div>
                ),
                value: option.key
              }))}
              className={styles.themeSegmented}
            />
          </div>
          </div>
        </Card>

        {/* advanced setting */}
        <Card className={styles.settingCard} contentClassName={styles.settingCardContent}>
          <div className={styles.settingCardTitle}>{t('setting.authorizationSetting')}</div>
          <div className={styles.settingCardItemList}>
          <div className={styles.settingItem}>
            <div className={styles.settingLabel}>
              <KeyOutlined /> {t('setting.miHomeAuthorization')}
            </div>
            <Space>
              <Button>{t('setting.configured')}</Button>
            </Space>
          </div>

          <div className={styles.settingItem}>
            <div className={styles.settingLabel}>
              <KeyOutlined /> {t('setting.homeAssistantAuthorization')}
            </div>
              <Button onClick={handleHaAuthConfig}>{haFormValues?.base_url ? t('setting.configured') : t('setting.configure')}</Button>
            </div>
          </div>
        </Card>

        {/* Camera configuration */}
        <Card className={styles.settingCard} contentClassName={styles.settingCardContent}>
          <div className={styles.settingCardTitle}>{t('setting.cameraSetting')}</div>
          <div className={styles.settingCardItemList}>
            <div className={styles.settingItem}>
              <div className={styles.settingLabel}>
                <VideoCameraOutlined /> {t('setting.videoQuality')}
              </div>
              <Select
                value={cameraConfig.video_quality}
                onChange={handleVideoQualityChange}
                style={{ width: 382 }}
                disabled={loadingCameraConfig}
              >
                <Option value="LOW">{t('setting.videoQualityLow')}</Option>
                <Option value="HIGH">{t('setting.videoQualityHigh')}</Option>
              </Select>
            </div>

            <div className={styles.settingItem}>
              <div className={styles.settingLabel}>
                <ToolOutlined /> {t('setting.visionImgResolution')}
              </div>
              <Tooltip title={t('setting.visionImgResolutionTooltip')}>
                <Input
                  type="number"
                  min={0}
                  max={3840}
                  value={cameraConfig.vision_img_resolution}
                  onChange={(e) => handleResolutionChange(parseInt(e.target.value) || 0)}
                  onBlur={handleResolutionBlur}
                  style={{ width: 382 }}
                  disabled={loadingCameraConfig}
                  placeholder={t('setting.pleaseEnterResolution')}
                />
              </Tooltip>
            </div>
          </div>
        </Card>

        {/* RTSP server configuration */}
        <Card className={styles.settingCard} contentClassName={styles.settingCardContent}>
          <div className={styles.settingCardTitle}>{t('setting.rtspServerSetting')}</div>
          <div className={styles.settingCardItemList}>
            <div className={styles.settingItem}>
              <div className={styles.settingLabel}>
                <ToolOutlined /> {t('setting.rtspServerEnabled')}
              </div>
              <Switch
                checked={!!rtspServerConfig.enabled}
                onChange={handleRtspEnabledChange}
                disabled={loadingRtspServerConfig}
              />
            </div>

            <div className={styles.settingItem}>
              <div className={styles.settingLabel}>
                <ToolOutlined /> {t('setting.rtspServerPort')}
              </div>
              <Input
                type="number"
                min={1}
                max={65535}
                value={rtspServerConfig.port}
                onChange={(e) => handleRtspPortChange(parseInt(e.target.value) || 0)}
                onBlur={handleRtspPortBlur}
                style={{ width: 382 }}
                disabled={loadingRtspServerConfig}
                placeholder={t('setting.rtspServerPortPlaceholder')}
              />
            </div>
          </div>
        </Card>

        {/* API Token management */}
        <Card className={styles.settingCard} contentClassName={styles.settingCardContent}>
          <div className={styles.settingCardTitle}>{t('setting.apiTokenManagement')}</div>
          <div className={styles.settingCardItemList}>
            <div className={styles.tokenHeader}>
              <Text type="secondary">{t('setting.apiTokenDescription')}</Text>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateToken}>
                {t('setting.createToken')}
              </Button>
            </div>
            <Table
              dataSource={apiTokens}
              rowKey="id"
              loading={loadingTokens}
              pagination={false}
              size="small"
              columns={[
                {
                  title: t('setting.tokenName'),
                  dataIndex: 'name',
                  key: 'name',
                },
                {
                  title: t('setting.tokenPreview'),
                  dataIndex: 'token_preview',
                  key: 'token_preview',
                },
                {
                  title: t('setting.tokenStatus'),
                  dataIndex: 'is_active',
                  key: 'is_active',
                  render: (isActive) => (
                    <Tag color={isActive ? 'success' : 'default'}>
                      {isActive ? t('setting.active') : t('setting.inactive')}
                    </Tag>
                  ),
                },
                {
                  title: t('setting.tokenExpiresAt'),
                  dataIndex: 'expires_at',
                  key: 'expires_at',
                  render: (expiresAt) => formatDate(expiresAt),
                },
                {
                  title: t('setting.tokenCreatedAt'),
                  dataIndex: 'created_at',
                  key: 'created_at',
                  render: (createdAt) => formatDate(createdAt),
                },
                {
                  title: t('common.operation'),
                  key: 'action',
                  render: (_, record) => (
                    <Popconfirm
                      title={t('setting.deleteTokenConfirm')}
                      description={t('setting.deleteTokenConfirmDesc')}
                      onConfirm={() => handleDeleteToken(record.id)}
                      okText={t('common.confirm')}
                      cancelText={t('common.cancel')}
                    >
                      <Button type="link" danger icon={<DeleteOutlined />}>
                        {t('common.delete')}
                      </Button>
                    </Popconfirm>
                  ),
                },
              ]}
            />
          </div>
        </Card>

        {/* XiaoAI Service Configuration */}
        <Card className={styles.settingCard} contentClassName={styles.settingCardContent}>
          <div className={styles.settingCardTitle}>
            <Space>
              <ToolOutlined />
              {t('setting.xiaoaiServiceSetting')}
            </Space>
          </div>
          <div className={styles.settingCardItemList}>
            {/* Enable toggle */}
            <div className={styles.settingItem}>
              <div className={styles.settingLabel}>
                <KeyOutlined /> {t('setting.xiaoaiServiceEnabled')}
                <Tooltip title={t('setting.xiaoaiServiceEnabledDesc')}>
                  <span style={{ marginLeft: 4, color: '#999', fontSize: 12 }}>(?)</span>
                </Tooltip>
              </div>
              <Switch
                checked={!!bridgeConfig.enabled}
                onChange={(checked) => handleBridgeConfigChange(null, 'enabled', checked)}
                disabled={loadingBridgeConfig}
              />
            </div>

            {/* VAD Settings */}
            <div className={styles.settingItem}>
              <Button
                type="link"
                onClick={() => toggleSection('vad')}
                style={{ padding: 0 }}
                className={styles.settingLabel}
              >
                <ToolOutlined /> {t('setting.vadSettings')}
              </Button>
              <span style={{ color: '#999', fontSize: 12 }}>
                {expandedSections.vad ? t('common.close') : t('common.edit')}
              </span>
            </div>
            {expandedSections.vad && (
              <div style={{ paddingLeft: 24, marginBottom: 16, borderLeft: 2, borderColor: '#e8e8e8', paddingBottom: 16 }}>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.vadThreshold')}
                    <Tooltip title={t('setting.vadThresholdDesc')}>
                      <span style={{ marginLeft: 4, color: '#999', fontSize: 12 }}>(?)</span>
                    </Tooltip>
                  </div>
                  <Input
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={bridgeConfig.vad?.threshold}
                    onChange={(e) => handleBridgeConfigChange('vad', 'threshold', parseFloat(e.target.value) || 0)}
                    style={{ width: 150 }}
                    disabled={loadingBridgeConfig}
                  />
                </div>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.vadMinSpeech')}
                    <Tooltip title={t('setting.vadMinSpeechDesc')}>
                      <span style={{ marginLeft: 4, color: '#999', fontSize: 12 }}>(?)</span>
                    </Tooltip>
                  </div>
                  <Input
                    type="number"
                    min={0}
                    value={bridgeConfig.vad?.min_speech_duration_ms}
                    onChange={(e) => handleBridgeConfigChange('vad', 'min_speech_duration_ms', parseInt(e.target.value) || 0)}
                    style={{ width: 150 }}
                    disabled={loadingBridgeConfig}
                  />
                </div>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.vadMinSilence')}
                    <Tooltip title={t('setting.vadMinSilenceDesc')}>
                      <span style={{ marginLeft: 4, color: '#999', fontSize: 12 }}>(?)</span>
                    </Tooltip>
                  </div>
                  <Input
                    type="number"
                    min={0}
                    value={bridgeConfig.vad?.min_silence_duration_ms}
                    onChange={(e) => handleBridgeConfigChange('vad', 'min_silence_duration_ms', parseInt(e.target.value) || 0)}
                    style={{ width: 150 }}
                    disabled={loadingBridgeConfig}
                  />
                </div>
              </div>
            )}

            {/* KWS Settings */}
            <div className={styles.settingItem}>
              <Button
                type="link"
                onClick={() => toggleSection('kws')}
                style={{ padding: 0 }}
                className={styles.settingLabel}
              >
                <KeyOutlined /> {t('setting.kwsSettings')}
              </Button>
              <span style={{ color: '#999', fontSize: 12 }}>
                {expandedSections.kws ? t('common.close') : t('common.edit')}
              </span>
            </div>
            {expandedSections.kws && (
              <div style={{ paddingLeft: 24, marginBottom: 16, borderLeft: 2, borderColor: '#e8e8e8', paddingBottom: 16 }}>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.kwsKeywords')}
                    <Tooltip title={t('setting.kwsKeywordsDesc')}>
                      <span style={{ marginLeft: 4, color: '#999', fontSize: 12 }}>(?)</span>
                    </Tooltip>
                  </div>
                  <Input
                    value={(bridgeConfig.kws?.keywords || []).join(',')}
                    onChange={(e) => handleBridgeConfigChange('kws', 'keywords', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                    style={{ width: 300 }}
                    disabled={loadingBridgeConfig}
                  />
                </div>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.kwsScore')}
                    <Tooltip title={t('setting.kwsScoreDesc')}>
                      <span style={{ marginLeft: 4, color: '#999', fontSize: 12 }}>(?)</span>
                    </Tooltip>
                  </div>
                  <Input
                    type="number"
                    min={0}
                    step={0.1}
                    value={bridgeConfig.kws?.keywords_score}
                    onChange={(e) => handleBridgeConfigChange('kws', 'keywords_score', parseFloat(e.target.value) || 0)}
                    style={{ width: 150 }}
                    disabled={loadingBridgeConfig}
                  />
                </div>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.kwsThreshold')}
                    <Tooltip title={t('setting.kwsThresholdDesc')}>
                      <span style={{ marginLeft: 4, color: '#999', fontSize: 12 }}>(?)</span>
                    </Tooltip>
                  </div>
                  <Input
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={bridgeConfig.kws?.keywords_threshold}
                    onChange={(e) => handleBridgeConfigChange('kws', 'keywords_threshold', parseFloat(e.target.value) || 0)}
                    style={{ width: 150 }}
                    disabled={loadingBridgeConfig}
                  />
                </div>
              </div>
            )}

            {/* ASR Settings */}
            <div className={styles.settingItem}>
              <Button
                type="link"
                onClick={() => toggleSection('asr')}
                style={{ padding: 0 }}
                className={styles.settingLabel}
              >
                <ToolOutlined /> {t('setting.asrSettings')}
              </Button>
              <span style={{ color: '#999', fontSize: 12 }}>
                {expandedSections.asr ? t('common.close') : t('common.edit')}
              </span>
            </div>
            {expandedSections.asr && (
              <div style={{ paddingLeft: 24, marginBottom: 16, borderLeft: 2, borderColor: '#e8e8e8', paddingBottom: 16 }}>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.asrModel')}
                  </div>
                  <Select
                    value={bridgeConfig.asr?.model}
                    onChange={(value) => handleBridgeConfigChange('asr', 'model', value)}
                    style={{ width: 200 }}
                    disabled={loadingBridgeConfig}
                  >
                    <Option value="sense_voice">{t('setting.asrModelSenseVoice')}</Option>
                    <Option value="paraformer">{t('setting.asrModelParaformer')}</Option>
                    <Option value="fire_red_asr">{t('setting.asrModelFireRed')}</Option>
                  </Select>
                </div>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.asrInt8')}
                    <Tooltip title={t('setting.asrInt8Desc')}>
                      <span style={{ marginLeft: 4, color: '#999', fontSize: 12 }}>(?)</span>
                    </Tooltip>
                  </div>
                  <Switch
                    checked={!!bridgeConfig.asr?.int8}
                    onChange={(checked) => handleBridgeConfigChange('asr', 'int8', checked)}
                    disabled={loadingBridgeConfig}
                  />
                </div>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.asrThreads')}
                    <Tooltip title={t('setting.asrThreadsDesc')}>
                      <span style={{ marginLeft: 4, color: '#999', fontSize: 12 }}>(?)</span>
                    </Tooltip>
                  </div>
                  <Input
                    type="number"
                    min={1}
                    value={bridgeConfig.asr?.num_threads}
                    onChange={(e) => handleBridgeConfigChange('asr', 'num_threads', parseInt(e.target.value) || 1)}
                    style={{ width: 100 }}
                    disabled={loadingBridgeConfig}
                  />
                </div>
              </div>
            )}

            {/* TTS Settings */}
            <div className={styles.settingItem}>
              <Button
                type="link"
                onClick={() => toggleSection('tts')}
                style={{ padding: 0 }}
                className={styles.settingLabel}
              >
                <ToolOutlined /> {t('setting.ttsSettings')}
              </Button>
              <span style={{ color: '#999', fontSize: 12 }}>
                {expandedSections.tts ? t('common.close') : t('common.edit')}
              </span>
            </div>
            {expandedSections.tts && (
              <div style={{ paddingLeft: 24, marginBottom: 16, borderLeft: 2, borderColor: '#e8e8e8', paddingBottom: 16 }}>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.ttsEngine')}
                  </div>
                  <Select
                    value={bridgeConfig.tts?.engine}
                    onChange={(value) => handleBridgeConfigChange('tts', 'engine', value)}
                    style={{ width: 200 }}
                    disabled={loadingBridgeConfig}
                  >
                    <Option value="doubao">{t('setting.ttsEngineDoubao')}</Option>
                    <Option value="xiaoai">{t('setting.ttsEngineXiaoai')}</Option>
                    <Option value="mimo">{t('setting.ttsEngineMimo')}</Option>
                  </Select>
                </div>
                {bridgeConfig.tts?.engine === 'doubao' && (
                  <>
                    <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                      <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                        {t('setting.ttsAppId')}
                      </div>
                      <Input
                        value={bridgeConfig.tts?.app_id}
                        onChange={(e) => handleBridgeConfigChange('tts', 'app_id', e.target.value)}
                        style={{ width: 300 }}
                        disabled={loadingBridgeConfig}
                      />
                    </div>
                    <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                      <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                        {t('setting.ttsAccessKey')}
                      </div>
                      <Input.Password
                        value={bridgeConfig.tts?.access_key}
                        onChange={(e) => handleBridgeConfigChange('tts', 'access_key', e.target.value)}
                        style={{ width: 300 }}
                        disabled={loadingBridgeConfig}
                      />
                    </div>
                  </>
                )}
                {bridgeConfig.tts?.engine === 'mimo' && (
                  <>
                    <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                      <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                        {t('setting.ttsApiKey')}
                      </div>
                      <Input.Password
                        value={bridgeConfig.tts?.api_key}
                        onChange={(e) => handleBridgeConfigChange('tts', 'api_key', e.target.value)}
                        style={{ width: 300 }}
                        disabled={loadingBridgeConfig}
                      />
                    </div>
                    <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                      <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                        {t('setting.ttsApiUrl')}
                      </div>
                      <Input
                        value={bridgeConfig.tts?.api_base_url}
                        onChange={(e) => handleBridgeConfigChange('tts', 'api_base_url', e.target.value)}
                        style={{ width: 300 }}
                        disabled={loadingBridgeConfig}
                      />
                    </div>
                  </>
                )}
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.ttsVoice')}
                  </div>
                  <Input
                    value={bridgeConfig.tts?.default_speaker}
                    onChange={(e) => handleBridgeConfigChange('tts', 'default_speaker', e.target.value)}
                    style={{ width: 300 }}
                    disabled={loadingBridgeConfig}
                  />
                </div>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.ttsFormat')}
                  </div>
                  <Select
                    value={bridgeConfig.tts?.audio_format}
                    onChange={(value) => handleBridgeConfigChange('tts', 'audio_format', value)}
                    style={{ width: 150 }}
                    disabled={loadingBridgeConfig}
                  >
                    <Option value="pcm">{t('setting.ttsFormatPcm')}</Option>
                    <Option value="mp3">{t('setting.ttsFormatMp3')}</Option>
                  </Select>
                </div>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.ttsStream')}
                    <Tooltip title={t('setting.ttsStreamDesc')}>
                      <span style={{ marginLeft: 4, color: '#999', fontSize: 12 }}>(?)</span>
                    </Tooltip>
                  </div>
                  <Switch
                    checked={!!bridgeConfig.tts?.stream}
                    onChange={(checked) => handleBridgeConfigChange('tts', 'stream', checked)}
                    disabled={loadingBridgeConfig}
                  />
                </div>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.ttsSpeed')}
                    <Tooltip title={t('setting.ttsSpeedDesc')}>
                      <span style={{ marginLeft: 4, color: '#999', fontSize: 12 }}>(?)</span>
                    </Tooltip>
                  </div>
                  <Input
                    type="number"
                    min={0.5}
                    max={2}
                    step={0.1}
                    value={bridgeConfig.tts?.speed}
                    onChange={(e) => handleBridgeConfigChange('tts', 'speed', parseFloat(e.target.value) || 1)}
                    style={{ width: 100 }}
                    disabled={loadingBridgeConfig}
                  />
                </div>
              </div>
            )}

            {/* Audio Settings */}
            <div className={styles.settingItem}>
              <Button
                type="link"
                onClick={() => toggleSection('audio')}
                style={{ padding: 0 }}
                className={styles.settingLabel}
              >
                <ToolOutlined /> {t('setting.audioSettings')}
              </Button>
              <span style={{ color: '#999', fontSize: 12 }}>
                {expandedSections.audio ? t('common.close') : t('common.edit')}
              </span>
            </div>
            {expandedSections.audio && (
              <div style={{ paddingLeft: 24, marginBottom: 16, borderLeft: 2, borderColor: '#e8e8e8', paddingBottom: 16 }}>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.audioGain')}
                    <Tooltip title={t('setting.audioGainDesc')}>
                      <span style={{ marginLeft: 4, color: '#999', fontSize: 12 }}>(?)</span>
                    </Tooltip>
                  </div>
                  <Input
                    type="number"
                    min={0}
                    max={10}
                    step={0.1}
                    value={bridgeConfig.audio_input?.gain}
                    onChange={(e) => handleBridgeConfigChange('audio_input', 'gain', parseFloat(e.target.value) || 1)}
                    style={{ width: 100 }}
                    disabled={loadingBridgeConfig}
                  />
                </div>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.audioSampleRate')}
                  </div>
                  <Input
                    type="number"
                    min={8000}
                    max={48000}
                    value={bridgeConfig.sample_rate}
                    onChange={(e) => handleBridgeConfigChange(null, 'sample_rate', parseInt(e.target.value) || 16000)}
                    style={{ width: 120 }}
                    disabled={loadingBridgeConfig}
                  />
                </div>
              </div>
            )}

            {/* Dialog Settings */}
            <div className={styles.settingItem}>
              <Button
                type="link"
                onClick={() => toggleSection('dialog')}
                style={{ padding: 0 }}
                className={styles.settingLabel}
              >
                <ToolOutlined /> {t('setting.dialogSettings')}
              </Button>
              <span style={{ color: '#999', fontSize: 12 }}>
                {expandedSections.dialog ? t('common.close') : t('common.edit')}
              </span>
            </div>
            {expandedSections.dialog && (
              <div style={{ paddingLeft: 24, marginBottom: 16, borderLeft: 2, borderColor: '#e8e8e8', paddingBottom: 16 }}>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.dialogExitKeywords')}
                    <Tooltip title={t('setting.dialogExitKeywordsDesc')}>
                      <span style={{ marginLeft: 4, color: '#999', fontSize: 12 }}>(?)</span>
                    </Tooltip>
                  </div>
                  <Input
                    value={(bridgeConfig.exit_keywords || []).join(',')}
                    onChange={(e) => handleBridgeConfigChange(null, 'exit_keywords', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                    style={{ width: 300 }}
                    disabled={loadingBridgeConfig}
                  />
                </div>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.dialogTimeout')}
                    <Tooltip title={t('setting.dialogTimeoutDesc')}>
                      <span style={{ marginLeft: 4, color: '#999', fontSize: 12 }}>(?)</span>
                    </Tooltip>
                  </div>
                  <Input
                    type="number"
                    min={5}
                    max={120}
                    value={bridgeConfig.wakeup_timeout}
                    onChange={(e) => handleBridgeConfigChange(null, 'wakeup_timeout', parseInt(e.target.value) || 20)}
                    style={{ width: 100 }}
                    disabled={loadingBridgeConfig}
                  />
                </div>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.dialogOpeningReply')}
                    <Tooltip title={t('setting.dialogOpeningReplyDesc')}>
                      <span style={{ marginLeft: 4, color: '#999', fontSize: 12 }}>(?)</span>
                    </Tooltip>
                  </div>
                  <Input
                    value={bridgeConfig.wakeup_opening_reply}
                    onChange={(e) => handleBridgeConfigChange(null, 'wakeup_opening_reply', e.target.value)}
                    style={{ width: 300 }}
                    disabled={loadingBridgeConfig}
                    placeholder={t('common.optional')}
                  />
                </div>
              </div>
            )}

            {/* WebSocket Settings */}
            <div className={styles.settingItem}>
              <Button
                type="link"
                onClick={() => toggleSection('ws')}
                style={{ padding: 0 }}
                className={styles.settingLabel}
              >
                <ToolOutlined /> {t('setting.wsSettings')}
              </Button>
              <span style={{ color: '#999', fontSize: 12 }}>
                {expandedSections.ws ? t('common.close') : t('common.edit')}
              </span>
            </div>
            {expandedSections.ws && (
              <div style={{ paddingLeft: 24, marginBottom: 16, borderLeft: 2, borderColor: '#e8e8e8', paddingBottom: 16 }}>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.wsPort')}
                  </div>
                  <Input
                    type="number"
                    min={1}
                    max={65535}
                    value={bridgeConfig.ws_port}
                    onChange={(e) => handleBridgeConfigChange(null, 'ws_port', parseInt(e.target.value) || 4399)}
                    style={{ width: 120 }}
                    disabled={loadingBridgeConfig}
                  />
                </div>
                <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                  <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                    {t('setting.wsHost')}
                  </div>
                  <Input
                    value={bridgeConfig.ws_host}
                    onChange={(e) => handleBridgeConfigChange(null, 'ws_host', e.target.value)}
                    style={{ width: 200 }}
                    disabled={loadingBridgeConfig}
                  />
                </div>
              </div>
            )}

            {/* Action buttons */}
            <div style={{ display: 'flex', gap: 12, padding: 16, borderTop: '1px solid #f0f0f0', justifyContent: 'flex-end' }}>
              <Popconfirm
                title={t('setting.xiaoaiServiceRestartConfirm')}
                description={t('setting.xiaoaiServiceRestartConfirmDesc')}
                onConfirm={handleBridgeRestart}
                okText={t('common.confirm')}
                cancelText={t('common.cancel')}
              >
                <Button type="default" loading={loadingBridgeConfig}>
                  {t('common.reload')}
                </Button>
              </Popconfirm>
              <Button type="primary" onClick={handleBridgeConfigSave} loading={loadingBridgeConfig}>
                {t('common.save')}
              </Button>
            </div>
          </div>
        </Card>

      </div>

      {/* Home Assistant authorization configuration modal */}
      <Modal
        title={t('setting.homeAssistantAuthorizationConfig')}
        open={haModalVisible}
        onOk={handleHaAuthConfirm}
        onCancel={handleHaAuthCancel}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={haFormValues}
        >
          <Form.Item
            name="base_url"
            label="URL"
            rules={[
              { required: true, message: t('setting.pleaseEnterUrl') },
              { type: 'url', message: t('setting.pleaseEnterValidUrl') }
            ]}
          >
            <Input placeholder={t('setting.pleaseEnterHomeAssistantUrl')} />
          </Form.Item>
          <Form.Item
            name="token"
            label="Token"
            rules={[
              { required: true, message: t('setting.pleaseEnterToken') }
            ]}
          >
            <Input.Password placeholder={t('setting.pleaseEnterHomeAssistantToken')} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Create API Token Modal */}
      <Modal
        title={t('setting.createToken')}
        open={tokenModalVisible}
        onOk={handleTokenModalConfirm}
        onCancel={handleTokenModalCancel}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
      >
        <Form
          form={tokenForm}
          layout="vertical"
        >
          <Form.Item
            name="name"
            label={t('setting.tokenName')}
            rules={[
              { required: true, message: t('setting.pleaseEnterTokenName') },
              { max: 50, message: t('setting.tokenNameTooLong') }
            ]}
          >
            <Input placeholder={t('setting.tokenNamePlaceholder')} />
          </Form.Item>
          <Form.Item
            name="description"
            label={t('setting.tokenDescription')}
            rules={[
              { max: 200, message: t('setting.tokenDescriptionTooLong') }
            ]}
          >
            <Input.TextArea placeholder={t('setting.tokenDescriptionPlaceholder')} rows={3} />
          </Form.Item>
          <Form.Item
            name="expires_days"
            label={t('setting.tokenExpiresDays')}
            initialValue={365}
            rules={[
              { required: true, message: t('setting.pleaseEnterExpiresDays') }
            ]}
          >
            <Input type="number" min={1} max={3650} placeholder={t('setting.tokenExpiresDaysPlaceholder')} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Token Detail Modal (show created token) */}
      <Modal
        title={t('setting.tokenCreated')}
        open={tokenDetailModalVisible}
        onCancel={() => setTokenDetailModalVisible(false)}
        footer={[
          <Button key="copy" type="primary" icon={<CopyOutlined />} onClick={() => handleCopyToken(createdToken?.token)}>
            {t('setting.copyToken')}
          </Button>,
          <Button key="close" onClick={() => setTokenDetailModalVisible(false)}>
            {t('common.close')}
          </Button>
        ]}
      >
        <div style={{ padding: '16px 0' }}>
          <Alert
            message={t('setting.tokenWarning')}
            description={t('setting.tokenWarningDesc')}
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
          />
          <div style={{ background: '#f5f5f5', padding: 16, borderRadius: 4, wordBreak: 'break-all' }}>
            <Text code style={{ fontSize: 14 }}>{createdToken?.token}</Text>
          </div>
          <div style={{ marginTop: 16 }}>
            <Text type="secondary">{t('setting.tokenName')}: {createdToken?.name}</Text>
            <br />
            <Text type="secondary">{t('setting.tokenExpiresAt')}: {formatDate(createdToken?.expires_at)}</Text>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default Setting;
