/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { Select } from 'antd';
import styles from './index.module.less';

/**
 * TimeSelector Component - Time selection component with hours, minutes and seconds
 * 时间选择器组件 - 包含小时、分钟和秒的时间选择组件
 *
 * @param {Object} props - Component props
 * @param {number} [props.hours=0] - Selected hours value
 * @param {number} [props.minutes=0] - Selected minutes value
 * @param {number} [props.seconds=0] - Selected seconds value
 * @param {Function} props.onHoursChange - Hours change callback
 * @param {Function} props.onMinutesChange - Minutes change callback
 * @param {Function} props.onSecondsChange - Seconds change callback
 * @param {Array} [props.hoursOptions=[]] - Available hours options
 * @param {Array} [props.minutesOptions=[]] - Available minutes options
 * @param {Array} [props.secondsOptions=[]] - Available seconds options
 * @param {string} [props.className=''] - Additional CSS class
 * @param {boolean} [props.disabled=false] - Whether the selector is disabled
 * @returns {JSX.Element} Time selector component
 */
const TimeSelector = ({
  hours = 0,
  minutes = 0,
  seconds = 0,
  onHoursChange,
  onMinutesChange,
  onSecondsChange,
  hoursOptions = [],
  minutesOptions = [],
  secondsOptions = [],
  className = '',
  disabled = false,
}) => {
  return (
    <div className={`${styles.timeSelector} ${className}`}>
      <Select
        value={hours}
        onChange={onHoursChange}
        options={hoursOptions}
        className={styles.timeSelect}
        disabled={disabled}
        placeholder="hh"
      />
      <span className={styles.timeSeparator}>:</span>
      <Select
        value={minutes}
        onChange={onMinutesChange}
        options={minutesOptions}
        className={styles.timeSelect}
        disabled={disabled}
        placeholder="mm"
      />
      <span className={styles.timeSeparator}>:</span>
      <Select
        value={seconds}
        onChange={(value) => {
          onSecondsChange(value);
        }}
        options={secondsOptions}
        className={styles.timeSelect}
        disabled={disabled}
        placeholder="ss"
      />
    </div>
  );
};

export default TimeSelector;
