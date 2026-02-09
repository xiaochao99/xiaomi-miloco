/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react'
import { Switch, Button, Popconfirm } from 'antd'
import { useTranslation } from 'react-i18next';
import { EditOutlined, DeleteOutlined } from '@ant-design/icons'
import styles from './index.module.less'

/**
 * ListItem Component - Reusable list item with title, description, actions and switch
 * 列表项组件 - 可复用的列表项，包含标题、描述、操作按钮和开关
 *
 * @param {Object} props - Component props
 * @param {string} props.title - Item title
 * @param {string} props.type - Item type badge
 * @param {string} props.description - Item description
 * @param {string} props.meta - Item metadata
 * @param {boolean} [props.showSwitch=false] - Whether to show switch control
 * @param {boolean} [props.switchValue=false] - Switch current value
 * @param {Function} props.onSwitchChange - Switch change callback
 * @param {boolean} [props.showEdit=false] - Whether to show edit button
 * @param {boolean} [props.showDelete=false] - Whether to show delete button
 * @param {Function} props.onEdit - Edit button callback
 * @param {Function} props.onDelete - Delete button callback
 * @param {string} [props.deleteConfirmTitle=''] - Custom delete confirmation title
 * @param {Function} props.onClick - Item click callback
 * @param {string} [props.className] - Additional CSS class
 * @param {string} [props.titleClassName=''] - Title CSS class
 * @param {React.ReactNode} props.rightContent - Custom right side content
 * @param {React.ReactNode} props.customInfo - Custom info content
 * @returns {JSX.Element} List item component
 */
const ListItem = ({
  title,
  type,
  description,
  meta,
  showSwitch = false,
  switchValue = false,
  onSwitchChange,
  showEdit = false,
  showDelete = false,
  onEdit,
  onDelete,
  deleteConfirmTitle = '',
  onClick,
  className,
  titleClassName='',
  rightContent,
  customInfo,
}) => {
  const { t } = useTranslation();
  const deletePopconfirm = deleteConfirmTitle ? deleteConfirmTitle : t('common.confirmDelete');
  return (
    <div
      className={`${styles.listItem} ${className || ''}`}
      onClick={onClick}
    >
      <div className={styles.content}>
        {title && (
          <div className={styles.header} style={{
            marginBottom: description || meta || customInfo ? '4px' : '0px'
          }}>
            <span className={`${styles.title} ${titleClassName}`}>{title}</span>
            {type && (
              <span className={styles.type}>{type}</span>
            )}
          </div>
        )}
        {description && (
          <div className={styles.desc}>{description}</div>
        )}
        {meta && (
          <div className={styles.meta}>{meta}</div>
        )}
        {customInfo && customInfo}
      </div>

      <div className={styles.actions}>
        {showSwitch && (
          <Switch
            checked={switchValue}
            onChange={onSwitchChange}
            size="default"
            onClick={(checked, event) => {
              event.stopPropagation()
            }}
          />
        )}

        {(showEdit || showDelete || rightContent) && (
          <div className={styles.actionsBtns}>
            {showEdit && (
              <Button
                type="link"
                icon={<EditOutlined />}
                onClick={(event) => {
                  event.stopPropagation()
                  onEdit && onEdit()
                }}
                style={{ color: 'rgba(191, 191, 191, 1)' }}
              />
            )}
            {showDelete && (
              <Popconfirm
                title={deletePopconfirm}
                onConfirm={(event) => {
                  event && event.stopPropagation()
                  onDelete && onDelete()
                }}
                okText={t('common.confirm')}
                cancelText={t('common.cancel')}
                onClick={(event) => event.stopPropagation()}
              >
                <Button
                  type="link"
                  icon={<DeleteOutlined />}
                  danger
                  style={{ color: 'rgba(191, 191, 191, 1)' }}
                  onClick={(event) => event.stopPropagation()}
                />
              </Popconfirm>
            )}

            {rightContent && rightContent}
          </div>
        )}
      </div>
    </div>
  )
}

export default ListItem
