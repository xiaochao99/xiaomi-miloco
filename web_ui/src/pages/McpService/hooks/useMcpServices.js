/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useState, useEffect } from 'react';
import { message } from 'antd';
import { useTranslation } from 'react-i18next';
import { getMCPService, setMCPService, updateMCPService, deleteMCPService } from '@/api';

/**
 * useMcpServices - MCP service management hooks
 * MCP服务管理钩子
 */
export const useMcpServices = () => {
  const { t } = useTranslation();
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(true);

  // load MCP service list
  const loadServices = async () => {
    setLoading(true);
    try {
      const response = await getMCPService();

      let servicesData = [];
      if (response?.code === 0 && response?.data) {
        const { configs = [] } = response.data;
        servicesData = Array.isArray(configs) ? configs : [];
      }

      setServices(servicesData);
    } catch (error) {
      console.error('Failed to load MCP services:', error);
      message.error(t('mcpService.loadFailed'));
      setServices([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSwitch = async (id, checked) => {
    try {
      const service = services.find(s => s.id === id);
      if (!service) {return;}

      const updatedService = { ...service, enable: checked };
      const response = await updateMCPService(id, updatedService);

      if (response?.code === 0) {
        await loadServices();
        message.success(checked ? t('mcpService.serviceEnabled') : t('mcpService.serviceDisabled'));
      } else {
        message.error(t('mcpService.updateFailed'));
      }
    } catch (error) {
      console.error('Failed to update service status:', error);
      message.error(t('mcpService.updateFailed'));
    }
  };

  const handleDelete = async (id) => {
    try {
      const response = await deleteMCPService(id);
      if (response?.code === 0) {
        await loadServices();
        message.success(t('mcpService.serviceDeleted'));
      } else {
        message.error(t('mcpService.deleteFailed'));
      }
    } catch (error) {
      console.error('Failed to delete service:', error);
      message.error(t('mcpService.deleteFailed'));
    }
  };

  const createService = async (apiData) => {
    try {
      const response = await setMCPService(apiData);
      if (response?.code === 0) {
        await loadServices();
        message.success(t('mcpService.serviceAdded'));
        return { success: true };
      } else {
        message.error(t('mcpService.serviceAddedFailed'));
        return { success: false };
      }
    } catch (error) {
      console.error('Failed to create service:', error);
      message.error(t('mcpService.serviceAddedFailed'));
      return { success: false };
    }
  };

  const updateService = async (id, apiData) => {
    try {
      const response = await updateMCPService(id, apiData);
      if (response?.code === 0) {
        await loadServices();
        message.success(response?.message || t('mcpService.serviceEdited'));
        return { success: true };
      } else {
        message.error(t('mcpService.serviceEditedFailed'));
        return { success: false };
      }
    } catch (error) {
      console.error('Failed to update service:', error);
      message.error(t('mcpService.serviceEditedFailed'));
      return { success: false };
    }
  };

  useEffect(() => {
    loadServices();
  }, []);

  return {
    services,
    loading,
    loadServices,
    handleSwitch,
    handleDelete,
    createService,
    updateService,
  };
};
