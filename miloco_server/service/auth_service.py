# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Authentication service module
"""

import logging

from miloco_server.dao.kv_dao import AuthConfigKeys, KVDao
from miloco_server.schema.auth_schema import (
    LoginRequest, RegisterRequest, RegisterData, RegisterStatusData,
    LoginResponseData, UserLanguage, UserLanguageData
)
from miloco_server.middleware import (
    BusinessException,
    ValidationException,
    AuthenticationException,
    create_access_token,
    set_auth_cookie,
    clear_auth_cookie,
    invalidate_all_tokens,
    ADMIN_USERNAME
)

logger = logging.getLogger(__name__)


class AuthService:
    """Authentication service class"""

    def __init__(self, kv_dao: KVDao):
        self._kv_dao = kv_dao
        self._admin_password: str | None = self._kv_dao.get(
            AuthConfigKeys.ADMIN_PASSWORD_KEY)

    def is_admin_registered(self) -> bool:
        """
        Check if admin is registered
        """
        logger.info(
            "is_admin_registered admin_password: %s", self._admin_password)
        return self._admin_password is not None

    def register_admin(self, password: str) -> bool:
        """
        Register admin
        """
        self._kv_dao.set(AuthConfigKeys.ADMIN_PASSWORD_KEY, password)
        self._admin_password = password
        return True

    def verify_admin_password(self, password: str) -> bool:
        """
        Verify admin password
        """
        return self._admin_password == password

    def register_admin_user(self, register_data: RegisterRequest) -> RegisterData:
        """
        Register admin user business logic
        """
        logger.info("Register API called - password=***")

        # Check if already registered
        if self.is_admin_registered():
            logger.info("Register API returned - Admin already registered")
            raise ValidationException("Admin already registered, cannot register again")

        # Register admin user
        success = self.register_admin(register_data.password)

        if success:
            logger.info("Register API returned - Successfully registered user: %s", ADMIN_USERNAME)
            return RegisterData(username=ADMIN_USERNAME)
        else:
            logger.error("Register API returned - Registration failed")
            raise BusinessException("Registration failed, please try again later")

    def check_register_status(self) -> RegisterStatusData:
        """
        Check registration status business logic
        """
        is_registered = self.is_admin_registered()

        logger.info("Check register status API returned - Is registered: %s", is_registered)
        return RegisterStatusData(is_registered=is_registered)

    def login_user(self, login_data: LoginRequest, response) -> LoginResponseData:
        """
        User login business logic
        Returns access token for API authentication
        """
        logger.info("Login API called - data=%s", login_data.username)

        # Verify username is fixed as admin
        if login_data.username != ADMIN_USERNAME:
            logger.warning("Login API returned - Invalid username: %s", login_data.username)
            raise AuthenticationException("Invalid username")

        # Check if admin is registered
        if not self.is_admin_registered():
            logger.warning("Login API returned - Admin not registered")
            raise ValidationException("Admin not registered, please register first")

        # Verify password
        if not self.verify_admin_password(login_data.password):
            logger.warning("Login API returned - Invalid password: username=%s", login_data.username)
            raise AuthenticationException("Invalid password")

        access_token = create_access_token(login_data.username)

        # Set Cookie using middleware function
        set_auth_cookie(response, access_token)

        logger.info("Login API returned - Login successful: username=%s", login_data.username)
        return LoginResponseData(
            username=ADMIN_USERNAME,
            access_token=access_token,
            token_type="bearer"
        )

    def logout_user(self, response) -> None:
        """
        User logout business logic
        """
        logger.info("Logout API called")
        invalidate_all_tokens()
        clear_auth_cookie(response)
        logger.info("Logout API returned - Logout successful")

    def get_user_language(self) -> UserLanguageData:
        """
        Get user language settings
        """
        logger.info("Get user language API called")
        language_str = self._kv_dao.get(AuthConfigKeys.USER_LANGUAGE_KEY, UserLanguage.CHINESE.value)

        try:
            language = UserLanguage(language_str)
        except ValueError:
            logger.warning("Invalid language value in storage: %s, using default: %s",
                         language_str, UserLanguage.CHINESE.value)
            language = UserLanguage.CHINESE

        logger.info("Get user language API returned - language=%s", language.value)
        return UserLanguageData(language=language)

    def set_user_language(self, language_request: UserLanguageData) -> UserLanguageData:
        """
        Set user language
        """
        logger.info("Set user language API called - language=%s", language_request.language.value)
        success = self._kv_dao.set(AuthConfigKeys.USER_LANGUAGE_KEY, language_request.language.value)

        if not success:
            logger.error("Set user language API returned - Failed to save language: %s",
                       language_request.language.value)
            raise BusinessException("Failed to save language settings")

        logger.info("Set user language API returned - Language set successfully: %s",
                   language_request.language.value)
        return UserLanguageData(language=language_request.language)
