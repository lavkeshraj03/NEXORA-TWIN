import json
import time
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.analyst.provider import AnalystModel
from app.analyst.schemas import InvestigationInput
from app.documents.ollama_provider import OllamaProvider
from app.documents.provider import ProviderError


def brain(monkeypatch, result):
    provider=OllamaProvider()
    provider.url="http://fixture.local";provider.chat_model="fixture-only"
    calls=[]
    def request(path,payload):
        calls.append((path,payload))
        return {"message":{"content":json.dumps(result)},"done_reason":"stop","prompt_eval_count":10,"eval_count":5}
    monkeypatch.setattr(provider,"request",request)
    monkeypatch.setattr("app.analyst.provider.get_provider",lambda:provider)
    return AnalystModel(),calls


def test_native_planner_is_bounded_and_never_requests_sql_or_free_tool_arguments(monkeypatch):
    model,calls=brain(monkeypatch,{"tools":["query_sales","query_expenses"]})
    plan=model.plan("Why did recorded profit change?",{"query_sales":"Sales","query_expenses":"Expenses"},{},time.monotonic()+60)
    assert plan.tools==["query_sales","query_expenses"]
    path,payload=calls[0]
    assert path=="/api/chat" and payload["think"] is False and payload["options"]["num_ctx"]==4096
    assert payload["format"]["additionalProperties"] is False
    assert model.usage[0]["completion_tokens"]==5


@pytest.mark.parametrize("result",[{"tools":["execute_sql"]},{"tools":["query_sales","query_sales"]},{"tools":["query_sales"],"business_id":"other"},{"tools":["query_sales"],"sql":"DELETE FROM orders"}])
def test_model_generated_unknown_or_injected_plan_fields_are_rejected(monkeypatch,result):
    model,_=brain(monkeypatch,result)
    with pytest.raises(ProviderError):model.plan("untrusted request",{"query_sales":"Sales"},{},time.monotonic()+60)


@pytest.mark.parametrize("result",[{"supported":True,"finding_ids":["FORGED"],"recommendation_ids":[]},{"supported":True,"finding_ids":["E1.F1"],"recommendation_ids":[],"answer":"Profit is 999999"},{"supported":"true","finding_ids":["E1.F1"],"recommendation_ids":[]},{"supported":False,"finding_ids":["E1.F1"],"recommendation_ids":[]}])
def test_synthesis_cannot_add_claims_or_forge_evidence(monkeypatch,result):
    model,_=brain(monkeypatch,result)
    with pytest.raises(ProviderError):model.select("question",[{"id":"E1.F1","text":"Exact calculated fact","kind":"calculated_historical"}],{},time.monotonic()+60)


def test_date_bounds_and_cross_tenant_extra_fields_are_validated():
    for changes in [{"start":"2026-10-29"},{"start":"2024-01-01"},{"business_id":str(uuid4())},{"model_data_scope":"all"},{"scenario_run_ids":[str(uuid4()) for _ in range(3)]}]:
        with pytest.raises(ValidationError):InvestigationInput.model_validate({"question":"What changed?","start":"2026-10-01","end":"2026-10-28"}|changes)


def test_time_budget_failure_does_not_generate_a_fallback(monkeypatch):
    model,calls=brain(monkeypatch,{"tools":[]})
    with pytest.raises(ProviderError,match="time budget"):model.plan("question",{}, {},time.monotonic()-1)
    assert calls==[]


@pytest.mark.parametrize("envelope",[[],{}, {"message":[]}, {"message":{"content":"not json"}}, {"message":{"content":"{}"},"done_reason":"length"}])
def test_malformed_provider_envelopes_fail_explicitly(monkeypatch,envelope):
    model,_=brain(monkeypatch,{"tools":[]})
    monkeypatch.setattr(model.provider,"request",lambda *_:envelope)
    with pytest.raises(ProviderError):model.plan("question",{"query_sales":"Sales"},{},time.monotonic()+60)
