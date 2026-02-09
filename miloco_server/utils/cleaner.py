# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Cleaner utility for managing data cleanup tasks.
Provides functionality to clean up chat history, trigger rule logs and image files.
"""

import asyncio
import logging

from miloco_server.config.normal_config import CHAT_CONFIG, TRIGGER_RULE_RUNNER_CONFIG
from miloco_server.dao.chat_history_dao import ChatHistoryDAO
from miloco_server.dao.trigger_rule_log_dao import TriggerRuleLogDAO
from miloco_server.schema.chat_history_schema import ChatHistorySession
from miloco_server.schema.chat_schema import Instruction, Template
from miloco_server.schema.miot_schema import CameraImgPathSeq
from miloco_server.schema.trigger_log_schema import TriggerRuleLog
from miloco_server.utils.media import image_manager

logger = logging.getLogger(__name__)


class Cleaner:
    """Cleaner for managing data cleanup tasks"""

    def __init__(self, chat_history_dao: ChatHistoryDAO,
                 trigger_rule_log_dao: TriggerRuleLogDAO):
        self._chat_history_dao = chat_history_dao
        self._trigger_rule_log_dao = trigger_rule_log_dao
        self._chat_history_ttl = CHAT_CONFIG["chat_history_ttl"]
        self._trigger_rule_log_ttl = TRIGGER_RULE_RUNNER_CONFIG["trigger_rule_log_ttl"]

        # Start scheduled cleanup task
        asyncio.create_task(self._cleanup_loop())
        logger.info("Cleaner started")

    async def _cleanup_loop(self):
        """Async cleanup loop"""
        while True:
            try:
                await self._clean_chat_history(self._chat_history_ttl)
                await self._clean_trigger_rule_log(self._trigger_rule_log_ttl)
                # Wait 24 hours
                await asyncio.sleep(24 * 60 * 60)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Cleanup error: %s", e)
                await asyncio.sleep(60 * 60)  # Wait 1 hour after error

    async def _clean_chat_history(self, days: int):
        # Execute cleanup immediately
        need_delete = self._chat_history_dao.get_records_before_days(days)
        if not need_delete:
            return

        for chat_history in need_delete:
            history = self._chat_history_dao.get_by_id(
                chat_history.session_id)
            if history is not None and history.session is not None:
                await self._clean_chat_history_session(
                    history.session)

        need_delete_ids = [chat_history.session_id for chat_history in need_delete]
        self._chat_history_dao.delete_by_ids(need_delete_ids)
        logger.info("Cleanup: deleted %d old records", len(need_delete))


    async def _clean_chat_history_session(self, session: ChatHistorySession):
        """
        Clean up image files
        """
        for session_item in session.data:
            if isinstance(session_item, Instruction):
                await self._clean_instruction_images(session_item)


    async def _clean_instruction_images(self, instruction: Instruction):
        if instruction.judge_type("Template", "CameraImages"):
            payload = Template.CameraImages.model_validate_json(
                instruction.payload)
            await self._clean_image_path_seq_list(
                payload.image_path_seq_list)


    async def _clean_trigger_rule_log(self, days: int):
        """
        Clean up trigger rule logs
        """
        try:
            logs: list[TriggerRuleLog] = self._trigger_rule_log_dao.get_logs_before_days(days)
            await self._clean_trigger_rule_log_condition_images(logs)
            await self._clean_trigger_rule_log_execute_result_images(logs)
            log_ids = [log.id for log in logs if log.id is not None]
            self._trigger_rule_log_dao.delete_by_ids(log_ids)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error cleaning trigger rule log: %s",
                         e, exc_info=True)

    async def _clean_trigger_rule_log_condition_images(self, logs: list[TriggerRuleLog]):
        """
        Clean up trigger rule log condition images
        """
        if not logs:
            return

        tasks = []
        for log in logs:
            for camera_condition_result in log.condition_results:
                if camera_condition_result.images:
                    tasks.append(
                        image_manager.delete_image_list_async([
                            image.data
                            for image in camera_condition_result.images
                        ]))
        await asyncio.gather(*tasks)

    async def _clean_trigger_rule_log_execute_result_images(self, logs: list[TriggerRuleLog]):
        """
        Clean up trigger rule log execute result
        """
        if not logs:
            return
        for log in logs:
            if log.execute_result and log.execute_result.ai_recommend_dynamic_execute_result:
                execute_result = log.execute_result.ai_recommend_dynamic_execute_result
                await self._clean_chat_history_session(execute_result.chat_history_session)


    async def _clean_image_path_seq_list(
            self, image_path_seq_list: list[CameraImgPathSeq]):
        """
        Clean up image files
        """
        logger.info("start to _clean_image_path_seq_list %s", image_path_seq_list)
        tasks = []
        for image_path_seq in image_path_seq_list:
            tasks.append(image_path_seq.delete_image_list_async())
        await asyncio.gather(*tasks)
