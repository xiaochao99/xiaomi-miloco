/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import {Select, Switch, Button, Form, Input, Modal, message, Divider, Space, Typography, Segmented, Table, Popconfirm, Tag, Tooltip, Alert, Upload, List, Spin, Checkbox} from 'antd';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { SettingOutlined, GlobalOutlined, BulbOutlined, KeyOutlined, ToolOutlined, PlusOutlined, CopyOutlined, DeleteOutlined, VideoCameraOutlined, UploadOutlined, AudioOutlined, SoundOutlined, ExperimentOutlined } from '@ant-design/icons';
import { setHAAuth, getHAAuth, getLanguage, setLanguage, getAPITokenList, createAPIToken, deleteAPIToken, getCameraConfig, setCameraConfig as saveCameraConfig, getRTSPServerConfig, setRTSPServerConfig, getXiaoAIConfig, updateXiaoAIConfig, restartXiaoAI, listVoiceClones, uploadVoiceClone, deleteVoiceClone, synthesizeWithVoiceClone, voiceDesignTTS, getUpdateStatus, checkForUpdates, applyUpdate, uploadUpdatePackage, getUpdateLog, listBackups, rollbackToBackup, getSystemStatus } from '@/api';
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
  const navigate = useNavigate();
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

  // System Update states
  const [updateStatus, setUpdateStatus] = useState({
    current_version: 'unknown',
    latest_version: null,
    update_available: false,
    last_check: null,
    last_update: null,
    is_updating: false,
    update_log: null
  });
  const [backups, setBackups] = useState([]);
  const [loadingUpdate, setLoadingUpdate] = useState(false);
  const [updateLogVisible, setUpdateLogVisible] = useState(false);
  const [updateLog, setUpdateLog] = useState('');
  const [rollbackModalVisible, setRollbackModalVisible] = useState(false);
  const [updateContentVisible, setUpdateContentVisible] = useState(false);
  const [updateContentData, setUpdateContentData] = useState(null);
  const [updateConfigChecked, setUpdateConfigChecked] = useState(false);

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
      speed: 1.0,
      mimo_tts_model: 'mimo-v2.5-tts',
      voice_design_description: ''
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

  // Voice clone states
  const [voiceClones, setVoiceClones] = useState([]);
  const [loadingVoiceClones, setLoadingVoiceClones] = useState(false);
  const [voiceCloneName, setVoiceCloneName] = useState('');
  const [voiceCloneUploading, setVoiceCloneUploading] = useState(false);
  const [voiceCloneTestText, setVoiceCloneTestText] = useState('');
  const [voiceCloneTesting, setVoiceCloneTesting] = useState(false);

  // Voice design states
  const [voiceDesignDesc, setVoiceDesignDesc] = useState('');
  const [voiceDesignText, setVoiceDesignText] = useState('');
  const [voiceDesigning, setVoiceDesigning] = useState(false);

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

  // Load Voice Clones when TTS section is open and model is voiceclone
  useEffect(() => {
    if (expandedSections.tts && bridgeConfig.tts?.mimo_tts_model === 'mimo-v2.5-tts-voiceclone') {
      fetchVoiceClones();
    }
  }, [expandedSections.tts, bridgeConfig.tts?.mimo_tts_model]);

  // Load System Update Status
  useEffect(() => {
    fetchUpdateStatus();
  }, []);

  const fetchBridgeConfig = async () => {
    setLoadingBridgeConfig(true);
    try {
      const res = await getXiaoAIConfig();
      if (res && res.code === 0) {
        setBridgeConfig(res.data);
        if (res.data?.tts?.voice_design_description) {
          setVoiceDesignDesc(res.data.tts.voice_design_description);
        }
      }
    } catch (error) {
      console.error('Failed to load Xiaomi Bridge config:', error);
    } finally {
      setLoadingBridgeConfig(false);
    }
  };

  // System Update functions
  const fetchUpdateStatus = async () => {
    try {
      const res = await getUpdateStatus();
      if (res && res.code === 0) {
        setUpdateStatus(res.data);
      }
    } catch (error) {
      console.error('Failed to load update status:', error);
    }
  };

  const handleCheckUpdates = async () => {
    setLoadingUpdate(true);
    try {
      const res = await checkForUpdates();
      if (res && res.code === 0) {
        setUpdateStatus(prev => ({
          ...prev,
          update_available: res.data.update_available,
          latest_version: res.data.latest_version,
          last_check: res.data.check_time
        }));
        if (res.data.update_available) {
          setUpdateContentData({
            latest_version: res.data.latest_version,
            current_version: res.data.current_version,
            release_body: res.data.release_body || '',
            release_name: res.data.release_name || '',
            release_url: res.data.release_url || '',
            published_at: res.data.published_at || '',
            has_config: res.data.has_config || false,
            pip_sync: res.data.pip_sync || false
          });
          setUpdateConfigChecked(false);
          setUpdateContentVisible(true);
        } else {
          message.info(t('setting.noUpdateAvailable'));
        }
      } else {
        message.error(res?.message || t('setting.checkUpdateFailed'));
      }
    } catch (error) {
      console.error('Failed to check updates:', error);
      message.error(t('setting.checkUpdateFailed'));
    } finally {
      setLoadingUpdate(false);
    }
  };

  const handleApplyUpdate = async (version = null, updateConfig = false) => {
    setLoadingUpdate(true);
    try {
      const res = await applyUpdate(version, updateConfig);
      if (res && res.code === 0) {
        message.success(t('setting.updateStarted'));
        // Poll for update status
        const pollInterval = setInterval(async () => {
          const logRes = await getUpdateLog();
          if (logRes && logRes.code === 0) {
            setUpdateLog(logRes.data.log);
            if (!logRes.data.is_updating) {
              clearInterval(pollInterval);
              fetchUpdateStatus();
              message.success(t('setting.updateCompleted'));
            }
          }
        }, 2000);
      } else {
        message.error(res?.message || t('setting.updateFailed'));
      }
    } catch (error) {
      console.error('Failed to apply update:', error);
      message.error(t('setting.updateFailed'));
    } finally {
      setLoadingUpdate(false);
    }
  };

  const handleLocalUpload = async (file) => {
    if (!file.name.endsWith('.tar.gz')) {
      message.error(t('setting.invalidPackageFormat'));
      return false;
    }
    setLoadingUpdate(true);
    try {
      const res = await uploadUpdatePackage(file);
      if (res && res.code === 0) {
        message.success(t('setting.updateStarted'));
        // Poll for update status
        const pollInterval = setInterval(async () => {
          const logRes = await getUpdateLog();
          if (logRes && logRes.code === 0) {
            setUpdateLog(logRes.data.log);
            if (!logRes.data.is_updating) {
              clearInterval(pollInterval);
              fetchUpdateStatus();
              message.success(t('setting.updateCompleted'));
            }
          }
        }, 2000);
      } else {
        message.error(res?.message || t('setting.updateFailed'));
      }
    } catch (error) {
      console.error('Failed to apply local update:', error);
      message.error(t('setting.updateFailed'));
    } finally {
      setLoadingUpdate(false);
    }
    return false; // Prevent default Upload behavior
  };

  const handleViewLog = async () => {
    try {
      const res = await getUpdateLog();
      if (res && res.code === 0) {
        setUpdateLog(res.data.log);
        setUpdateLogVisible(true);
      }
    } catch (error) {
      console.error('Failed to get update log:', error);
    }
  };

  const handleListBackups = async () => {
    try {
      const res = await listBackups();
      if (res && res.code === 0) {
        setBackups(res.data.backups || []);
        setRollbackModalVisible(true);
      }
    } catch (error) {
      console.error('Failed to list backups:', error);
    }
  };

  const handleRollback = async (backupName) => {
    setLoadingUpdate(true);
    try {
      const res = await rollbackToBackup(backupName);
      if (res && res.code === 0) {
        message.success(t('setting.rollbackSuccess'));
        fetchUpdateStatus();
        setRollbackModalVisible(false);
      } else {
        message.error(res?.message || t('setting.rollbackFailed'));
      }
    } catch (error) {
      console.error('Failed to rollback:', error);
      message.error(t('setting.rollbackFailed'));
    } finally {
      setLoadingUpdate(false);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString();
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

  const fetchVoiceClones = async () => {
    setLoadingVoiceClones(true);
    try {
      const res = await listVoiceClones();
      if (res && res.code === 0) {
        setVoiceClones(res.data || []);
      }
    } catch (error) {
      console.error('Failed to load voice clones:', error);
    } finally {
      setLoadingVoiceClones(false);
    }
  };

  const handleVoiceCloneUpload = async (file) => {
    console.log('[VoiceClone] Upload called:', { voiceCloneName, fileType: typeof file, fileName: file?.name });
    if (!voiceCloneName.trim()) {
      message.warning(t('setting.voiceCloneNamePlaceholder'));
      return false;
    }
    setVoiceCloneUploading(true);
    try {
      const res = await uploadVoiceClone(file, voiceCloneName.trim());
      console.log('[VoiceClone] Upload result:', res);
      if (res && res.code === 0) {
        message.success(t('common.addSuccess'));
        setVoiceCloneName('');
        fetchVoiceClones();
      } else {
        message.error(res?.message || t('common.addFail'));
      }
    } catch (error) {
      console.error('[VoiceClone] Upload error:', error);
      message.error(t('common.addFail'));
    } finally {
      setVoiceCloneUploading(false);
    }
    return false;
  };

  const handleVoiceCloneDelete = async (cloneId) => {
    try {
      const res = await deleteVoiceClone(cloneId);
      if (res && res.code === 0) {
        message.success(t('common.deleteSuccess'));
        fetchVoiceClones();
      } else {
        message.error(res?.message || t('common.deleteFail'));
      }
    } catch (error) {
      message.error(t('common.deleteFail'));
    }
  };

  const handleVoiceCloneTest = async (cloneId) => {
    const text = voiceCloneTestText.trim() || t('setting.voiceCloneTestText');
    setVoiceCloneTesting(true);
    try {
      const res = await synthesizeWithVoiceClone({
        text,
        mimo_model: 'mimo-v2.5-tts-voiceclone',
        voice: cloneId,
      });
      if (res && res.code === 0) {
        message.success(t('common.success'));
      } else {
        message.error(res?.message || t('common.fail'));
      }
    } catch (error) {
      message.error(t('common.fail'));
    } finally {
      setVoiceCloneTesting(false);
    }
  };

  const handleVoiceDesignPreview = async () => {
    if (!voiceDesignDesc.trim()) {
      message.warning(t('setting.voiceDesignDescriptionDesc'));
      return;
    }
    if (!voiceDesignText.trim()) {
      message.warning(t('setting.voiceDesignTextPlaceholder'));
      return;
    }
    setVoiceDesigning(true);
    try {
      const res = await voiceDesignTTS({
        description: voiceDesignDesc.trim(),
        text: voiceDesignText.trim(),
      });
      if (res && res.code === 0) {
        message.success(t('common.success'));
      } else {
        message.error(res?.message || t('common.fail'));
      }
    } catch (error) {
      message.error(t('common.fail'));
    } finally {
      setVoiceDesigning(false);
    }
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
                    <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                      <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                        {t('setting.mimoTtsModel')}
                      </div>
                      <Select
                        value={bridgeConfig.tts?.mimo_tts_model || 'mimo-v2.5-tts'}
                        onChange={(value) => handleBridgeConfigChange('tts', 'mimo_tts_model', value)}
                        style={{ width: 320 }}
                        disabled={loadingBridgeConfig}
                      >
                        <Option value="mimo-v2.5-tts">{t('setting.mimoTtsModelV25')}</Option>
                        <Option value="mimo-v2.5-tts-voicedesign">{t('setting.mimoTtsModelVoiceDesign')}</Option>
                        <Option value="mimo-v2.5-tts-voiceclone">{t('setting.mimoTtsModelVoiceClone')}</Option>
                      </Select>
                    </div>
                    <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                      <div className={styles.settingLabel} style={{ fontWeight: 'normal' }}>
                        <Tooltip title={t('setting.ttsAudioTagDesc')}>
                          <span>{t('setting.ttsAudioTagInfo')} <span style={{ color: '#999', fontSize: 12 }}>(?)</span></span>
                        </Tooltip>
                      </div>
                    </div>

                    {/* Voice Design Section */}
                    {bridgeConfig.tts?.mimo_tts_model === 'mimo-v2.5-tts-voicedesign' && (
                      <div style={{ margin: '8px 0', padding: 12, background: '#fafafa', borderRadius: 8, border: '1px solid #f0f0f0' }}>
                        <div style={{ fontWeight: 500, marginBottom: 8 }}>
                          <ExperimentOutlined /> {t('setting.mimoTtsModelVoiceDesign')}
                        </div>
                        <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                          <div className={styles.settingLabel} style={{ fontWeight: 'normal', fontSize: 13 }}>
                            {t('setting.voiceDesignDescription')}
                            <Tooltip title={t('setting.voiceDesignDescriptionDesc')}>
                              <span style={{ marginLeft: 4, color: '#999', fontSize: 12 }}>(?)</span>
                            </Tooltip>
                          </div>
                          <Input.TextArea
                            rows={2}
                            value={voiceDesignDesc}
                            onChange={(e) => {
                              setVoiceDesignDesc(e.target.value);
                              handleBridgeConfigChange('tts', 'voice_design_description', e.target.value);
                            }}
                            placeholder={t('setting.voiceDesignDescriptionDesc')}
                            style={{ width: 300 }}
                          />
                        </div>
                        <div className={styles.settingItem} style={{ borderBottom: 'none' }}>
                          <div className={styles.settingLabel} style={{ fontWeight: 'normal', fontSize: 13 }}>
                            {t('setting.voiceDesignText')}
                          </div>
                          <Input.TextArea
                            rows={2}
                            value={voiceDesignText}
                            onChange={(e) => setVoiceDesignText(e.target.value)}
                            placeholder={t('setting.voiceDesignTextPlaceholder')}
                            style={{ width: 300 }}
                          />
                        </div>
                        <div style={{ textAlign: 'right', marginTop: 8 }}>
                          <Button
                            type="primary"
                            size="small"
                            icon={<SoundOutlined />}
                            loading={voiceDesigning}
                            onClick={handleVoiceDesignPreview}
                            disabled={!voiceDesignDesc.trim() || !voiceDesignText.trim()}
                          >
                            {voiceDesigning ? t('setting.voiceDesignPreviewing') : t('setting.voiceDesignPreview')}
                          </Button>
                        </div>
                      </div>
                    )}

                    {/* Voice Clone Section */}
                    {bridgeConfig.tts?.mimo_tts_model === 'mimo-v2.5-tts-voiceclone' && (
                      <div style={{ margin: '8px 0', padding: 12, background: '#fafafa', borderRadius: 8, border: '1px solid #f0f0f0' }}>
                        <div style={{ fontWeight: 500, marginBottom: 8 }}>
                          <AudioOutlined /> {t('setting.voiceCloneTitle')}
                        </div>
                        <div style={{ marginBottom: 8, fontSize: 12, color: '#666' }}>
                          {t('setting.voiceCloneUploadDesc')}
                        </div>
                        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                          <Input
                            value={voiceCloneName}
                            onChange={(e) => setVoiceCloneName(e.target.value)}
                            placeholder={t('setting.voiceCloneNamePlaceholder')}
                            style={{ flex: 1 }}
                            size="small"
                          />
                          <Upload
                            accept=".mp3,.wav"
                            showUploadList={false}
                            beforeUpload={handleVoiceCloneUpload}
                          >
                            <Button
                              type="primary"
                              size="small"
                              icon={<UploadOutlined />}
                              loading={voiceCloneUploading}
                              disabled={!voiceCloneName.trim()}
                            >
                              {voiceCloneUploading ? t('setting.voiceCloneUploading') : t('setting.voiceCloneUpload')}
                            </Button>
                          </Upload>
                        </div>
                        <div style={{ marginBottom: 8 }}>
                          <Input
                            size="small"
                            value={voiceCloneTestText}
                            onChange={(e) => setVoiceCloneTestText(e.target.value)}
                            placeholder={t('setting.voiceCloneTestTextPlaceholder')}
                            style={{ width: '100%' }}
                          />
                        </div>
                        {loadingVoiceClones ? (
                          <div style={{ textAlign: 'center', padding: 12 }}><Spin size="small" /></div>
                        ) : voiceClones.length === 0 ? (
                          <div style={{ textAlign: 'center', padding: 12, color: '#999', fontSize: 13 }}>
                            {t('setting.voiceCloneEmpty')}
                          </div>
                        ) : (
                          <List
                            size="small"
                            dataSource={voiceClones}
                            renderItem={(item) => (
                              <List.Item
                                actions={[
                                  <Button
                                    key="test"
                                    type="link"
                                    size="small"
                                    icon={<SoundOutlined />}
                                    loading={voiceCloneTesting}
                                    onClick={() => handleVoiceCloneTest(item.id)}
                                  >
                                    {t('setting.voiceCloneTest')}
                                  </Button>,
                                  <Popconfirm
                                    key="delete"
                                    title={t('setting.voiceCloneDeleteConfirm')}
                                    onConfirm={() => handleVoiceCloneDelete(item.id)}
                                  >
                                    <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                                      {t('setting.voiceCloneDelete')}
                                    </Button>
                                  </Popconfirm>
                                ]}
                              >
                                <List.Item.Meta
                                  title={item.voice_name}
                                  description={`${item.mime_type} - ${new Date(item.created_at * 1000).toLocaleString()}`}
                                />
                              </List.Item>
                            )}
                          />
                        )}
                      </div>
                    )}
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

        {/* System Update */}
        <Card className={styles.settingCard} contentClassName={styles.settingCardContent}>
          <div className={styles.settingCardTitle}>
            <Space>
              <ToolOutlined />
              {t('setting.systemUpdate')}
            </Space>
          </div>
          <div className={styles.settingCardItemList}>
            {/* Current Version */}
            <div className={styles.settingItem}>
              <div className={styles.settingLabel}>
                <SettingOutlined /> {t('setting.currentVersion')}
              </div>
              <Text>{updateStatus.current_version}</Text>
            </div>

            {/* Update Status */}
            <div className={styles.settingItem}>
              <div className={styles.settingLabel}>
                <SettingOutlined /> {t('setting.updateStatus')}
              </div>
              <Space>
                {updateStatus.update_available ? (
                  <Tag color="orange">{t('setting.updateAvailable')}</Tag>
                ) : (
                  <Tag color="green">{t('setting.upToDate')}</Tag>
                )}
                {updateStatus.last_check && (
                  <Text type="secondary">
                    {t('setting.lastCheck')}: {formatDate(updateStatus.last_check)}
                  </Text>
                )}
              </Space>
            </div>

            {/* Latest Version */}
            {updateStatus.update_available && updateStatus.latest_version && (
              <div className={styles.settingItem}>
                <div className={styles.settingLabel}>
                  <SettingOutlined /> {t('setting.latestVersion')}
                </div>
                <Text type="warning">{updateStatus.latest_version}</Text>
              </div>
            )}

            {/* Action Buttons */}
            <div style={{ display: 'flex', gap: 12, padding: 16, borderTop: '1px solid #f0f0f0', justifyContent: 'flex-end' }}>
              <Button 
                onClick={handleCheckUpdates} 
                loading={loadingUpdate}
              >
                {t('setting.checkUpdates')}
              </Button>
              
              {updateStatus.update_available && (
                <Popconfirm
                  title={t('setting.confirmUpdate')}
                  description={t('setting.confirmUpdateDesc')}
                  onConfirm={() => handleApplyUpdate()}
                  okText={t('common.confirm')}
                  cancelText={t('common.cancel')}
                >
                  <Button 
                    type="primary" 
                    loading={loadingUpdate}
                  >
                    {t('setting.applyUpdate')}
                  </Button>
                </Popconfirm>
              )}
              
              <Button onClick={handleViewLog}>
                {t('setting.viewLog')}
              </Button>
              
              <Button onClick={handleListBackups}>
                {t('setting.rollback')}
              </Button>
              
              <Upload
                accept=".tar.gz"
                showUploadList={false}
                beforeUpload={handleLocalUpload}
              >
                <Button icon={<UploadOutlined />}>
                  {t('setting.localUpload')}
                </Button>
              </Upload>
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

      {/* Update Log Modal */}
      <Modal
        title={t('setting.updateLog')}
        open={updateLogVisible}
        onCancel={() => setUpdateLogVisible(false)}
        footer={[
          <Button key="close" onClick={() => setUpdateLogVisible(false)}>
            {t('common.close')}
          </Button>
        ]}
        width={800}
      >
        <div style={{ 
          background: '#f5f5f5', 
          padding: 16, 
          borderRadius: 4, 
          maxHeight: '60vh', 
          overflow: 'auto',
          fontFamily: 'monospace',
          fontSize: 12,
          whiteSpace: 'pre-wrap'
        }}>
          {updateLog || t('setting.noUpdateLog')}
        </div>
      </Modal>

      {/* Update Content Modal */}
      <Modal
        title={t('setting.updateContent')}
        open={updateContentVisible}
        onCancel={() => setUpdateContentVisible(false)}
        footer={[
          <Button key="later" onClick={() => setUpdateContentVisible(false)}>
            {t('setting.updateLater')}
          </Button>,
          <Button
            key="update"
            type="primary"
            onClick={() => {
              handleApplyUpdate(updateContentData?.latest_version, updateConfigChecked);
              setUpdateContentVisible(false);
            }}
          >
            {t('setting.updateNow')}
          </Button>
        ]}
        width={640}
      >
        {updateContentData && (
          <div>
            <div style={{ marginBottom: 16 }}>
              <Text>
                {t('setting.updateNewVersionDesc', {
                  current: updateContentData.current_version,
                  latest: updateContentData.latest_version
                })}
              </Text>
              {updateContentData.published_at && (
                <Text type="secondary" style={{ marginLeft: 12 }}>
                  {formatDate(updateContentData.published_at)}
                </Text>
              )}
            </div>
            {updateContentData.has_config && (
              <div style={{ marginBottom: 12 }}>
                <Checkbox
                  checked={updateConfigChecked}
                  onChange={(e) => setUpdateConfigChecked(e.target.checked)}
                >
                  {t('setting.updateConfigCheckbox')}
                </Checkbox>
              </div>
            )}
            {updateContentData.pip_sync && (
              <div style={{ marginBottom: 12 }}>
                <Alert
                  message={t('setting.pipSyncNotice')}
                  type="info"
                  showIcon
                />
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
              {updateContentData.release_body ? (
                <ReactMarkdown>{updateContentData.release_body}</ReactMarkdown>
              ) : (
                t('setting.noUpdateLog')
              )}
            </div>
          </div>
        )}
      </Modal>

      {/* Rollback Modal */}
      <Modal
        title={t('setting.rollbackToBackup')}
        open={rollbackModalVisible}
        onCancel={() => setRollbackModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setRollbackModalVisible(false)}>
            {t('common.close')}
          </Button>
        ]}
      >
        <div>
          {backups.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 24, color: '#999' }}>
              {t('setting.noBackupsAvailable')}
            </div>
          ) : (
            <List
              dataSource={backups}
              renderItem={(backup) => (
                <List.Item
                  actions={[
                    <Popconfirm
                      key="rollback"
                      title={t('setting.confirmRollback')}
                      description={t('setting.confirmRollbackDesc')}
                      onConfirm={() => handleRollback(backup)}
                      okText={t('common.confirm')}
                      cancelText={t('common.cancel')}
                    >
                      <Button type="link" loading={loadingUpdate}>
                        {t('setting.rollback')}
                      </Button>
                    </Popconfirm>
                  ]}
                >
                  <List.Item.Meta
                    title={backup}
                    description={t('setting.backupTime', { time: formatDate(backup) })}
                  />
                </List.Item>
              )}
            />
          )}
        </div>
      </Modal>
    </div>
  );
};

export default Setting;
