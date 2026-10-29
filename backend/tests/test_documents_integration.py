import os
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.documents import pipeline, rag
from app.documents.models import DocumentVersion, RagConversation
from test_identity_integration import accounts, create

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="Requires migrated PostgreSQL/Redis")]


class TestProvider:
    """Deterministic test double only; never installed in production configuration."""
    __test__ = False
    embeddings_configured = True
    chat_configured = True
    embedding_model = "fixture-model"
    chat_model = "fixture-chat"
    identity = "fixture-model-v1"
    def health_status(self): return "Test fixture only"
    def embed_query(self, question): return self.embed([question])
    def embed(self, texts): return [[1.0, 0.0, 0.0] for text in texts], {"embedding_tokens": len(texts)}
    def answer(self, question, sources, previous):
        self.last_sources = sources
        return {"answer": "Returns are accepted within thirty days.", "insufficient": False, "citations": [{"chunk_id": sources[0]["chunk_id"], "quote": sources[0]["excerpt"][:200]}]}, {"total_tokens": 10}


@pytest.fixture
def processing(accounts, monkeypatch):
    connection = accounts[-1]
    provider = TestProvider()
    monkeypatch.setattr("app.documents.router.enqueue", lambda *_: None)
    monkeypatch.setattr(pipeline, "get_engine", lambda: connection)
    monkeypatch.setattr(pipeline, "Session", lambda *args, **kwargs: Session(connection, expire_on_commit=False, join_transaction_mode="create_savepoint"))
    monkeypatch.setattr(pipeline, "get_provider", lambda: provider)
    monkeypatch.setattr(rag, "get_provider", lambda: provider)
    monkeypatch.setattr("app.documents.router.get_provider", lambda: provider)
    return accounts, provider


def upload(owner, headers, path, title="Policy", visibility="team", document_id=None, text=b"Returns are accepted within thirty days."):
    params = {"title": title, "filename": "policy.txt", "visibility": visibility}
    if document_id: params["document_id"] = document_id
    response = owner.post(path + "/documents", headers=headers, params=params, content=text)
    assert response.status_code == 202, response.text
    return response.json()


def test_ingestion_hybrid_retrieval_versions_and_citations(processing):
    accounts, provider = processing
    owner, _, headers, _, _, _, _ = accounts
    business = create(owner, headers)
    path = f"/api/v1/businesses/{business['id']}"
    first = upload(owner, headers, path)
    assert first["status"] == "queued"
    pipeline.process_version(first["id"])
    document = owner.get(path + "/documents").json()[0]
    assert document["active_version"] == 1 and document["versions"][0]["status"] == "ready"
    response = owner.post(path + "/rag/ask", headers=headers, json={"question": "What is the return policy?"})
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["citations"][0]["document_id"] == first["document_id"]
    assert answer["citations"][0]["excerpt"] == "Returns are accepted within thirty days."
    second = upload(owner, headers, path, document_id=first["document_id"], text=b"Returns are accepted within fourteen days.")
    pipeline.process_version(second["id"])
    search = owner.post(path + "/rag/search", headers=headers, json={"question": "Returns policy"})
    assert search.status_code == 200, search.text
    assert all(source["version"] == 2 and "fourteen" in source["excerpt"] for source in search.json()["sources"])
    assert owner.get(path + f"/documents/{first['document_id']}/versions/{first['id']}/chunks").json()[0]["content"] == "Returns are accepted within thirty days."
    repeated = upload(owner, headers, path, document_id=first["document_id"], text=b"Returns are accepted within fourteen days.")
    assert repeated["id"] == second["id"]


def test_document_and_conversation_access_precede_provider(processing):
    accounts, provider = processing
    owner, other, headers, other_headers, _, other_identity, _ = accounts
    business = create(owner, headers)
    separate = create(owner, headers, name="Separate")
    path = f"/api/v1/businesses/{business['id']}"
    restricted = upload(owner, headers, path, title="Secret policy", visibility="administrators", text=b"Secret supplier discount is fifty percent.")
    pipeline.process_version(restricted["id"])
    public = upload(owner, headers, path)
    pipeline.process_version(public["id"])
    assert owner.post(path + "/members", headers=headers, json={"email": other_identity["user"]["email"], "role": "viewer"}).status_code == 201
    assert len(other.get(path + "/documents").json()) == 1
    assert other.get(path + f"/documents/{restricted['document_id']}/versions/{restricted['id']}/chunks").status_code == 404
    assert other.post(path + "/documents", headers=other_headers, params={"filename": "x.txt", "title": "Denied"}, content=b"Denied").status_code == 403
    result = other.post(path + "/rag/ask", headers=other_headers, json={"question": "What are supplier terms?"})
    assert result.status_code == 200, result.text
    assert all(source["title"] != "Secret policy" for source in provider.last_sources)
    conversation = result.json()["conversation_id"]
    assert owner.post(path + "/rag/ask", headers=headers, json={"question": "Follow-up question", "conversation_id": conversation}).status_code == 404
    assert other.get(f"/api/v1/businesses/{separate['id']}/documents").status_code == 404
    assert owner.post(f"/api/v1/businesses/{separate['id']}/rag/ask", headers=headers, json={"question": "Follow up", "conversation_id": conversation}).status_code == 404


def test_missing_provider_and_invalid_citations_are_explicit(processing, monkeypatch):
    accounts, provider = processing
    owner, _, headers, _, _, _, connection = accounts
    business = create(owner, headers)
    path = f"/api/v1/businesses/{business['id']}"
    provider.embeddings_configured = False
    version = upload(owner, headers, path)
    pipeline.process_version(version["id"])
    result = owner.get(path + "/documents").json()[0]
    assert result["versions"][0]["status"] == "awaiting_configuration" and result["active_version"] == 0
    assert owner.post(path + "/rag/ask", headers=headers, json={"question": "Returns policy?"}).status_code == 503
    provider.embeddings_configured = True
    pipeline.process_version(version["id"])
    monkeypatch.setattr(provider, "answer", lambda *_: ({"answer": "Forged", "insufficient": False, "citations": [{"chunk_id": "forged", "quote": "Made up quotation"}]}, {}))
    assert owner.post(path + "/rag/ask", headers=headers, json={"question": "Returns policy?"}).status_code == 503
    with Session(connection, join_transaction_mode="create_savepoint") as db:
        assert db.scalar(select(RagConversation).where(RagConversation.business_id == UUID(business["id"]))) is None


def test_evaluation_records_measured_results_and_pending_human_review(processing):
    accounts, _ = processing
    owner, _, headers, _, _, _, _ = accounts
    business = create(owner, headers)
    path = f"/api/v1/businesses/{business['id']}"
    assert owner.get(path + "/rag/status").json()["evaluation"] is None
    version = upload(owner, headers, path)
    pipeline.process_version(version["id"])
    response = owner.post(path + "/rag/evaluate", headers=headers, json={"cases": [{"question": "What is the return policy?", "expected_document_ids": [version["document_id"]], "expected_answer": "thirty days"}]})
    assert response.status_code == 200, response.text
    metrics = response.json()
    assert metrics["document_recall_at_5_chunks"] == 1 and metrics["mean_reciprocal_rank"] == 1
    assert metrics["citation_integrity"] == 1 and "Not evaluated" in metrics["answer_faithfulness"]
    assert owner.get(path + "/rag/status").json()["evaluation"]["cases"] == 1
