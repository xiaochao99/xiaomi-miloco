# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

# pylint: disable=import-outside-toplevel, unused-argument, missing-function-docstring, line-too-long, C0114, W0621
import pytest
import json
from fastapi.testclient import TestClient
import logging

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.unit]


@pytest.fixture(scope="module")
def mock_config_and_fs(test_mock_model_config: dict, test_mock_model_file: str):
    """Mock configuration and filesystem before app starts"""
    from _pytest.monkeypatch import MonkeyPatch
    monkeypatch = MonkeyPatch()

    import miloco_ai_engine.config.config as cfg
    monkeypatch.setattr(cfg, "_config", test_mock_model_config)
    monkeypatch.setattr(cfg, "MODELS_CONFIG", test_mock_model_config["models"])

    import os
    real_exists = os.path.exists
    real_isfile = os.path.isfile

    def _exists(path):
        if str(path).endswith(test_mock_model_file):
            return True
        return real_exists(path)

    def _isfile(path):
        if str(path).endswith(test_mock_model_file):
            return True
        return real_isfile(path)

    monkeypatch.setattr(os.path, "exists", _exists)
    monkeypatch.setattr(os.path, "isfile", _isfile)

    try:
        yield
    finally:
        monkeypatch.undo()


@pytest.fixture(scope="module")
def mock_mico_clib(test_mock_mico_clib):
    from _pytest.monkeypatch import MonkeyPatch
    monkeypatch = MonkeyPatch()

    import miloco_ai_engine.core_python.lib_manager as lm
    # Reset library manager singleton state before mocking
    monkeypatch.setattr(lm.lib_manager, "_library", None)
    monkeypatch.setattr(lm.lib_manager, "_function_loaded", False)
    monkeypatch.setattr(lm.lib_manager, "get_library",
                        lambda: test_mock_mico_clib)
    monkeypatch.setattr(lm, "get_library", lambda: test_mock_mico_clib)
    try:
        yield
    finally:
        monkeypatch.undo()


@pytest.fixture(scope="module", autouse=True)
def test_client_mock(mock_config_and_fs, mock_mico_clib):
    """Test client with mocked config - only auto-use for unit tests (non-integration)"""
    logger.info("test_client_mock")
    from miloco_ai_engine.main import app as _app
    with TestClient(_app) as c:
        yield c


@pytest.mark.dependency()
def test_root(test_client_mock: TestClient):
    resp = test_client_mock.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


@pytest.mark.dependency(depends=["test_root"])
def test_list_models(test_client_mock: TestClient, test_mock_model_name: str):
    resp = test_client_mock.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data and isinstance(data["data"], list)
    print([m.get("id") for m in data["data"]])
    assert any(m.get("id") == test_mock_model_name for m in data["data"])


@pytest.mark.dependency(depends=["test_list_models"])
def test_model_load(test_client_mock: TestClient, test_mock_model_name: str):
    r = test_client_mock.post(
        "/models/load", params={"model_name": test_mock_model_name})
    assert r.status_code in (200, 204)


@pytest.mark.dependency(depends=["test_list_models"])
def test_model_unload(test_client_mock: TestClient, test_mock_model_name: str):
    r = test_client_mock.post(
        "/models/unload", params={"model_name": test_mock_model_name})
    assert r.status_code in (200, 204)


@pytest.mark.dependency(depends=["test_model_load", "test_model_unload"])
def test_chat_completions_stream(test_client_mock: TestClient, test_mock_model_name: str, test_mock_payload_stream: dict):
    # ensure model loaded
    r = test_client_mock.post(
        "/models/load", params={"model_name": test_mock_model_name})
    assert r.status_code in (200, 204)
    with test_client_mock.stream("POST", "/v1/chat/completions", json=test_mock_payload_stream) as r:
        chunks = [line for line in r.iter_lines() if line.startswith("data: ")]
        assert chunks[-1] == "data: [DONE]"
        first = json.loads(chunks[0].split("data: ", 1)[1])
        second = json.loads(chunks[1].split("data: ", 1)[1])
        assert first["choices"][0]["delta"]["content"] == "hello world"
        assert second["choices"][0]["delta"]["content"] == ""
        assert second["choices"][0]["delta"]["tool_calls"][0]["type"] == "function"
        assert second["choices"][0]["delta"]["tool_calls"][0]["function"] == {
            "name": "get_weather", "arguments": "{\"city\": \"Beijing\"}"}


@pytest.mark.dependency(depends=["test_model_load", "test_model_unload"])
def test_chat_completions_non_stream(test_client_mock: TestClient, test_mock_model_name: str, test_mock_payload: dict):
    # ensure model loaded
    r = test_client_mock.post(
        "/models/load", params={"model_name": test_mock_model_name})
    assert r.status_code in (200, 204)

    resp = test_client_mock.post(
        "/v1/chat/completions", json=test_mock_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "choices" in data and data["choices"]
    assert data["choices"][0]["message"]["content"] == "hello world"
    assert data["choices"][0]["message"]["tool_calls"][0]["type"] == "function"
    assert data["choices"][0]["message"]["tool_calls"][0]["function"] == {
        "name": "get_weather", "arguments": "{\"city\": \"Beijing\"}"}
