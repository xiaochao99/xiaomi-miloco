/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

export const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

export const classNames = (...classes) => {
  return classes.filter(Boolean).join(' ');
};

export const formatDataToMarkdown = (obj) => {
  if (!obj || typeof obj !== 'object') {
    return String(obj);
  }
  try {
    const jsonString = JSON.stringify(obj, null, 2);
    return `\`\`\`json\n${jsonString}\n\`\`\``;
  } catch (error) {
    return String(obj);
  }
};

export const isFirefox = () => {
  return typeof navigator !== 'undefined' && navigator.userAgent.toLowerCase().indexOf('firefox') > -1
}
