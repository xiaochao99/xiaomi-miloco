# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Test script for Xiaomi Bridge refactored code.

Run with: python -m miloco_server.xiaomi_bridge.test_bridge
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_config_manager():
    """Test config manager."""
    from miloco_server.xiaomi_bridge.utils.config import ConfigManager
    
    config = ConfigManager.instance()
    
    # Test getting config
    bridge_enabled = config.get_app_config("bridge.enabled")
    print("OK: Bridge enabled:", bridge_enabled)
    
    # Test default values
    test_key = config.get_app_config("nonexistent.key", "default_value")
    assert test_key == "default_value", "Default value test failed"
    print("OK: Default value test passed")
    
    # Test setting config
    config.set_app_config("test.key", "test_value")
    assert config.get_app_config("test.key") == "test_value", "Set config test failed"
    print("OK: Set config test passed")
    
    print("OK: ConfigManager tests passed!")


async def test_logger():
    """Test logger."""
    from miloco_server.xiaomi_bridge.utils.logger import get_logger
    
    logger = get_logger("test")
    logger.info("Test log message")
    print("OK: Logger test passed!")


async def test_audio_modules():
    """Test audio modules initialization."""
    from miloco_server.xiaomi_bridge.services.audio.vad import VAD
    from miloco_server.xiaomi_bridge.services.audio.kws import KWS
    from miloco_server.xiaomi_bridge.services.audio.asr.sherpa import SherpaASR
    from miloco_server.xiaomi_bridge.services.audio.tts.doubao import DoubaoTTS
    from miloco_server.xiaomi_bridge.services.audio.stream import AudioStreamHandler
    
    # Test VAD
    vad = VAD.instance()
    VAD.set_config(threshold=0.10)
    print("OK: VAD initialized")
    
    # Test KWS
    kws = KWS.instance()
    KWS.set_config(keywords=["测试"])
    print("OK: KWS initialized")
    
    # Test TTS
    tts = DoubaoTTS.instance()
    await tts.initialize()
    print("OK: TTS initialized")
    
    # Test AudioStreamHandler
    audio_stream = AudioStreamHandler.instance()
    print("OK: AudioStreamHandler initialized")
    
    print("OK: Audio modules tests passed!")


async def test_conversation_controller():
    """Test conversation controller."""
    from miloco_server.xiaomi_bridge.conversation_controller import ConversationController
    
    controller = ConversationController.instance()
    assert not controller.is_active(), "Controller should not be active"
    print("OK: ConversationController initialized")
    
    # Test config properties
    print("OK: Exit keywords:", controller.exit_keywords)
    print("OK: Timeout:", controller.timeout)
    print("OK: Input mode:", controller.input_mode)
    
    print("OK: ConversationController tests passed!")


async def test_routes():
    """Test route modules."""
    from miloco_server.xiaomi_bridge.routes import api_router, websocket_router
    
    assert api_router is not None, "API router should not be None"
    assert websocket_router is not None, "WebSocket router should not be None"
    print("OK: API router: OK")
    print("OK: WebSocket router: OK")
    
    print("OK: Routes tests passed!")


async def test_main_app():
    """Test main app initialization."""
    from miloco_server.xiaomi_bridge.main_app import MainApp
    
    # Test with Miloco disabled for testing
    app = MainApp.instance(enable_miloco=False)
    assert app is not None, "MainApp should not be None"
    print("OK: MainApp initialized")
    
    print("OK: MainApp tests passed!")


async def main():
    """Run all tests."""
    print("Starting Xiaomi Bridge tests...")
    print()
    
    await test_config_manager()
    print()
    
    test_logger()
    print()
    
    await test_audio_modules()
    print()
    
    test_conversation_controller()
    print()
    
    test_routes()
    print()
    
    test_main_app()
    print()
    
    print("All tests passed successfully!")


if __name__ == "__main__":
    asyncio.run(main())