import io
import json
from zipfile import ZipFile

import httpx
import pytest

from app.documents.extraction import Section, chunk_sections, extract, validate_upload
from app.documents.provider import CompatibleProvider, ProviderError
from app.documents.rag import validate_citations


def test_text_headings_overlap_and_table_extraction():
    pieces = chunk_sections(extract("policy.txt", b"# Returns\n\nReturns are accepted within thirty days."))
    assert pieces[-1].heading == "Returns" and "thirty days" in pieces[-1].text
    long = "word " * 500
    pieces = chunk_sections([Section(long, page=2, heading="Policy")], size=400, overlap=50)
    assert len(pieces) > 1 and all(piece.page == 2 for piece in pieces)
    assert pieces[0].text[-50:] == pieces[1].text[:50]
    table = extract("policy.csv", b"Name,Days\nReturns,30\n")
    assert table[0].kind == "table" and table[0].text == "Name: Returns | Days: 30"


def test_docx_preserves_headings_and_tables():
    raw = io.BytesIO()
    with ZipFile(raw, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Policy</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Returns</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>30 days</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
    sections = extract("policy.docx", raw.getvalue())
    assert sections[1] == Section("Returns | 30 days", heading="Policy", kind="table")


@pytest.mark.parametrize("name,raw", [("a.exe", b"x"), ("a.pdf", b"invalid"), ("a.txt", b""), ("a.docx", b"invalid"), ("a.txt", b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE")])
def test_reject_invalid_uploads(name, raw):
    with pytest.raises(ValueError):
        validate_upload(name, raw)


def test_scanned_pdf_reports_ocr_requirement(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "ocr_url", "")
    from pypdf import PdfWriter
    book = PdfWriter()
    book.add_blank_page(width=100, height=100)
    raw = io.BytesIO()
    book.write(raw)
    with pytest.raises(ValueError, match="OCR"):
        extract("scan.pdf", raw.getvalue())


def test_citations_must_use_retrieved_ids_and_exact_excerpts():
    source = {"chunk_id": "real", "excerpt": "Returns are accepted within thirty days.", "title": "Policy"}
    answer = {"answer": "Thirty days.", "insufficient": False, "citations": [{"chunk_id": "real", "quote": source["excerpt"]}]}
    assert validate_citations(answer, [source])[1][0]["title"] == "Policy"
    for invalid in [{"chunk_id": "invented", "quote": source["excerpt"]}, {"chunk_id": "real", "quote": "Returns accepted for ninety days."}]:
        with pytest.raises(ProviderError):
            validate_citations(answer | {"citations": [invalid]}, [source])


def test_compatible_adapter_validates_embeddings_and_answer_contract(monkeypatch):
    provider = CompatibleProvider()
    provider.url, provider.embedding_model, provider.chat_model = "http://test/v1", "test-embed", "test-chat"
    requests = []
    def request(path, payload):
        requests.append((path, payload))
        if path == "/embeddings":
            return {"data": [{"index": 0, "embedding": [1, 0]}], "usage": {"total_tokens": 3}}
        return {"choices": [{"message": {"content": json.dumps({"answer": "Not established", "insufficient": True, "citations": []})}}]}
    monkeypatch.setattr(provider, "request", request)
    assert provider.embed(["Policy"])[0] == [[1.0, 0.0]]
    assert provider.answer("What?", [], [])[0]["insufficient"]
    assert "untrusted" in requests[-1][1]["messages"][0]["content"]
    monkeypatch.setattr(provider, "request", lambda *_: {"data": [{"index": 0, "embedding": [float("nan")]}]})
    with pytest.raises(ProviderError):
        provider.embed(["Policy"])


def test_provider_failure_does_not_fabricate_a_response(monkeypatch):
    provider = CompatibleProvider()
    provider.url = "http://test/v1"
    class FailureClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def stream(self, *args, **kwargs): raise httpx.ConnectError("offline")
    monkeypatch.setattr(httpx, "Client", FailureClient)
    monkeypatch.setattr("app.documents.provider.time.sleep", lambda _: None)
    with pytest.raises(ProviderError, match="unavailable"):
        provider.request("/embeddings", {})


def test_ocr_adapter_preserves_real_page_numbers(monkeypatch):
    from app.core.config import get_settings
    from app.documents.ocr import pdf_pages
    monkeypatch.setattr(get_settings(), "ocr_url", "http://fixture/ocr")
    requests = []
    class OCRClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def stream(self, method, url, **kwargs):
            requests.append((method, url, kwargs))
            return self
        status_code = 200
        def iter_bytes(self):
            yield b'{"pages":[{"number":2,"text":"Real scanned policy text"}]}'
    monkeypatch.setattr(httpx, "Client", OCRClient)
    assert pdf_pages(b"%PDF-fixture") == {2: "Real scanned policy text"}
    assert requests[0][2]["headers"]["Content-Type"] == "application/pdf"
