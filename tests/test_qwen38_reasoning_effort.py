from types import SimpleNamespace

from weird_captcha_gym.evaluation import qwen38


def test_qwen38_forwards_reasoning_effort(monkeypatch):
    captured = {}
    client_options = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            message = SimpleNamespace(
                reasoning=None,
                reasoning_content=None,
                content="done",
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class Client:
        def __init__(self, **kwargs):
            client_options.update(kwargs)
            self.chat = SimpleNamespace(completions=Completions())

    monkeypatch.setattr(qwen38.openai, "OpenAI", Client)

    result = qwen38.call_qwen38_with_timeout(
        messages=[{"role": "user", "content": "test"}],
        model="Qwen/Qwen3.8-27B",
        temperature=0.6,
        top_p=0.95,
        top_k=20,
        reasoning_effort="low",
        request_timeout_seconds=900,
    )

    assert result == "done"
    assert captured["reasoning_effort"] == "low"
    assert "user" not in captured
    assert client_options["timeout"] == 900
