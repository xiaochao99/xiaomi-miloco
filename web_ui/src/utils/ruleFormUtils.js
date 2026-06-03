/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */



/**
 * rule form tool function
 * handle time conversion, cron expression etc.
 */

// trigger period options
export const TRIGGER_PERIOD_OPTIONS = [
  { label: '全天', value: 'all_day' },
  { label: '白天(早6晚6)', value: 'daytime' },
  { label: '晚上(晚6点0分01秒-第二天早5点59分59秒)', value: 'nighttime' },
  { label: '自定义时间段', value: 'custom' },
];

// weekday options for cron expression (0=Sunday, 1=Monday, ..., 6=Saturday)
export const WEEKDAY_OPTIONS = [
  { label: '周日', value: 0 },
  { label: '周一', value: 1 },
  { label: '周二', value: 2 },
  { label: '周三', value: 3 },
  { label: '周四', value: 4 },
  { label: '周五', value: 5 },
  { label: '周六', value: 6 },
];

// weekday cron value mapping (cron: 0=Sunday, 1=Monday, ..., 6=Saturday)
export const WEEKDAY_CRON_MAP = {
  0: '0', // Sunday
  1: '1', // Monday
  2: '2', // Tuesday
  3: '3', // Wednesday
  4: '4', // Thursday
  5: '5', // Friday
  6: '6', // Saturday
};

// trigger interval options (hour, minute, second)
export const TRIGGER_INTERVAL_OPTIONS = {
  hours: Array.from({ length: 24 }, (_, i) => ({ label: `${i}小时`, value: i })),
  minutes: Array.from({ length: 60 }, (_, i) => ({ label: `${i}分钟`, value: i })),
  seconds: Array.from({ length: 60 }, (_, i) => ({ label: `${i}秒`, value: i })),
};


/**
 * trigger period conversion tool
 */
export const triggerPeriodUtils = {
  periodToCron: (period, customTimeRange, weekdays = []) => {
    const weekdayStr = weekdays.length > 0
      ? weekdays.sort((a, b) => a - b).join(',')
      : '*';

    switch (period) {
      case 'all_day':
        return `* * * * ${weekdayStr}`;
      case 'daytime':
        return `* 6-17 * * ${weekdayStr}`;
      case 'nighttime':
        return `* 18-23,0-5 * * ${weekdayStr}`;
      case 'custom':
        if (!customTimeRange || !customTimeRange.startTime || !customTimeRange.endTime) {
          return `* * * * ${weekdayStr}`;
        }
        return triggerPeriodUtils.customTimeRangeToCron(customTimeRange.startTime, customTimeRange.endTime, weekdays);
      default:
        return '';
    }
  },

  cronToPeriod: (cron) => {
    if (!cron) {return { period: '', weekdays: [] };}

    try {
      const parts = cron.split(' ');
      if (parts.length !== 5) {return { period: '', weekdays: [] };}

      const [minute, hour, day, month, weekday] = parts;

      // Parse weekdays from cron
      const weekdays = triggerPeriodUtils.cronToWeekdays(weekday);

      // check if it is all day
      if (minute === '*' && hour === '*' && day === '*' && month === '*') {
        return { period: 'all_day', weekdays };
      }

      // check if it is daytime (6:00-17:59)
      if (minute === '*' && hour === '6-17' && day === '*' && month === '*') {
        return { period: 'daytime', weekdays };
      }

      // check if it is nighttime (18:00-23:59, 0:00-5:59)
      if (minute === '*' && hour === '18-23,0-5' && day === '*' && month === '*') {
        return { period: 'nighttime', weekdays };
      }

      // check if it is custom (non-preset cron)
      // any valid cron that doesn't match presets is considered custom
      return { period: 'custom', weekdays };
    } catch (error) {
      console.error('Invalid cron expression:', error);
      return { period: '', weekdays: [] };
    }
  },

  // Convert custom time range to cron expression
  customTimeRangeToCron: (startTime, endTime, weekdays = []) => {
    const [startHour, startMinute] = startTime.split(':').map(Number);
    const [endHour, endMinute] = endTime.split(':').map(Number);

    const weekdayStr = weekdays.length > 0
      ? weekdays.sort((a, b) => a - b).join(',')
      : '*';

    // Validate input
    if (isNaN(startHour) || isNaN(startMinute) || isNaN(endHour) || isNaN(endMinute)) {
      return `* * * * ${weekdayStr}`;
    }

    // If same time, return all_day
    if (startHour === endHour && startMinute === endMinute) {
      return `* * * * ${weekdayStr}`;
    }

    // Handle time ranges that cross midnight
    if (startHour < endHour || (startHour === endHour && startMinute < endMinute)) {
      // Simple range, e.g., 08:00 to 17:30
      return `* ${startHour}-${endHour} * * ${weekdayStr}`;
    } else {
      // Cross midnight, e.g., 22:00 to 06:00
      return `* ${startHour}-23,0-${endHour} * * ${weekdayStr}`;
    }
  },

  // Parse cron expression to custom time range
  cronToCustomTimeRange: (cron) => {
    if (!cron) {return null;}

    try {
      const parts = cron.split(' ');
      if (parts.length !== 5) {return null;}

      const [minute, hour] = parts;

      // Simple hour range like "8-17"
      const simpleRangeMatch = hour.match(/^(\d+)-(\d+)$/);
      if (simpleRangeMatch) {
        const startHour = parseInt(simpleRangeMatch[1], 10);
        const endHour = parseInt(simpleRangeMatch[2], 10);
        return {
          startTime: `${startHour.toString().padStart(2, '0')}:00`,
          endTime: `${endHour.toString().padStart(2, '0')}:00`,
        };
      }

      // Cross midnight range like "22-23,0-6"
      const crossMidnightMatch = hour.match(/^(\d+)-23,0-(\d+)$/);
      if (crossMidnightMatch) {
        const startHour = parseInt(crossMidnightMatch[1], 10);
        const endHour = parseInt(crossMidnightMatch[2], 10);
        return {
          startTime: `${startHour.toString().padStart(2, '0')}:00`,
          endTime: `${endHour.toString().padStart(2, '0')}:00`,
        };
      }

      return null;
    } catch (error) {
      console.error('Invalid cron expression:', error);
      return null;
    }
  },

  // Parse weekday string from cron to array of weekday numbers
  cronToWeekdays: (weekdayStr) => {
    if (!weekdayStr || weekdayStr === '*') {
      return [];
    }

    try {
      const weekdays = [];
      // Handle comma-separated values like "1,3,5" or ranges like "1-5"
      const parts = weekdayStr.split(',');
      for (const part of parts) {
        const rangeMatch = part.match(/^(\d+)-(\d+)$/);
        if (rangeMatch) {
          const start = parseInt(rangeMatch[1], 10);
          const end = parseInt(rangeMatch[2], 10);
          for (let i = start; i <= end; i++) {
            weekdays.push(i);
          }
        } else {
          const num = parseInt(part, 10);
          if (!isNaN(num)) {
            weekdays.push(num);
          }
        }
      }
      return [...new Set(weekdays)].sort((a, b) => a - b);
    } catch (error) {
      console.error('Invalid weekday expression:', error);
      return [];
    }
  },

  // get period option display text
  getPeriodLabel: (value) => {
    const option = TRIGGER_PERIOD_OPTIONS.find(opt => opt.value === value);
    return option ? option.label : '';
  },
};

/**
 * trigger interval conversion tool
 */
export const triggerIntervalUtils = {
  // convert time selector value to seconds
  timeToSeconds: (hours = 0, minutes = 0, seconds = 0) => {
    return hours * 3600 + minutes * 60 + seconds;
  },

  // convert seconds to time selector value
  secondsToTime: (totalSeconds) => {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return { hours, minutes, seconds };
  },

  // validate time selector value
  validateTime: (hours, minutes, seconds) => {
    return hours >= 0 && hours <= 23 &&
           minutes >= 0 && minutes <= 59 &&
           seconds >= 0 && seconds <= 59;
  },
};

/**
 * trigger frequency conversion tool
 */
export const triggerFrequencyUtils = {
  // convert frequency selector value to object
  timeToFrequencyObject: (periodHours = 0, periodMinutes = 0, periodSeconds = 0, frequency = 1) => {
    console.log('periodHours', periodHours, periodMinutes, periodSeconds, frequency);
    const period = triggerIntervalUtils.timeToSeconds(periodHours, periodMinutes, periodSeconds);
    return {
      frequency: Math.min(frequency, 99),
      period: period,
    };
  },

  // convert object to frequency selector value
  frequencyObjectToTime: (obj) => {
    if (!obj || typeof obj.frequency !== 'number' || typeof obj.period !== 'number') {
      return { periodHours: 0, periodMinutes: 0, periodSeconds: 0, frequency: 1 };
    }

    const time = triggerIntervalUtils.secondsToTime(obj.period);
    return {
      periodHours: time.hours,
      periodMinutes: time.minutes,
      periodSeconds: time.seconds,
      frequency: Math.min(obj.frequency, 99),
    };
  },

  // validate frequency selector value
  validateFrequency: (periodHours, periodMinutes, periodSeconds, frequency) => {
    const isValidTime = triggerIntervalUtils.validateTime(periodHours, periodMinutes, periodSeconds);
    const isValidFrequency = frequency >= 1 && frequency <= 99;
    return isValidTime && isValidFrequency;
  },
};

/**
 * form data conversion tool
 */
export const formDataUtils = {
  // convert form data to submit format
  toSubmitFormat: (formData) => {
    const {
      triggerPeriod,
      triggerIntervalHours,
      triggerIntervalMinutes,
      triggerIntervalSeconds,
      customStartTime,
      customEndTime,
      triggerWeekdays,
      ...otherData
    } = formData;

    const period = triggerPeriod ? triggerPeriodUtils.periodToCron(triggerPeriod, {
      startTime: customStartTime,
      endTime: customEndTime,
    }, triggerWeekdays || []) : triggerPeriodUtils.periodToCron('all_day', null, triggerWeekdays || []);

    return {
      ...otherData,
      period,
      interval: triggerIntervalUtils.timeToSeconds(
        triggerIntervalHours || 0,
        triggerIntervalMinutes || 0,
        triggerIntervalSeconds
      ),
    };
  },

  // convert backend data to form format
  toFormFormat: (backendData) => {
    const {
      period,
      interval,
      // frequency,
      ...otherData
    } = backendData;

    const intervalTime = triggerIntervalUtils.secondsToTime(interval || 2);
    const periodResult = triggerPeriodUtils.cronToPeriod(period);
    const periodValue = periodResult?.period || 'all_day';
    const weekdays = periodResult?.weekdays || [];

    // If it's a custom period, parse the cron to get start/end time
    let customStartTime = '08:00';
    let customEndTime = '18:00';
    if (periodValue === 'custom' && period) {
      const timeRange = triggerPeriodUtils.cronToCustomTimeRange(period);
      if (timeRange) {
        customStartTime = timeRange.startTime;
        customEndTime = timeRange.endTime;
      }
    }

    return {
      ...otherData,
      triggerPeriod: periodValue,
      triggerIntervalHours: intervalTime.hours,
      triggerIntervalMinutes: intervalTime.minutes,
      triggerIntervalSeconds: intervalTime.seconds,
      customStartTime,
      customEndTime,
      triggerWeekdays: weekdays,
    };
  },
};

