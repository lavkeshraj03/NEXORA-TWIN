import csv
import io
import json
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.businesses import access
from app.core.security import current_user, rate_limit
from app.data.service import json_ready
from app.db.session import get_session
from app.ml.datasets import fingerprint
from app.models import AuditLog, User
from app.simulation.engine import VERSION, calculate, difference
from app.simulation.models import SimulationRun
from app.simulation.schemas import RunInput, ScenarioInput
from app.twin.router import owned as owned_snapshot
from app.twin.service import verified as verified_snapshot

router = APIRouter(prefix="/businesses/{business_id}/simulations", tags=["What-If Lab"])


def compute(db, business_id, data):
    snapshot = owned_snapshot(db, business_id, data.baseline_snapshot_id)
    verified_snapshot(snapshot)
    parameters = data.model_dump(mode="json", include=set(ScenarioInput.model_fields))
    preview_hash = fingerprint({"implementation_version":VERSION, "baseline_hash":snapshot.content_hash, "parameters":parameters})
    try:
        result = calculate(snapshot.payload["inputs"], parameters)
    except ValueError as error:
        raise HTTPException(422, str(error))
    return snapshot, parameters, result, preview_hash


def digest(baseline_hash, parameters, result):
    return fingerprint({"implementation_version":VERSION, "baseline_hash":baseline_hash, "parameters":parameters, "result":result})


def owned(db, business_id, run_id):
    row = db.scalar(select(SimulationRun).where(SimulationRun.business_id == business_id, SimulationRun.id == run_id))
    if row is None: raise HTTPException(404, "Simulation run not found")
    return row


def detail(db, row):
    if row.implementation_version != VERSION or str(row.baseline_snapshot_id) != row.parameters["baseline_snapshot_id"] or row.content_hash != digest(row.baseline_hash, row.parameters, row.result):
        raise HTTPException(409, "Simulation integrity/version check failed")
    baseline, _, result, _ = compute(db, row.business_id, ScenarioInput.model_validate(row.parameters))
    if baseline.content_hash != row.baseline_hash or result != row.result:
        raise HTTPException(409, "Simulation does not reproduce from its saved baseline and parameters")
    return json_ready({"id":row.id, "name":row.name, "baseline_snapshot_id":row.baseline_snapshot_id, "baseline_hash":row.baseline_hash, "content_hash":row.content_hash, "implementation_version":row.implementation_version, "created_at":row.created_at, "parameters":row.parameters, "result":result, "integrity":"verified_and_reproduced"})


@router.post("/preview")
def preview(business_id: UUID, data: ScenarioInput, user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "simulation:run", lock=True)
    rate_limit(f"simulation-preview:{business_id}:{user.id}", 60, 3600)
    snapshot, parameters, result, preview_hash = compute(db, business_id, data)
    return {"preview_hash":preview_hash, "baseline_hash":snapshot.content_hash, "parameters":parameters, "result":result, "persisted":False}


@router.post("/runs", status_code=201)
def run(business_id: UUID, data: RunInput, user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "simulation:run", lock=True)
    rate_limit(f"simulation-run:{business_id}:{user.id}", 20, 3600)
    if db.scalar(select(func.count()).select_from(SimulationRun).where(SimulationRun.business_id == business_id)) >= 40:
        raise HTTPException(422, "This release retains at most 40 simulation runs per business")
    snapshot, parameters, result, preview_hash = compute(db, business_id, data)
    if preview_hash != data.preview_hash:
        raise HTTPException(409, "Parameters or baseline differ from the reviewed preview; preview again")
    row = SimulationRun(business_id=business_id, created_by=user.id, baseline_snapshot_id=snapshot.id, name=data.name,
        implementation_version=VERSION, baseline_hash=snapshot.content_hash, parameters=parameters, result=result,
        content_hash=digest(snapshot.content_hash, parameters, result))
    db.add(row)
    db.flush()
    db.add(AuditLog(business_id=business_id, user_id=user.id, event="simulation.completed", target_id=str(row.id)))
    db.commit()
    return detail(db, row)


@router.get("/runs")
def runs(business_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "simulation:read")
    query = select(SimulationRun.id, SimulationRun.name, SimulationRun.baseline_snapshot_id, SimulationRun.created_at, SimulationRun.content_hash)
    return json_ready([dict(row) for row in db.execute(query.where(SimulationRun.business_id == business_id).order_by(SimulationRun.created_at.desc(), SimulationRun.id.desc()).limit(40)).mappings()])


@router.get("/compare")
def compare_runs(business_id: UUID, left: UUID, right: UUID, user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "simulation:read")
    a, b = detail(db, owned(db,business_id,left)), detail(db, owned(db,business_id,right))
    if a["baseline_snapshot_id"] != b["baseline_snapshot_id"]:
        raise HTTPException(422, "Compare scenarios using the same baseline snapshot")
    before = {key:Decimal(str(value)) if value is not None else None for key,value in a["result"]["metrics"].items()}
    after = {key:Decimal(str(value)) if value is not None else None for key,value in b["result"]["metrics"].items()}
    return json_ready({"left_id":left, "right_id":right, "baseline_snapshot_id":a["baseline_snapshot_id"], "changes":difference(before,after), "definition":"Right hypothetical scenario minus left; both use the same saved baseline. The baseline/scenario columns below refer to these two scenarios."})


@router.get("/runs/{run_id}")
def saved(business_id: UUID, run_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "simulation:read")
    return detail(db, owned(db,business_id,run_id))


@router.get("/runs/{run_id}/export")
def export(business_id: UUID, run_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "simulation:read")
    row = detail(db, owned(db,business_id,run_id))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["HYPOTHETICAL SIMULATION — not actual results or a guaranteed forecast"])
    metadata = {"name":row["name"], "business":owned_snapshot(db,business_id,UUID(row["baseline_snapshot_id"])).payload["inputs"]["business"]["name"], "baseline_snapshot_id":row["baseline_snapshot_id"], "baseline_hash":row["baseline_hash"], "simulation_hash":row["content_hash"], "implementation_version":VERSION,
        "created_at":row["created_at"], "baseline_period":row["result"]["baseline_period"], "baseline_captured_at":row["result"]["baseline_captured_at"], "currency":row["result"]["currency"], "demo_records_present":row["result"]["demo_records_present"], "assumptions":row["parameters"], "methodology":row["result"]["methodology"], "warnings":row["result"]["warnings"], "replenishment_cash_outlay":row["result"]["replenishment_cash_outlay"]}
    for key,value in metadata.items():
        cell = json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else str(value)
        writer.writerow([key, "'"+cell if cell.lstrip().startswith(("=","+","-","@")) else cell])
    writer.writerow([])
    writer.writerow(["metric","baseline","scenario","absolute_change","percentage_change","unit"])
    for key,value in row["result"]["changes"].items():
        writer.writerow([key,*[value[field] for field in ["baseline","scenario","absolute_change","percentage_change","unit"]]])
    writer.writerow([])
    writer.writerow(["inventory",json.dumps(row["result"]["inventory"],ensure_ascii=False)])
    writer.writerow(["sensitivity",json.dumps(row["result"]["sensitivity"],ensure_ascii=False)])
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition":f'attachment; filename="simulation-{run_id}.csv"', "Cache-Control":"no-store"})
