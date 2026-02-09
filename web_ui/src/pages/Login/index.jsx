/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useCallback, useEffect, useState, useRef } from "react"
import CryptoJS from 'crypto-js'
import { useTranslation } from 'react-i18next';
import { useNavigate } from "react-router-dom"
import { Button, Input, message } from 'antd'
import { EyeInvisibleOutlined, EyeOutlined } from '@ant-design/icons'
import { getJudgeLogin, getPinLogin } from "@/api"
import { ContentModal, LanguageSwitcher } from "@/components";
import styles from './index.module.less'

/**
 * Login Page - User authentication page with PIN code login
 * 登录页面 - 使用PIN码进行用户身份验证的页面
 *
 * @returns {JSX.Element} Login page component
 */
const Login = () => {
  const [pin, setPin] = useState("")
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const inputRef = useRef(null)
  const navigate = useNavigate()
  const { t } = useTranslation();

  useEffect(() => {
    const fetchData = async () => {
      const res = await getJudgeLogin()
      const { code = 0, data: { is_registered } } = res
      if (code === 0 && !is_registered) {
        navigate("/setup")
        return
      }
    }
    fetchData()
    inputRef.current?.focus()
  }, [])

  const handleSubmit = useCallback(async (inputPin) => {
    if (loading) {return;}
    if (inputPin.length !== 6) {return;}
    setLoading(true)
    const res = await getPinLogin({ username: 'admin', password: CryptoJS.MD5(inputPin).toString() })
    setLoading(false)
    if (res?.code === 0) {
      message.success(t('login.loginSuccess'))
      navigate("/home")
    } else {
      message.error(t('login.loginFail'))
    }
  }, [loading, t, navigate])

  return (
    <ContentModal>
      <LanguageSwitcher
        size="small"
        showIcon={true}
        showLabel={false}
        className={styles.loginLanguageSwitcher}
      />

      <h1 className={styles.title}>{t('login.pleaseLogin')}</h1>
      <div className={styles.form}>
        <div className={styles.inputGroup}>
          <div className={styles.label}>
            {t('login.inputPin')}
          </div>
          <div className={styles.otpContainer}>
            <Input.OTP
              ref={inputRef}
              length={6}
              type={showPassword ? "text" : "password"}
              size="large"
              onChange={(value) => {
                setPin(value)
                if (value.length === 6) {
                  handleSubmit(value)
                }
              }}
              style={{
                justifyContent: 'space-between',
                flex: 1,
              }}
            />
            <div
              className={styles.eyeIcon}
              onClick={() => setShowPassword(!showPassword)}
            >
              {showPassword ? <EyeOutlined /> : <EyeInvisibleOutlined />}
            </div>
          </div>
        </div>
        <Button
          onClick={() => handleSubmit(pin)}
          className={styles.button}
          type="primary"
          size="large"
          loading={loading}

        >
          {t('login.login')}
        </Button>
      </div>
    </ContentModal>
  )
}

export default Login
