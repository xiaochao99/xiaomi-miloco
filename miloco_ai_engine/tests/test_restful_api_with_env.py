# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

# pylint: disable=import-outside-toplevel, unused-argument, missing-function-docstring, line-too-long, C0114, W0621
import pytest
import json
from fastapi.testclient import TestClient
import logging

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.integration]


@pytest.fixture(scope="module")
def test_client_real():
    """Test client without mocking (uses real config/clib)"""
    import importlib
    import miloco_ai_engine.config.config as cfg
    import miloco_ai_engine.model_manager.model_manager as mm
    import miloco_ai_engine.main as main

    # Ensure integration tests see fresh, real configs and clean module state
    importlib.reload(cfg)
    importlib.reload(mm)
    importlib.reload(main)

    _app = main.app
    with TestClient(_app) as c:
        yield c


@pytest.mark.dependency()
def test_root(test_client_real: TestClient):
    """Verify root endpoint is running"""
    resp = test_client_real.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


@pytest.mark.dependency(depends=["test_root"])
def test_list_models(test_client_real: TestClient):
    """Verify models list API returns correct models"""
    resp = test_client_real.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data and isinstance(data["data"], list)
    assert len(data["data"]) > 0


@pytest.mark.dependency(depends=["test_list_models"])
def test_model_lifecycle(test_client_real: TestClient):
    """Verify model load/unload lifecycle"""
    # Get the first available model
    models_resp = test_client_real.get("/v1/models")
    model_name = models_resp.json()["data"][0]["id"]

    # Load model
    load_resp = test_client_real.post(
        "/models/load", params={"model_name": model_name})
    assert load_resp.status_code in (200, 204)

    # Unload model
    unload_resp = test_client_real.post(
        "/models/unload", params={"model_name": model_name})
    assert unload_resp.status_code in (200, 204)


@pytest.mark.dependency(depends=["test_model_lifecycle"])
def test_chat_completions_stream(test_client_real: TestClient, test_mock_payload_stream: dict):
    """Verify streaming chat completions API"""
    # Get and load the first model
    models_resp = test_client_real.get("/v1/models")
    model_name = models_resp.json()["data"][0]["id"]
    test_client_real.post("/models/load", params={"model_name": model_name})

    payload = test_mock_payload_stream.copy()
    payload["model"] = model_name
    with test_client_real.stream("POST", "/v1/chat/completions", json=payload) as r:
        chunks = [line for line in r.iter_lines() if line.startswith("data: ")]
        assert len(chunks) > 0
        assert chunks[-1] == "data: [DONE]"

        # Validate the structure of the first chunk
        first_chunk = json.loads(chunks[0].split("data: ", 1)[1])
        assert "choices" in first_chunk
        assert len(first_chunk["choices"]) > 0


@pytest.mark.dependency(depends=["test_model_lifecycle"])
def test_chat_completions_non_stream(test_client_real: TestClient, test_mock_payload: dict):
    """Verify non-streaming chat completions API"""
    # Get and load the first model
    models_resp = test_client_real.get("/v1/models")
    model_name = models_resp.json()["data"][0]["id"]
    test_client_real.post("/models/load", params={"model_name": model_name})

    payload = test_mock_payload.copy()
    payload["model"] = model_name
    resp = test_client_real.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    # Validate response structure
    assert "choices" in data
    assert len(data["choices"]) > 0
    choice = data["choices"][0]
    assert "message" in choice
    assert "content" in choice["message"] or "tool_calls" in choice["message"]
