import os
from copy import deepcopy
from uuid import UUID

import pytest
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.simulation.models import SimulationRun
from test_identity_integration import accounts, create
from test_operations_integration import add, order, seed
from test_twin_integration import PERIOD, save

pytestmark = [pytest.mark.integration,pytest.mark.skipif(os.getenv("RUN_INTEGRATION")!="1",reason="Requires migrated PostgreSQL/Redis")]


def setup(owner,headers):
    business=create(owner,headers)
    path=f"/api/v1/businesses/{business['id']}"
    seed(owner,headers,path)
    add(owner,headers,path,"orders",[order()])
    owner.put(path+"/expense-coverage",headers=headers,json={"start_date":PERIOD["start"],"end_date":PERIOD["end"],"complete":True})
    return path, save(owner,headers,path)


def simulate(owner,headers,path,snapshot,**changes):
    body={"name":"Assumed scenario","baseline_snapshot_id":snapshot["id"]}|changes
    preview=owner.post(path+"/simulations/preview",headers=headers,json=body)
    assert preview.status_code==200,preview.text
    response=owner.post(path+"/simulations/runs",headers=headers,json=body|{"preview_hash":preview.json()["preview_hash"],"assumptions_confirmed":True})
    assert response.status_code==201,response.text
    return response.json()


def test_preview_confirmation_replay_export_and_no_operational_mutations(accounts):
    owner,_,headers,_,_,_,_=accounts
    path,snapshot=setup(owner,headers)
    current=f"{path}/twin/current?start={PERIOD['start']}&end={PERIOD['end']}"
    before=owner.get(current).json()["state"]["source_versions"]
    body={"name":"Price assumption","baseline_snapshot_id":snapshot["id"],"price_change_pct":"10","price_elasticity":"-1"}
    preview=owner.post(path+"/simulations/preview",headers=headers,json=body).json()
    assert preview["persisted"] is False and owner.get(path+"/simulations/runs").json()==[]
    stale=owner.post(path+"/simulations/runs",headers=headers,json=body|{"demand_change_pct":"20","preview_hash":preview["preview_hash"],"assumptions_confirmed":True})
    assert stale.status_code==409
    assert owner.post(path+"/simulations/runs",headers=headers,json=body|{"preview_hash":preview["preview_hash"],"assumptions_confirmed":False}).status_code==422
    run=simulate(owner,headers,path,snapshot)
    route=path+"/simulations/runs/"+run["id"]
    assert run["integrity"]=="verified_and_reproduced" and run["result"]["metrics"]==run["result"]["baseline_metrics"]
    assert owner.get(current).json()["state"]["source_versions"]==before
    csv=owner.get(route+"/export")
    assert csv.status_code==200 and "text/csv" in csv.headers["content-type"]
    assert "HYPOTHETICAL SIMULATION" in csv.text and run["baseline_hash"] in csv.text
    assert "attachment" in csv.headers["content-disposition"]
    second=simulate(owner,headers,path,snapshot,demand_change_pct="100")
    comparison=owner.get(path+f"/simulations/compare?left={run['id']}&right={second['id']}").json()
    assert comparison["changes"]["revenue"]["absolute_change"]=="28.00"
    original=owner.get(route).json()
    sale=owner.get(path+"/orders").json()["items"][0]
    owner.patch(path+"/orders/"+sale["id"],headers=headers,json={"status":"refunded","reason":"After saved simulation"})
    assert owner.get(route).json()==original
    assert any(row["event"]=="simulation.completed" for row in owner.get(path+"/audit-logs").json())


def test_simulation_tenants_roles_and_database_guard(accounts):
    owner,other,headers,other_headers,_,other_account,connection=accounts
    path,snapshot=setup(owner,headers)
    business_id=UUID(path.rsplit("/",1)[-1])
    run=simulate(owner,headers,path,snapshot)
    route=path+"/simulations/runs/"+run["id"]
    second=create(owner,headers,name="Separate")
    otherpath=f"/api/v1/businesses/{second['id']}"
    assert other.get(route).status_code==404
    assert owner.get(otherpath+"/simulations/runs/"+run["id"]).status_code==404
    assert owner.post(otherpath+"/simulations/preview",headers=headers,json={"name":"Foreign baseline","baseline_snapshot_id":snapshot["id"]}).status_code==404
    assert owner.get(otherpath+f"/simulations/compare?left={run['id']}&right={run['id']}").status_code==404
    owner.post(path+"/members",headers=headers,json={"email":other_account["user"]["email"],"role":"viewer"})
    assert other.get(route).status_code==200 and other.get(route+"/export").status_code==200
    assert other.post(path+"/simulations/preview",headers=other_headers,json={"name":"Denied","baseline_snapshot_id":snapshot["id"]}).status_code==403
    owner.patch(path+"/members/"+other_account["user"]["id"],headers=headers,json={"role":"analyst"})
    simulate(other,other_headers,path,snapshot,name="Analyst assumption")
    with Session(connection,join_transaction_mode="create_savepoint") as db:
        with pytest.raises(DBAPIError):
            db.execute(update(SimulationRun).where(SimulationRun.id==UUID(run["id"])).values(name="Rewrite"))
        db.rollback()
    with Session(connection,join_transaction_mode="create_savepoint") as db:
        original=db.get(SimulationRun,UUID(run["id"]))
        copy=SimulationRun(business_id=UUID(second["id"]),baseline_snapshot_id=UUID(snapshot["id"]),name="Wrong tenant",implementation_version="1",baseline_hash=original.baseline_hash,parameters=original.parameters,result=original.result,content_hash=original.content_hash)
        db.add(copy)
        with pytest.raises(IntegrityError) as failure: db.flush()
        assert failure.value.orig.diag.constraint_name=="fk_simulation_tenant_snapshot"
        db.rollback()


def test_invalid_targets_empty_baselines_and_cross_baseline_comparison(accounts):
    owner,_,headers,_,_,_,_=accounts
    path,snapshot=setup(owner,headers)
    base={"name":"Invalid","baseline_snapshot_id":snapshot["id"]}
    for changes in [{"price_change_pct":"10"},{"product_sku":"FOREIGN"},{"supplier_external_id":"FOREIGN"},{"customer_loss_pct":"101"}]:
        assert owner.post(path+"/simulations/preview",headers=headers,json=base|changes).status_code==422
    first=simulate(owner,headers,path,snapshot)
    newer=save(owner,headers,path,"Another baseline")
    second=simulate(owner,headers,path,newer)
    assert owner.get(path+f"/simulations/compare?left={first['id']}&right={second['id']}").status_code==422
    empty=save(owner,headers,path,"No paid sales",start="2026-01-01",end="2026-01-02")
    assert owner.post(path+"/simulations/preview",headers=headers,json=base|{"baseline_snapshot_id":empty["id"]}).status_code==422
