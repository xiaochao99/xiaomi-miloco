/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import axios from "axios";
import { message } from "antd";

const instace = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '',
  timeout: 30000,
});

// Version marker for cache busting
console.log('[HTTP] Module loaded v2 - Camera Config Fix');

instace.interceptors.request.use(
  (config) => {
    // Set Content-Type for POST/PUT requests with data
    const method = config.method?.toLowerCase();
    if ((method === 'post' || method === 'put') && config.data) {
      config.headers['Content-Type'] = 'application/json';
    }
    console.log('HTTP Request:', config.method, config.url, config.data);
    return config;
  },
  (err) => {
    message.destroy();
    return Promise.reject(err);
  }
);

instace.interceptors.response.use(
  (response) => {
    console.log('HTTP Response:', response.config.url, response.status, response.data);
    if (response.status === 200 && response.data) {
      return response.data
    } else {
      if(response.data?.message) {
        message.error(response.data.message)
      }
      return response.data || null
    }
  },
  (err) => {
    console.error('HTTP Error:', err.config?.url, err.response?.status, err.response?.data, err.message);
    if(err?.response?.data?.message) {
      message.error(err?.response?.data?.message)
    }
    const origin = window.location && window.location.origin ? window.location.origin : '';
    if (err?.response?.status === 401) {
      const { pathname } = window.location
      if (pathname !== "/login") {
        window.location.href = `${origin}/login`;
      }
    }
    if (err?.response?.status === 500) {
      window.location.href = `${origin}/500`;
    }

    // Return error response data if available, otherwise return error object
    if (err?.response?.data) {
      return Promise.resolve(err.response.data);
    }
    // Return a proper error object that the frontend can handle
    return Promise.resolve({ code: -1, message: err.message || 'Request failed', data: null });
  }
);

const callapi = (method = "GET", url, data = {}, timeout = null) => {
  const isGet = method === "GET";
  const config = {
    method,
    url,
    params: isGet ? data : {},
    data: isGet ? {} : data,
    headers: isGet ? {} : {
      'Content-Type': 'application/json'
    }
  };

  if (timeout !== null) {
    config.timeout = timeout;
  }

  console.log('callapi config:', { method, url, data, headers: config.headers });
  return instace(config);
};

export const getApi = (url, data, timeout = null) => callapi("GET", url, data, timeout);
export const postApi = (url, data, timeout = null) => callapi("POST", url, data, timeout);
export const putApi = (url, data, timeout = null) => callapi("PUT", url, data, timeout);
export const deleteApi = (url, timeout = null) => callapi("DELETE", url, {}, timeout);
