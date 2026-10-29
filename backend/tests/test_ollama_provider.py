import json

import pytest

from app.documents.ollama_provider import OllamaProvider, QUERY_INSTRUCTION
from app.documents.provider import ProviderError
from app.documents.rag import validate_citations


def provider():
    instance = OllamaProvider()
    instance.url = "http://local-fixture:11434"
    instance.embedding_model = "qwen3-embedding:0.6b"
    instance.chat_model = "qwen3:1.7b"
    return instance


def test_query_instructions_are_separate_from_document_embeddings(monkeypatch):
    instance = provider()
    requests = []
    def request(path, payload):
        requests.append((path, payload))
        return {"embeddings": [[1, 0] for _ in payload["input"]], "prompt_eval_count": 5}
    monkeypatch.setattr(instance, "request", request)
    instance.embed(["Original document text"])
    instance.embed_query("What is the policy?")
    assert requests[0][1]["input"] == ["Original document text"]
    assert requests[1][1]["input"] == [QUERY_INSTRUCTION+"What is the policy?"]
    assert requests[1][1]["keep_alive"] == 0 and requests[1][1]["truncate"] is False


@pytest.mark.parametrize("vectors", [[], [[0, 0]], [[float("nan"), 1]], [[1], [2]]])
def test_local_embeddings_reject_bad_shapes_and_values(monkeypatch, vectors):
    instance = provider()
    monkeypatch.setattr(instance, "request", lambda *_: {"embeddings": vectors})
    with pytest.raises(ProviderError):
        instance.embed(["Policy"])


def test_small_model_uses_structured_non_thinking_bounded_output(monkeypatch):
    instance = provider()
    source = {"chunk_id": "real-chunk", "excerpt": "Returns are accepted within thirty days.", "title": "Policy"}
    answer = {"answer": "Thirty days.", "insufficient": False, "citations": [{"chunk_id": "real-chunk", "quote": source["excerpt"]}]}
    requests = []
    def request(path, payload):
        requests.append((path, payload))
        return {"message": {"content": json.dumps(answer)}, "done_reason": "stop", "eval_count": 20}
    monkeypatch.setattr(instance, "request", request)
    generated, usage = instance.answer("How long?", [source], ["Earlier question"])
    assert validate_citations(generated, [source])[1][0]["chunk_id"] == "real-chunk"
    path, payload = requests[0]
    assert path == "/api/chat" and payload["think"] is False and payload["keep_alive"] == 0
    assert payload["options"]["num_ctx"] == 4096 and payload["options"]["num_predict"] == 768
    assert payload["format"]["properties"]["citations"]["items"]["properties"]["chunk_id"]["enum"] == ["real-chunk"]
    assert usage["completion_tokens"] == 20


def test_truncated_local_answer_fails_without_a_fabricated_fallback(monkeypatch):
    instance = provider()
    monkeypatch.setattr(instance, "request", lambda *_: {"message": {"content": '{"answer":"Partial","insufficient":true,"citations":[]}'}, "done_reason": "length"})
    with pytest.raises(ProviderError, match="complete"):
        instance.answer("Question", [{"chunk_id": "one", "excerpt": "Actual text"}], [])
