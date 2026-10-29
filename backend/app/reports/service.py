import calendar
import json
from datetime import date,datetime,timezone
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from app.analyst.router import owned as owned_investigation
from app.api.businesses import access
from app.data.calculations import ZERO
from app.data.service import json_ready
from app.ml.datasets import fingerprint,closed_today
from app.ml.models import ModelRun
from app.ml.service import forecast_rows
from app.reports.models import GeneratedReport
from app.simulation.router import owned as owned_scenario,detail as scenario_detail
from app.twin.router import owned as owned_snapshot
from app.twin.service import verified as verified_snapshot

VERSION="1"


def section(title,columns,rows,note=""):
    return {"title":title,"columns":columns,"rows":rows,"note":note}


def generate_payload(db,business_id,user,data):
    business,member=access(db,user,business_id,"reports:create",lock=True)
    meta={"business_id":str(business.id),"business_name":business.name,"business_type":business.business_type,"currency":business.currency,"timezone":business.timezone,"generated_at":datetime.now(timezone.utc).isoformat(),"report_kind":data.kind,"name":data.name,"implementation_version":VERSION}
    sources,sections,assumptions,limits=[],[],[],[]
    meta|={"data_freshness":None,"reporting_period":None,"result_kind":None,"demo_records_present":False}
    if data.snapshot_id:
        access(db,user,business_id,"twin:read")
        snapshot=owned_snapshot(db,business_id,data.snapshot_id);state=verified_snapshot(snapshot)
        if data.kind=="monthly":
            start,end=date.fromisoformat(state["period"]["start"]),date.fromisoformat(state["period"]["end"])
            if start.day!=1 or start.year!=end.year or start.month!=end.month or end.day!=calendar.monthrange(end.year,end.month)[1]:raise HTTPException(422,"Monthly reports require a saved snapshot covering one complete calendar month")
            if end>=closed_today(business):raise HTTPException(422,"Monthly reports must cover a closed calendar month")
        meta|={"business_name":state["business"]["name"],"currency":state["business"]["currency"],"timezone":state["business"]["timezone"],"reporting_period":state["period"],"captured_at":state["captured_at"],"data_freshness":state["data_updated_at"],"result_kind":"calculated_historical" if data.kind!="inventory_risk" else "calculated_inventory_risk","demo_records_present":state["demo_records"]>0}
        sources.append({"type":"twin_snapshot","id":str(snapshot.id),"name":snapshot.name,"sha256":snapshot.content_hash,"implementation_version":snapshot.implementation_version,"source_versions":state["source_versions"]})
        assumptions.extend(state["assumptions"])
        if data.kind in {"monthly","revenue_expenses"}:
            sections.append(section("Financial results",["metric","value","definition"],[[key,value,state["metric_provenance"][key]["definition"]] for key,value in state["metrics"].items()],"Incomplete or undefined values remain null. Expenses are recorded paid expenses; operating profit requires exact-period coverage."))
            sections.append(section("Operating context",["metric","value"],[["active_customers",state["customers"]["active_in_period"]],["retained_customers",state["customers"]["retained"]],["eligible_retention_cohort",state["customers"]["eligible_retention"]],["retention_pct",state["customers"]["retention_pct"]],["inventory_value_at_capture",state["inventory_value"]],["expense_coverage_confirmed",state["expenses_complete"]],["missing_cost_lines",state["missing_cost_lines"]]]))
            if state["metrics"]["operating_profit"] is None:limits.append("Operating profit is incomplete: historical line costs or exact-period expense coverage are missing. This is not net profit.")
        else:
            if state["inventory"] is None:raise HTTPException(422,"Inventory risk requires an inventory-enabled baseline")
            orders={row["id"] for row in snapshot.payload["inputs"]["sources"]["orders"] if row["status"]=="paid" and state["period"]["start"]<=row["ordered_on"]<=state["period"]["end"]}
            units={}
            for row in snapshot.payload["inputs"]["sources"]["order_items"]:
                if row["order_id"] in orders:units[row["product_id"]]=units.get(row["product_id"],ZERO)+Decimal(row["quantity"])
            rows=[]
            for item in state["inventory"]:
                rate=units.get(item["product_id"],ZERO)/state["period"]["days"]
                stock=Decimal(item["quantity"]);needed=rate*data.lead_days+data.safety_units
                gap=max(ZERO,needed-stock-data.incoming_units)
                rows.append([item["sku"],stock,rate.quantize(Decimal("0.001")),data.lead_days,data.incoming_units,data.safety_units,needed.quantize(Decimal("0.001")),gap.quantize(Decimal("0.001")),"shortfall" if gap else "no_calculated_shortfall"])
            sections.append(section("Inventory risk at capture",["sku","stock","daily_recorded_units","lead_days","incoming_assumption","safety_assumption","required_units","shortfall","rule"],rows,"Required units = exact mean recorded reporting-period units per day × lead time + safety. Shortfall = max(0, required − captured stock − incoming)."))
            assumptions.append(f"Lead time {data.lead_days} days; incoming {data.incoming_units} and safety {data.safety_units} units apply independently to each SKU. Stock is current at snapshot capture.")
            limits.append("A deterministic rule using recorded demand, not an ML probability or guaranteed stockout date. Missing imports, lost sales and supply timing are not modelled.")
    elif data.model_run_id:
        access(db,user,business_id,"ml:read")
        task="sales" if data.kind=="sales_forecast" else "churn"
        run=db.scalar(select(ModelRun).where(ModelRun.business_id==business_id,ModelRun.id==data.model_run_id,ModelRun.task==task))
        if run is None:raise HTTPException(404,"Model of the requested task not found in this business")
        if run.implementation_version!="1" or fingerprint(run.dataset)!=run.dataset_hash:raise HTTPException(409,"Model integrity/version check failed")
        meta|={"result_kind":"forecast_estimates" if task=="sales" else "inactivity_estimates","reporting_period":{"start":run.config.get("start",run.dataset.get("start")),"end":run.config["end"]},"data_freshness":run.config["end"],"captured_at":run.created_at.isoformat(),"currency":run.config["currency"],"timezone":run.config["timezone"],"demo_records_present":run.data_scope=="demo","model":{"id":str(run.id),"algorithm":run.algorithm,"data_scope":run.data_scope,"implementation_version":run.implementation_version,"dataset_hash":run.dataset_hash}}
        sources.append({"type":"model_run","id":str(run.id),"sha256":run.dataset_hash,"algorithm":run.algorithm,"implementation_version":run.implementation_version,"config":run.config,"result_hash":fingerprint(run.result)})
        limits.extend(run.result["limitations"])
        assumptions.append("Saved-artifact estimates at their original cutoff; generating this report does not retrain, activate or refresh the model.")
        if task=="sales":
            if run.config["aggregation"]=="weekly" and data.horizon>12:raise HTTPException(422,"Weekly forecast reports support at most twelve periods")
            points=forecast_rows(run.dataset,run.result,run.artifact,data.horizon)
            meta["forecast_period"]={"start":points[0]["date"],"end":points[-1]["date"],"aggregation":run.config["aggregation"]}
            sections.append(section("Forecast estimates",["date","prediction","lower_diagnostic_band","upper_diagnostic_band"],[[row["date"],row["prediction"],row["lower"],row["upper"]] for row in points],"Estimates, not historical sales. Diagnostic residual bands are not guaranteed prediction intervals."))
            rows=[]
            for algorithm,result in run.result["candidates"].items():
                for split,values in result.items():
                    if isinstance(values,dict):rows.append([algorithm,split,values.get("mae"),values.get("rmse"),values.get("wape_pct"),values.get("observations")])
            sections.append(section("Saved evaluation",["algorithm","partition","MAE","RMSE","WAPE_pct","observations"],rows))
        else:
            predictions=run.result["predictions"]
            if len(predictions)>1000:raise HTTPException(422,"Inactivity reports support at most 1000 saved estimates")
            sections.append(section("Saved customer inactivity estimates",["customer_reference","customer_id","estimated_probability"],[[row["external_id"],row["customer_id"],row["estimated_inactivity_probability"]] for row in predictions],run.result["definition"]+" These are uncalibrated probabilities and not confirmed customer losses."))
            sections.append(section("Evaluation versus baseline",["metric","model","baseline"],[[key,value,run.result["baseline"].get(key)] for key,value in run.result["evaluation"].items()]))
    elif data.scenario_run_ids:
        access(db,user,business_id,"simulation:read")
        left,right=[scenario_detail(db,owned_scenario(db,business_id,key)) for key in data.scenario_run_ids]
        if left["baseline_snapshot_id"]!=right["baseline_snapshot_id"]:raise HTTPException(422,"Scenario reports require the same baseline snapshot")
        meta|={"result_kind":"hypothetical_simulation","reporting_period":left["result"]["baseline_period"],"captured_at":left["result"]["baseline_captured_at"],"data_freshness":left["result"]["baseline_captured_at"],"currency":left["result"]["currency"],"timezone":left["result"]["timezone"],"demo_records_present":left["result"]["demo_records_present"]}
        for item in [left,right]:sources.append({"type":"simulation_run","id":item["id"],"name":item["name"],"sha256":item["content_hash"],"baseline_snapshot_id":item["baseline_snapshot_id"],"baseline_hash":item["baseline_hash"],"parameters":item["parameters"]})
        rows=[]
        for key,a in left["result"]["metrics"].items():
            b=right["result"]["metrics"][key]
            delta=Decimal(str(b))-Decimal(str(a)) if a is not None and b is not None else None
            rows.append([key,a,b,delta])
        sections.append(section("Hypothetical scenario comparison",["metric",left["name"],right["name"],"right_minus_left"],rows,"Both scenarios use one saved baseline. Simulated results are not actual financial performance."))
        sections.append(section("Replenishment cash assumptions",["scenario","cash_outlay"],[[item["name"],item["result"]["replenishment_cash_outlay"]] for item in [left,right]],"Inventory purchase cash remains separate from operating expenses and COGS."))
        assumptions.extend(left["result"]["methodology"])
        limits.extend(left["result"]["warnings"]+right["result"]["warnings"])
        limits.append("Scenario differences compare explicit assumptions, not guaranteed future outcomes or established causal effects.")
    else:
        access(db,user,business_id,"analyst:read")
        investigation=owned_investigation(db,business_id,user,data.investigation_id)
        if not investigation.response:raise HTTPException(422,"Only investigations with saved findings can be reported")
        answer=investigation.response
        identity=investigation.inputs["business"]
        demo=any(row.get("is_demo",False) for records in investigation.inputs["sources"].values() for row in records)
        meta|={"business_name":identity["name"],"currency":identity["currency"],"timezone":identity["timezone"],"result_kind":"evidence_backed_investigation","reporting_period":{"start":investigation.parameters["start"],"end":investigation.parameters["end"]},"captured_at":investigation.inputs["captured_at"],"data_freshness":answer.get("data_updated_at"),"demo_records_present":demo,"chat_model":investigation.chat_model}
        sources.append({"type":"analyst_investigation","id":str(investigation.id),"sha256":investigation.input_hash,"evidence_hash":answer["evidence_hash"],"implementation_version":investigation.implementation_version,"question":investigation.question})
        sections.append(section("Investigation findings",["evidence","kind","finding"],[[row["evidence_id"],row["kind"],row["text"]] for row in answer["findings"]],answer["answer"] if answer["insufficient"] else "Model-selected validated evidence with the financial comparison bridge retained. References require human relevance review."))
        sections.append(section("Review recommendations",["action"],[[row] for row in answer["recommendations"]]))
        sections.append(section("Tool execution trail",["evidence","tool","status","duration_ms","error"],[[row["id"],row["tool"],row["status"],row["duration_ms"],row.get("error")] for row in investigation.executions]))
        limits.extend(answer["limitations"])
    limits.extend(["Reports freeze the saved source values and do not update automatically after later operational corrections.","Null values mean incomplete or undefined, not zero. Currency conversion and partial-refund modelling are not performed."])
    return json_ready({"metadata":meta,"sections":sections,"sources":sources,"assumptions":list(dict.fromkeys(assumptions)),"limitations":list(dict.fromkeys(limits))}),member.role


def owned(db,business_id,user,report_id):
    _,member=access(db,user,business_id,"reports:read")
    row=db.scalar(select(GeneratedReport).where(GeneratedReport.business_id==business_id,GeneratedReport.user_id==user.id,GeneratedReport.id==report_id))
    if row is None:raise HTTPException(404,"Report not found")
    if row.captured_role in {"owner","administrator"} and member.role not in {"owner","administrator"}:raise HTTPException(403,"This report was captured with administrator privileges")
    if row.implementation_version!=VERSION or fingerprint(row.payload)!=row.content_hash:raise HTTPException(409,"Report integrity/version check failed")
    for source in row.payload["sources"]:
        if source["type"]=="analyst_investigation":
            from uuid import UUID
            owned_investigation(db,business_id,user,UUID(source["id"]))
    return row


def export_rows(payload):
    rows=[["NEXORA TWIN business report"]]
    for key,value in payload["metadata"].items():rows.append([key,json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else value])
    for part in payload["sections"]:
        rows.extend([[],[part["title"]],[part["note"]],part["columns"]]);rows.extend(part["rows"])
    for title in ["sources","assumptions","limitations"]:
        rows.extend([[],[title]])
        for value in payload[title]:rows.append([json.dumps(value,ensure_ascii=False) if isinstance(value,dict) else value])
    return rows


def export_lines(payload):
    lines=["NEXORA TWIN | "+payload["metadata"]["name"],"Result type: "+payload["metadata"]["result_kind"],""]
    for key,value in payload["metadata"].items():lines.append(key+": "+(json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else str(value)))
    for part in payload["sections"]:
        lines.extend(["",part["title"],part["note"]," | ".join(part["columns"])])
        for row in part["rows"]:lines.append(" | ".join("Incomplete / undefined" if cell is None else str(cell) for cell in row))
    for title in ["sources","assumptions","limitations"]:
        lines.extend(["",title.upper()])
        for value in payload[title]:lines.append(json.dumps(value,ensure_ascii=False) if isinstance(value,dict) else str(value))
    lines.extend(["","PDF uses standard portable fonts; unsupported characters appear as Unicode escapes. CSV retains full Unicode text."])
    return lines
