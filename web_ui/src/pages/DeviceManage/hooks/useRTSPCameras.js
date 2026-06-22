/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useState, useEffect, useCallback } from 'react';
import { message } from 'antd';
import { useTranslation } from 'react-i18next';
import { getRTSPCameras, getCameraList, createRTSPCamera, updateRTSPCamera, deleteRTSPCamera } from '@/api';

/**
 * Hook for managing all cameras (MiOT + RTSP)
 * @returns {Object} Camera management methods and state
 */
export const useRTSPCameras = () => {
  const { t } = useTranslation();
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingCamera, setEditingCamera] = useState(null);

  // Fetch all cameras (MiOT + RTSP)
  const fetchCameras = useCallback(async () => {
    setLoading(true);
    try {
      const [rtspRes, allRes] = await Promise.all([
        getRTSPCameras(),
        getCameraList()
      ]);

      const rtspCameras = (rtspRes && rtspRes.code === 0) ? (rtspRes.data || []) : [];
      const allCameras = (allRes && allRes.code === 0) ? (allRes.data || []) : [];

      // Build a set of RTSP camera DIDs
      const rtspDids = new Set(rtspCameras.map(c => c.did));

      // MiOT cameras = all cameras that are NOT in RTSP list
      const miotCameras = allCameras
        .filter(c => !rtspDids.has(c.did))
        .map(c => ({
          ...c,
          _isMiot: true,
          rtsp_url: null,
          enable_audio: false,
          transport: 'tcp',
          enabled: c.online !== false,
        }));

      // Mark RTSP cameras
      const markedRtsp = rtspCameras.map(c => ({ ...c, _isMiot: false }));

      // MiOT cameras first, then RTSP
      setCameras([...miotCameras, ...markedRtsp]);
    } catch (error) {
      console.error('Failed to fetch cameras:', error);
      message.error(t('deviceManage.rtsp.fetchFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  // Load cameras on mount
  useEffect(() => {
    fetchCameras();
  }, [fetchCameras]);

  // Create new camera
  const createCamera = async (values) => {
    try {
      const res = await createRTSPCamera(values);
      if (res && res.code === 0) {
        message.success(t('deviceManage.rtsp.createSuccess'));
        await fetchCameras();
        return true;
      } else {
        message.error(res?.message || t('deviceManage.rtsp.createFailed'));
        return false;
      }
    } catch (error) {
      console.error('Failed to create RTSP camera:', error);
      message.error(t('deviceManage.rtsp.createFailed'));
      return false;
    }
  };

  // Update camera
  const updateCamera = async (did, values) => {
    try {
      const res = await updateRTSPCamera(did, values);
      if (res && res.code === 0) {
        message.success(t('deviceManage.rtsp.updateSuccess'));
        await fetchCameras();
        return true;
      } else {
        message.error(res?.message || t('deviceManage.rtsp.updateFailed'));
        return false;
      }
    } catch (error) {
      console.error('Failed to update RTSP camera:', error);
      message.error(t('deviceManage.rtsp.updateFailed'));
      return false;
    }
  };

  // Delete camera
  const deleteCamera = async (did) => {
    try {
      const res = await deleteRTSPCamera(did);
      if (res && res.code === 0) {
        message.success(t('deviceManage.rtsp.deleteSuccess'));
        await fetchCameras();
        return true;
      } else {
        message.error(res?.message || t('deviceManage.rtsp.deleteFailed'));
        return false;
      }
    } catch (error) {
      console.error('Failed to delete RTSP camera:', error);
      message.error(t('deviceManage.rtsp.deleteFailed'));
      return false;
    }
  };

  // Open modal for creating
  const openCreateModal = () => {
    setEditingCamera(null);
    setModalVisible(true);
  };

  // Open modal for editing
  const openEditModal = (camera) => {
    setEditingCamera(camera);
    setModalVisible(true);
  };

  // Close modal
  const closeModal = () => {
    setModalVisible(false);
    setEditingCamera(null);
  };

  // Handle save (create or update)
  const handleSave = async (values) => {
    if (editingCamera) {
      return await updateCamera(editingCamera.did, values);
    } else {
      return await createCamera(values);
    }
  };

  // Toggle camera enable status
  const toggleCameraEnable = async (did, enabled) => {
    try {
      const camera = cameras.find(c => c.did === did);
      if (!camera) return false;
      
      const res = await updateRTSPCamera(did, { ...camera, enabled });
      if (res && res.code === 0) {
        message.success(enabled 
          ? t('deviceManage.rtsp.enableSuccess') 
          : t('deviceManage.rtsp.disableSuccess')
        );
        await fetchCameras();
        return true;
      } else {
        message.error(res?.message || t('deviceManage.rtsp.updateFailed'));
        return false;
      }
    } catch (error) {
      console.error('Failed to toggle camera enable status:', error);
      message.error(t('deviceManage.rtsp.updateFailed'));
      return false;
    }
  };

  return {
    cameras,
    loading,
    modalVisible,
    editingCamera,
    fetchCameras,
    createCamera,
    updateCamera,
    deleteCamera,
    openCreateModal,
    openEditModal,
    closeModal,
    handleSave,
    toggleCameraEnable
  };
};
