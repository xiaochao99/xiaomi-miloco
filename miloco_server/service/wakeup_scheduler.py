# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
WakeUp Scheduler
Schedules and orchestrates the complete wakeup flow
"""

import asyncio
import logging
import uuid
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime

from miloco_server.schema.trigger_schema import TriggerRule, ExecuteInfo
from miloco_server.schema.wakeup_schema import (
    WakeUpContext, WakeUpConfig, WakeUpSession, WakeUpState,
    WakeUpMode, WakeUpExecutionResult, ProcessResult,
    TriggerSourceType
)
from miloco_server.service.wakeup_context_builder import WakeUpContextBuilder
from miloco_server.agent.wakeup_chat_agent import WakeUpChatAgent

logger = logging.getLogger(__name__)


class WakeUpScheduler:
    """
    WakeUp Scheduler

    Responsibilities:
    1. Build wakeup context from trigger rules
    2. Orchestrate TTS playback → wakeup listening → voice capture → AI processing
    3. Manage wakeup session state machine
    4. Handle timeout and retry logic
    """

    def __init__(self, bridge_manager=None, llm_proxy=None, tool_executor=None):
        self._bridge_manager = bridge_manager
        self._llm_proxy = llm_proxy
        self._tool_executor = tool_executor

        self._active_sessions: Dict[str, WakeUpSession] = {}
        self._event_callbacks: Dict[str, Callable] = {}

        self._context_builder = WakeUpContextBuilder()
        if llm_proxy:
            self._context_builder.set_llm_proxy(llm_proxy)

    def set_bridge_manager(self, bridge_manager):
        """Set bridge manager for TTS and audio control"""
        self._bridge_manager = bridge_manager

    def set_llm_proxy(self, llm_proxy):
        """Set LLM proxy for AI decision making"""
        self._llm_proxy = llm_proxy
        self._context_builder.set_llm_proxy(llm_proxy)

    def set_tool_executor(self, tool_executor):
        """Set tool executor for action execution"""
        self._tool_executor = tool_executor

    def set_ha_proxy(self, ha_proxy):
        """Set HA proxy for device state fetching"""
        self._context_builder.set_ha_proxy(ha_proxy)

    async def execute_wakeup_flow(
        self,
        rule: TriggerRule,
        trigger_event: Optional[Dict[str, Any]] = None
    ) -> WakeUpExecutionResult:
        """
        Execute complete wakeup flow

        Flow:
        1. Build wakeup context (AI decides whether to ask)
        2. If inquiry needed:
           a. TTS play inquiry content
           b. Start wakeup listening
           c. After user speaks, WakeUpChatAgent processes
           d. Execute corresponding action
        3. If no inquiry needed, execute automation action directly
        """

        session_id = str(uuid.uuid4())

        try:
            context = await self._context_builder.build_from_rule(rule, trigger_event)
            context.session_id = session_id

            logger.info(
                f"[WakeUpScheduler] Context built for rule {rule.name}: "
                f"requires_inquiry={context.requires_inquiry}, "
                f"content={context.inquiry_content[:30] if context.inquiry_content else 'N/A'}..."
            )

            wakeup_config = self._get_wakeup_config(rule)

            # MANUAL: 传统静默/直接执行（不做主动询问与语音交互）
            if wakeup_config.mode == WakeUpMode.MANUAL or wakeup_config.enabled is False:
                return await self._execute_direct_action(rule, session_id, context)

            session = WakeUpSession(
                session_id=session_id,
                context=context,
                state=WakeUpState.CONTEXT_BUILDING,
                device_ids=wakeup_config.target_devices or None
            )
            self._active_sessions[session_id] = session

            return await self._execute_inquiry_flow(session, wakeup_config, rule)

        except Exception as e:
            logger.error(f"[WakeUpScheduler] Wakeup flow error for session {session_id}: {e}")
            return WakeUpExecutionResult(
                success=False,
                session_id=session_id,
                error=str(e)
            )

    async def _execute_direct_action(
        self,
        rule: TriggerRule,
        session_id: str,
        context: WakeUpContext
    ) -> WakeUpExecutionResult:
        """Execute action directly without inquiry"""

        logger.info(f"[WakeUpScheduler] Direct action execution for session {session_id}")

        try:
            if rule.execute_info and rule.execute_info.automation_actions:
                for action in rule.execute_info.automation_actions:
                    if self._tool_executor:
                        await self._tool_executor.execute_tool_by_params(
                            action.mcp_client_id,
                            action.mcp_tool_name,
                            action.mcp_tool_input
                        )

            return WakeUpExecutionResult(
                success=True,
                session_id=session_id,
                response=f"{rule.name}已执行"
            )
        except Exception as e:
            logger.error(f"[WakeUpScheduler] Direct action error: {e}")
            return WakeUpExecutionResult(
                success=False,
                session_id=session_id,
                error=str(e)
            )

    async def _execute_inquiry_flow(
        self,
        session: WakeUpSession,
        wakeup_config: WakeUpConfig,
        rule: TriggerRule
    ) -> WakeUpExecutionResult:
        """
        Execute wakeup interaction flow with a single user turn.

        UX:
        1) (optional) play inquiry TTS
        2) directly start voice interaction window (no wake word needed)
        3) after one turn, end the session automatically
        """

        session.state = WakeUpState.TTS_PLAYING
        session.tts_start_time = datetime.now()

        try:
            if not self._bridge_manager:
                raise RuntimeError("BridgeManager is not set")

            # 1) Play inquiry TTS only in PROACTIVE mode
            if wakeup_config.mode == WakeUpMode.PROACTIVE:
                tts_text = session.context.inquiry_content or "有什么可以帮您的吗？"
                devices = wakeup_config.target_devices if wakeup_config.target_devices else None
                session.state = WakeUpState.TTS_PLAYING
                session.tts_start_time = datetime.now()

                # "播报优先": 当 AI 判定需要主动询问时，先播报 broadcast_text，再播报 inquiry_content
                broadcast_text = session.context.relevant_data.get("broadcast_text") if session.context.relevant_data else None
                should_play_broadcast_first = (
                    session.context.requires_inquiry
                    and broadcast_text
                    and str(broadcast_text).strip()
                    and str(broadcast_text).strip() != str(tts_text).strip()
                )

                if should_play_broadcast_first:
                    ok1 = await self._bridge_manager.play_tts(str(broadcast_text), device_ids=devices)
                    if not ok1:
                        raise RuntimeError("Broadcast TTS playback failed")

                ok2 = await self._bridge_manager.play_tts(tts_text, device_ids=devices)
                if not ok2:
                    raise RuntimeError("Inquiry TTS playback failed")

            session.state = WakeUpState.VOICE_CAPTURING
            session.wakeup_start_time = datetime.now()

            # 2) Start one-turn voice interaction, route to WakeUpChatAgent
            interaction_future: asyncio.Future = asyncio.get_event_loop().create_future()
            captured_user_text: Optional[str] = None

            chat_agent = WakeUpChatAgent(
                session_id=session.session_id,
                context=session.context,
                llm_proxy=self._llm_proxy,
                tool_executor=self._tool_executor
            )

            async def process_text_callback(user_text: str) -> str:
                result = await chat_agent.process(user_text)
                nonlocal captured_user_text
                captured_user_text = user_text
                if not interaction_future.done():
                    interaction_future.set_result(result)
                return result.response

            # Ensure we start from clean state and then restore default callback afterwards.
            self._bridge_manager.conversation_controller.configure(
                process_text_callback=process_text_callback,
                single_turn=True,
                timeout=wakeup_config.voice_input_timeout
            )

            try:
                await self._bridge_manager.conversation_controller.start()
            finally:
                self._bridge_manager.restore_conversation_default_process_text_callback()

            # 3) Collect results from callback (if any)
            if interaction_future.done():
                result: ProcessResult = interaction_future.result()
                session.state = WakeUpState.COMPLETED

                # Cleanup session resources
                self._cleanup_session(session.session_id)

                return WakeUpExecutionResult(
                    success=True,
                    session_id=session.session_id,
                    user_speech=captured_user_text,
                    response=result.response,
                    action_executed=result.action_executed,
                    action_success=result.action_success,
                    ended=True
                )

            # No user speech / callback not triggered
            session.state = WakeUpState.TIMEOUT
            if not interaction_future.done():
                interaction_future.cancel()
            self._cleanup_session(session.session_id)
            return WakeUpExecutionResult(
                success=False,
                session_id=session.session_id,
                error="Voice interaction timeout"
            )

        except Exception as e:
            logger.error(f"[WakeUpScheduler] Inquiry flow error: {e}")
            session.state = WakeUpState.FAILED
            self._cleanup_session(session.session_id)
            return WakeUpExecutionResult(
                success=False,
                session_id=session.session_id,
                error=str(e)
            )

    async def _wait_for_tts_complete(
        self,
        session_id: str,
        timeout: int
    ) -> bool:
        """Wait for TTS playback to complete"""

        if not self._bridge_manager:
            await asyncio.sleep(2)
            return True

        try:
            future = asyncio.Future()

            def on_tts_complete(event_data):
                if not future.done():
                    future.set_result(True)

            self._event_callbacks[f"tts_complete_{session_id}"] = on_tts_complete

            if self._bridge_manager:
                await self._bridge_manager.play_tts_async(
                    " ", ["all"],
                    callback=lambda e: asyncio.get_event_loop().call_soon_threadsafe(
                        lambda: on_tts_complete(e) if on_tts_complete else None
                    )
                )

            try:
                await asyncio.wait_for(future, timeout=timeout)
                return True
            except asyncio.TimeoutError:
                return False

        except Exception as e:
            logger.error(f"[WakeUpScheduler] TTS wait error: {e}")
            await asyncio.sleep(2)
            return True

    async def _wait_for_wakeup(
        self,
        session_id: str,
        timeout: int
    ) -> bool:
        """Wait for wakeup keyword detection"""

        if not self._bridge_manager:
            await asyncio.sleep(3)
            return True

        try:
            future = asyncio.Future()

            def on_wakeup_detected(event_data):
                logger.info(f"[WakeUpScheduler] Wakeup detected for session {session_id}")
                if not future.done():
                    future.set_result(True)

            self._event_callbacks[f"wakeup_{session_id}"] = on_wakeup_detected

            if self._bridge_manager:
                await self._bridge_manager.start_wakeup_listening(
                    session_id=session_id,
                    callback=lambda e: asyncio.get_event_loop().call_soon_threadsafe(
                        lambda: on_wakeup_detected(e) if on_wakeup_detected else None
                    )
                )

            try:
                await asyncio.wait_for(future, timeout=timeout)
                return True
            except asyncio.TimeoutError:
                logger.info(f"[WakeUpScheduler] Wakeup timeout for session {session_id}")
                return False

        except Exception as e:
            logger.error(f"[WakeUpScheduler] Wakeup wait error: {e}")
            await asyncio.sleep(3)
            return True

    async def _capture_and_process_voice(
        self,
        session: WakeUpSession,
        wakeup_config: WakeUpConfig,
        rule: TriggerRule
    ) -> WakeUpExecutionResult:
        """Capture voice and process with AI"""

        try:
            audio_data = await self._bridge_manager.capture_voice(
                session_id=session.session_id,
                timeout=wakeup_config.voice_input_timeout
            )

            if not audio_data:
                logger.warning(
                    f"[WakeUpScheduler] No voice captured for session {session.session_id}"
                )
                return await self._handle_voice_timeout(session, wakeup_config, rule)

            session.state = WakeUpState.AI_PROCESSING

            stt_text = await self._bridge_manager.speech_to_text(audio_data)

            if not stt_text:
                return await self._handle_voice_timeout(session, wakeup_config, rule)

            logger.info(
                f"[WakeUpScheduler] User speech for session {session.session_id}: {stt_text}"
            )

            chat_agent = WakeUpChatAgent(
                session_id=session.session_id,
                context=session.context,
                llm_proxy=self._llm_proxy,
                tool_executor=self._tool_executor
            )

            result = await chat_agent.process(stt_text)

            session.state = WakeUpState.RESPONSE_SPEAKING

            if result.response:
                await self._bridge_manager.play_tts(result.response)

            session.state = WakeUpState.COMPLETED

            if result.should_end:
                self._cleanup_session(session.session_id)

            return WakeUpExecutionResult(
                success=True,
                session_id=session.session_id,
                user_speech=stt_text,
                response=result.response,
                action_executed=result.action_executed,
                action_success=result.action_success,
                ended=result.should_end
            )

        except Exception as e:
            logger.error(f"[WakeUpScheduler] Voice processing error: {e}")
            session.state = WakeUpState.FAILED
            return WakeUpExecutionResult(
                success=False,
                session_id=session.session_id,
                error=str(e)
            )

    async def _handle_voice_timeout(
        self,
        session: WakeUpSession,
        wakeup_config: WakeUpConfig,
        rule: TriggerRule
    ) -> WakeUpExecutionResult:
        """Handle voice input timeout"""

        if session.context.turn_count < wakeup_config.retry_count:
            retry_response = "抱歉，我没有听清楚，您能再说一次吗？"
            await self._bridge_manager.play_tts(retry_response)

            session.context.turn_count += 1

            return await self._capture_and_process_voice(
                session, wakeup_config, rule
            )

        session.state = WakeUpState.TIMEOUT
        self._cleanup_session(session.session_id)

        return WakeUpExecutionResult(
            success=False,
            session_id=session.session_id,
            error="Voice input timeout"
        )

    async def _retry_wakeup(
        self,
        session: WakeUpSession,
        wakeup_config: WakeUpConfig,
        rule: TriggerRule
    ) -> WakeUpExecutionResult:
        """Retry wakeup after failure"""

        for attempt in range(wakeup_config.retry_count):
            retry_interval = wakeup_config.retry_interval

            logger.info(
                f"[WakeUpScheduler] Retry wakeup attempt {attempt + 1} "
                f"for session {session.session_id}, waiting {retry_interval}s"
            )

            await asyncio.sleep(retry_interval)

            tts_text = "您还在吗？我再问一次，" + (session.context.inquiry_content or "")

            try:
                await self._bridge_manager.play_tts(tts_text)

                wakeup_detected = await self._wait_for_wakeup(
                    session.session_id,
                    timeout=wakeup_config.wakeup_timeout
                )

                if wakeup_detected:
                    return await self._capture_and_process_voice(
                        session, wakeup_config, rule
                    )

            except Exception as e:
                logger.error(f"[WakeUpScheduler] Retry error: {e}")
                continue

        session.state = WakeUpState.FAILED
        self._cleanup_session(session.session_id)

        return WakeUpExecutionResult(
            success=False,
            session_id=session.session_id,
            error=f"All {wakeup_config.retry_count} retry attempts failed"
        )

    def _get_wakeup_config(self, rule: TriggerRule) -> WakeUpConfig:
        """Get wakeup configuration from rule"""

        if rule.execute_info and rule.execute_info.xiaoai_wakeup:
            return rule.execute_info.xiaoai_wakeup

        return WakeUpConfig()

    def _cleanup_session(self, session_id: str):
        """Clean up session resources"""

        if session_id in self._active_sessions:
            del self._active_sessions[session_id]

        keys_to_remove = [k for k in self._event_callbacks if k.endswith(f"_{session_id}")]
        for key in keys_to_remove:
            del self._event_callbacks[key]

        if self._bridge_manager:
            asyncio.create_task(
                self._bridge_manager.stop_wakeup_listening(session_id)
            )

    def get_session(self, session_id: str) -> Optional[WakeUpSession]:
        """Get active session by ID"""
        return self._active_sessions.get(session_id)

    def get_active_sessions(self) -> List[WakeUpSession]:
        """Get all active sessions"""
        return list(self._active_sessions.values())
