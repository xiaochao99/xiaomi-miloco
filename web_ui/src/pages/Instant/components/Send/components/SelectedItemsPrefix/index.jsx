/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useCallback } from 'react';

import SelectedItems from '../SelectedItems';
import { useChatStore } from '@/stores/chatStore';
import styles from '../../style.module.less';

  /**
   * SelectedItemsPrefix Component - Used for Sender's prefix, display selected cameras and MCP services
   * 已选择项目前缀组件 - 用于Sender的prefix，显示已选择的摄像头和MCP服务
   *
   * @returns {JSX.Element} SelectedItemsPrefix component
   */
const SelectedItemsPrefix = () => {
  // use global state
  const {
    cameraList,
    selectedCameraIds,
    mcpList,
    availableMcpServices,
    setMcpList,
    handleCameraSelect
  } = useChatStore();

  // calculate selected cameras list
  const selectedCameras = React.useMemo(() => {
    if (!cameraList || !selectedCameraIds) {return [];}
    return cameraList.filter(camera => selectedCameraIds.includes(camera.did));
  }, [cameraList, selectedCameraIds]);

  // handle camera remove
  const handleRemoveCamera = useCallback((cameraId) => {
    if (handleCameraSelect) {
      handleCameraSelect(cameraId);
    }
  }, [handleCameraSelect]);

  // handle MCP service remove
  const handleRemoveMcpService = useCallback((serviceId) => {
    const currentList = Array.isArray(mcpList) ? mcpList : [];
    if (currentList.includes(serviceId)) {
      setMcpList(currentList.filter(id => id !== serviceId));
    }
  }, [mcpList, setMcpList]);

  // if no item is selected, return null
  if (selectedCameras.length === 0 && mcpList.length === 0) {
    return null;
  }

  return (
    <div className={styles.selectedItemsContainer}>
      {/* display selected cameras */}
      {selectedCameras.length > 0 && (
        <SelectedItems
          selectedItems={selectedCameras}
          onRemoveItem={handleRemoveCamera}
          itemConfig={{
            idField: 'did',
            nameField: 'name',
            descField: 'model'
          }}
        />
      )}

      {selectedCameras.length > 0 && mcpList.length > 0 && (
        <div style={{ width: 1, height: 18, backgroundColor: 'rgba(0, 0, 0, 0.24)' }}></div>
      )}

      {/* display selected MCP services */}
      {mcpList.length > 0 && (
        <SelectedItems
          selectedItems={availableMcpServices.filter(service => mcpList.includes(service.client_id))}
          onRemoveItem={handleRemoveMcpService}
          itemConfig={{
            idField: 'client_id',
            nameField: 'server_name',
            descField: 'description'
          }}
          type="mcp"
        />
      )}
    </div>
  );
};

export default SelectedItemsPrefix;
