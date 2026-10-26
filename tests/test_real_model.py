import json

import pytest

from scheduler.real_model import OpenAICompatibleModel


def test_real_model_passes_configured_timeout_to_urlopen(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": '{"final":"ok"}'}}]}).encode()

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setattr("scheduler.real_model.urllib.request.urlopen", fake_urlopen)

    model = OpenAICompatibleModel(timeout_seconds=2.5)
    # json.load calls read() on the response context manager.
    assert model.complete([{"role": "user", "content": "hello"}]) == '{"final":"ok"}'
    assert captured["timeout"] == 2.5


def test_real_model_rejects_non_positive_timeout():
    with pytest.raises(ValueError, match="positive"):
        OpenAICompatibleModel(timeout_seconds=0)
