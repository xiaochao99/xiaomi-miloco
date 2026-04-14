# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Main application controller for Xiaomi Bridge.

Reference: open-xiaoai-bridge/core/app.py
"""

import asyncio
import os
import threading
import time

from miloco_server.xiaomi_bridge.ref import set_app, set_speaker, set_vad
from miloco_server.xiaomi_bridge.services.audio.vad import VAD
from miloco_server.xiaomi_bridge.services.audio.kws import KWS
from miloco_server.xiaomi_bridge.services.audio.asr.sherpa import SherpaASR
from miloco_server.xiaomi_bridge.services.audio.tts.doubao import DoubaoTTS
from miloco_server.xiaomi_bridge.services.audio.stream import AudioStreamHandler
from miloco_server.xiaomi_bridge.conversation_controller import ConversationController
from miloco_server.xiaomi_bridge.services.protocols.typing import DeviceState, EventType
from miloco_server.xiaomi_bridge.utils.config import ConfigManager
from miloco_server.xiaomi_bridge.utils.logger import logger


class MainApp:
    """Main application controller for Xiaomi Bridge."""

    _instance = None

    @classmethod
    def instance(cls, enable_miloco: bool = True):
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = MainApp(enable_miloco=enable_miloco)
        return cls._instance

    def __init__(self, enable_miloco: bool = True):
        """Initialize the main application."""
        if MainApp._instance is not None:
            raise Exception("MainApp is singleton, use instance() to get instance")
        MainApp._instance = self

        # Config
        self.config = ConfigManager.instance()

        # Feature flags
        self._enable_miloco = enable_miloco

        # Device state
        self.device_state = DeviceState.IDLE
        self.current_text = ""
        self.current_emotion = "neutral"

        # Event loop and threads
        self.loop = asyncio.new_event_loop()
        self.loop_thread = None
        self.config_watch_thread = None
        self.shutdown_requested = False
        self.running = False

        # Task queue
        self.main_tasks = []
        self.mutex = threading.Lock()

        # Events
        self.events = {
            EventType.SCHEDULE_EVENT: threading.Event(),
            EventType.AUDIO_INPUT_READY_EVENT: threading.Event(),
            EventType.WAKEUP_EVENT: threading.Event(),
        }

        # Conversation controller
        self.conversation_controller = None

        set_app(self)

    @property
    def is_enabled(self) -> bool:
        """Check if bridge is enabled."""
        return self.config.get_app_config("bridge.enabled", False)

    def run(self):
        """Start the main application."""
        if not self.is_enabled:
            logger.info("[MainApp] Xiaomi Bridge is disabled")
            return

        # Check audio input status
        audio_input_enabled = os.environ.get(
            "AUDIO_INPUT_ENABLE", "true"
        ).strip().lower() in ("true", "1", "yes", "on")

        if not audio_input_enabled and self._enable_miloco:
            raise RuntimeError(
                "Audio input is disabled (AUDIO_INPUT_ENABLE=false) but Miloco is enabled."
            )

        # Create event loop thread
        self.loop_thread = threading.Thread(target=self._run_event_loop)
        self.loop_thread.daemon = True
        self.loop_thread.start()

        self._start_config_watcher()

        time.sleep(0.1)

        # Initialize components
        asyncio.run_coroutine_threadsafe(self._init_components(), self.loop)

        # Start main loop thread
        main_loop_thread = threading.Thread(target=self._main_loop)
        main_loop_thread.daemon = True
        main_loop_thread.start()

        # Start audio services
        if self._enable_miloco:
            if audio_input_enabled:
                VAD.start()
                KWS.start()
                AudioStreamHandler.start()
                logger.info("[MainApp] Audio input enabled (VAD/KWS/AudioStream started)")
            else:
                logger.info("[MainApp] Audio input disabled")

            # Pre-warm ASR
            if audio_input_enabled:
                threading.Thread(
                    target=SherpaASR._ensure_loaded,
                    daemon=True,
                    name="asr-warmup",
                ).start()

    def _run_event_loop(self):
        """Run asyncio event loop in separate thread."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _start_config_watcher(self):
        """Start config file watcher thread."""
        if self.config_watch_thread and self.config_watch_thread.is_alive():
            return

        self.config_watch_thread = threading.Thread(
            target=self._watch_config_file,
            daemon=True,
        )
        self.config_watch_thread.start()

    def _watch_config_file(self):
        """Poll config file for changes and hot-reload."""
        config_path = self.config.get_config_path()
        last_mtime = None

        while True:
            if self.shutdown_requested:
                break

            try:
                current_mtime = os.path.getmtime(config_path)
                if last_mtime is None:
                    last_mtime = current_mtime
                elif current_mtime != last_mtime:
                    last_mtime = current_mtime
                    self.config.reload_app_config()
                    logger.info(f"[Config] Reloaded runtime config from {config_path}")
            except Exception as exc:
                logger.warning(f"[Config] Failed to reload config: {exc}")

            time.sleep(1)

    async def _init_components(self):
        """Initialize all components."""
        self.device_state = DeviceState.CONNECTING

        # Initialize VAD
        vad_config = self.config.get_app_config("vad", {})
        VAD.set_config(
            threshold=vad_config.get("threshold", 0.10),
            min_speech_duration_ms=vad_config.get("min_speech_duration_ms", 250),
            min_silence_duration_ms=vad_config.get("min_silence_duration_ms", 500),
        )
        set_vad(VAD.instance())

        # Initialize KWS
        kws_config = self.config.get_app_config("kws", {})
        wakeup_keywords = self.config.get_app_config("wakeup.keywords", ["小米同学"])
        KWS.set_config(
            keywords=wakeup_keywords,
            keywords_score=kws_config.get("keywords_score", 2.0),
            keywords_threshold=kws_config.get("keywords_threshold", 0.2),
            model_dir=kws_config.get("model_dir", "models/kws"),
        )
        KWS.set_callback(self._on_keyword_detected)

        # Initialize ASR
        asr_config = self.config.get_app_config("asr", {})
        SherpaASR.set_config(
            model=asr_config.get("model", "sense_voice"),
            model_dir=asr_config.get("model_dir", "models/asr"),
            int8=asr_config.get("int8", True),
            num_threads=asr_config.get("num_threads", 2),
        )
        SherpaASR.initialize()

        # Initialize TTS
        tts_config = self.config.get_app_config("tts", {})
        DoubaoTTS.set_config(
            app_id=tts_config.get("app_id", ""),
            access_key=tts_config.get("access_key", ""),
            default_speaker=tts_config.get("default_speaker", "zh_female_vv_uranus_bigtts"),
            audio_format=tts_config.get("audio_format", "pcm"),
            stream=tts_config.get("stream", True),
            speed=tts_config.get("speed", 1.0),
        )
        await DoubaoTTS.initialize()

        # Initialize audio stream handler
        AudioStreamHandler.instance().set_audio_input_callback(self._handle_audio_input)

        # Initialize conversation controller
        self.conversation_controller = ConversationController.instance()

        # Set dummy speaker for now (will be replaced with real speaker)
        set_speaker(DummySpeaker())

        self.device_state = DeviceState.CONNECTED
        logger.info("[MainApp] Xiaomi Bridge components initialized")

    def _handle_audio_input(self, audio_data: bytes):
        """Handle incoming audio data."""
        if not self.running:
            return

        # Process through KWS when not in conversation
        if self.conversation_controller and not self.conversation_controller.is_active():
            if KWS.is_running():
                KWS.process_audio(audio_data)

        # Process through VAD when in conversation
        if self.conversation_controller and self.conversation_controller.is_active():
            if VAD.is_running() and not VAD.is_paused():
                VAD.process_audio(audio_data)

        # Trigger audio input ready event
        self.events[EventType.AUDIO_INPUT_READY_EVENT].set()

    def _on_keyword_detected(self, keyword: str):
        """Handle keyword detection."""
        logger.info(f"[MainApp] Wakeup keyword detected: {keyword}")
        
        if self.conversation_controller and not self.conversation_controller.is_active():
            # Start conversation
            asyncio.run_coroutine_threadsafe(
                self.conversation_controller.start(),
                self.loop
            )

        # Trigger wakeup event
        self.events[EventType.WAKEUP_EVENT].set()

    def _main_loop(self):
        """Main application loop."""
        self.running = True

        while self.running:
            for event_type, event in self.events.items():
                if event.is_set():
                    event.clear()

                    if event_type == EventType.AUDIO_INPUT_READY_EVENT:
                        pass  # Handled in _handle_audio_input
                    elif event_type == EventType.SCHEDULE_EVENT:
                        self._process_scheduled_tasks()
                    elif event_type == EventType.WAKEUP_EVENT:
                        pass  # Handled in _on_keyword_detected

            time.sleep(0.01)

    def _process_scheduled_tasks(self):
        """Process scheduled tasks."""
        with self.mutex:
            tasks = self.main_tasks.copy()
            self.main_tasks.clear()

        for task in tasks:
            try:
                task()
            except Exception as exc:
                logger.error(f"[MainApp] Scheduled task failed: {type(exc).__name__}: {exc}")

    def schedule(self, callback):
        """Schedule task to main loop."""
        with self.mutex:
            if "abort_speaking" in str(callback):
                if any("abort_speaking" in str(task) for task in self.main_tasks):
                    return
            self.main_tasks.append(callback)
        self.events[EventType.SCHEDULE_EVENT].set()

    # State management

    def set_chat_message(self, role, message):
        """Set chat message."""
        self.current_text = message

    def set_emotion(self, emotion):
        """Set emotion."""
        self.current_emotion = emotion

    def alert(self, title, message):
        """Show alert."""
        logger.warning(f"[Alert] {title}: {message}")

    # Shutdown

    def shutdown(self):
        """Shutdown the application."""
        self.shutdown_requested = True
        self.running = False

        # Stop conversation
        if self.conversation_controller:
            self.conversation_controller.stop()

        # Stop audio services
        VAD.stop()
        KWS.stop()
        AudioStreamHandler.stop()

        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

        if self.loop_thread and self.loop_thread.is_alive():
            self.loop_thread.join(timeout=1.0)

        if self.config_watch_thread and self.config_watch_thread.is_alive():
            self.config_watch_thread.join(timeout=1.0)

        logger.info("[MainApp] Xiaomi Bridge shutdown completed")


class DummySpeaker:
    """Dummy speaker for testing."""

    async def play(self, text=None, buffer=None, blocking=True):
        """Play audio."""
        if text:
            logger.info(f"[Speaker] Playing text: {text[:50]}")
        elif buffer:
            logger.info(f"[Speaker] Playing buffer: {len(buffer)} bytes")

    async def wake_up(self, awake=True):
        """Wake up or sleep."""
        pass

    async def stop_device_audio(self):
        """Stop audio."""
        pass