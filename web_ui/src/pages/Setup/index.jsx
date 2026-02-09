/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState } from "react"
import CryptoJS from 'crypto-js'
import { useNavigate } from "react-router-dom"
import { message, Input, Button } from "antd"
import { useTranslation } from 'react-i18next';
import { LanguageSwitcher, ContentModal } from "@/components";
import { setInitPinCode } from "@/api"
import styles from "./index.module.less"


/**
 * Setup Page - Initial setup page for setting up PIN code for first-time users
 * 设置页面 - 为首次用户设置登录码的初始设置页面
 *
 * @returns {JSX.Element} Setup page component
 */
const Setup = () => {
  const [pin, setPin] = useState("")
  const [confirmPin, setConfirmPin] = useState("")
  const navigate = useNavigate()
  const { t } = useTranslation();

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (pin.length !== 6) {
      message.error(t('login.pinLength'))
      return
    }
    if (pin !== confirmPin) {
      message.error(t('login.pinNotMatch'))
      return
    }
    const res = await setInitPinCode({ password: CryptoJS.MD5(pin).toString() })

    if (res?.code === 0) {
      message.success(t('login.setSuccess'))
      navigate("/login")
    } else {
      message.error(t('login.setFail'))
    }
  }

  return (
    <ContentModal>
      <LanguageSwitcher
        size="small"
        showIcon={true}
        showLabel={false}
        className={styles.loginLanguageSwitcher}
      />
      <h1 className={styles.title}>{t('login.setPinTitle')}</h1>
      <div className={styles.description}>{t('login.setPinDescription')}<span>{t('login.setPinReminder')}</span></div>
      <div className={styles.form}>
        <div className={styles.inputGroup}>
          <div className={styles.label}>
            {t('login.inputPin')}
          </div>
          <Input.Password
            type="password"
            value={pin}
            onChange={(e) => setPin(e.target.value)}
            maxLength={6}
            className={styles.input}
            placeholder={t('login.inputPinPlaceholder')}
          />
          <div className={styles.label}>
            {t('login.confirmPinLabel')}
          </div>
          <Input.Password
            type="password"
            value={confirmPin}
            onChange={(e) => setConfirmPin(e.target.value)}
            maxLength={6}
            className={styles.input}
            placeholder={t('login.confirmPinPlaceholder')}
          />
        </div>
        <div className={styles.buttonGroup}>
          <Button onClick={() => {
            if (window.opener) {
              window.close()
            } else if (window.history.length > 1) {
              navigate(-1)
            }
          }} className={styles.button}>
            {t('login.cancelButton')}
          </Button>
          <Button
            onClick={handleSubmit}
            type="primary"
            className={styles.button}
          >
            {t('login.confirmSetButton')}
          </Button>
        </div>
      </div>
    </ContentModal>
  )
}



export default Setup
