from __future__ import annotations
from unittest.mock import patch
from irc.llm._types import ResolvedRoute
from irc.llm.http_client import ChatResponse
from irc.memo.synthesizer import synthesize_memo
from irc.memo.auditor import audit_memo
from irc.memo.traceability import check_traceability


def _route() -> ResolvedRoute:
    return ResolvedRoute(task="t", provider="openai", model="gpt-4", base_url="http://x", api_key_env="K")


def _response(text: str) -> ChatResponse:
    return ChatResponse(text=text, prompt_tokens=10, completion_tokens=20, latency_ms=100, raw={})


def test_synthesize_calls_llm():
    with patch("irc.memo.synthesizer.call_chat", return_value=_response("memo body")) as m:
        resp = synthesize_memo(skeleton="# skel", raw_ref_pool=["ref1"], route=_route())
    assert m.called
    assert resp.text == "memo body"


def test_audit_calls_llm():
    with patch("irc.memo.auditor.call_chat", return_value=_response("审核通过")) as m:
        resp = audit_memo(draft="Some memo", route=_route())
    assert m.called
    assert "审核" in resp.text


def test_traceability_full_coverage():
    result = check_traceability(memo_text="ref1 ref2", raw_refs=["ref1", "ref2"])
    assert result["n_refs_quoted_verbatim"] == 2
    assert result["n_refs_provided"] == 2


def test_traceability_partial_missing():
    result = check_traceability(memo_text="ref1", raw_refs=["ref1", "ref2"])
    assert result["n_refs_quoted_verbatim"] == 1
    assert result["n_refs_provided"] == 2
