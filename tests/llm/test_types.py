from irc.llm._types import ChatResponse


def test_chat_response_raw_is_optional_and_drops_when_disabled(monkeypatch):
    monkeypatch.setenv("IRC_PERSIST_LLM_RAW", "0")
    r = ChatResponse(text="hi", prompt_tokens=1, completion_tokens=1, raw=None)
    assert r.raw is None


def test_chat_response_raw_defaults_to_none():
    r = ChatResponse(text="hi", prompt_tokens=1, completion_tokens=1)
    assert r.raw is None
