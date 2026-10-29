"""Real Next.js -> API -> PostgreSQL graph/report acceptance; owned cleanup."""
import io
import os
import json
import secrets
from datetime import datetime,timedelta
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor,Request,build_opener
from uuid import UUID,uuid4
from zoneinfo import ZoneInfo
from pypdf import PdfReader
from sqlalchemy import delete,select
from sqlalchemy.orm import Session
from app.db.session import get_engine
from app.models import AuditLog,Business,Membership,User

BASE=os.getenv("NEXORA_BASE_URL", "http://localhost:3000").rstrip("/")


def main():
    prefix="nexora-insights-http-"+uuid4().hex
    client=build_opener(HTTPCookieProcessor(CookieJar()));users=[];businesses=[];csrf=None
    def call(path,method="GET",body=None,expected=200,binary=False):
        headers={"Origin":BASE}
        if csrf:headers["X-CSRF-Token"]=csrf
        data=json.dumps(body).encode() if body is not None else None
        if data is not None:headers["Content-Type"]="application/json"
        try:response=client.open(Request(BASE+"/api/backend/"+path,method=method,headers=headers,data=data),timeout=65)
        except HTTPError as error:response=error
        with response:
            content=response.read()
            assert response.code==expected,f"{method} {path}: {response.code}: {content[:350]!r}"
            return (content,response.headers) if binary else json.loads(content) if content else None
    try:
        identity=call("auth/register","POST",{"name":"Graph/report acceptance","email":prefix+"@example.com","password":secrets.token_urlsafe(32)},201)
        users.append(UUID(identity["user"]["id"]));csrf=identity["csrf_token"]
        for name in ["Graph report HTTP check","Separate graph report HTTP check"]:
            business=call("businesses","POST",{"name":name,"business_type":"retail","country":"IN","currency":"INR","timezone":"Asia/Kolkata"},201)
            businesses.append(UUID(business["id"]))
        path,other=["businesses/"+str(value) for value in businesses]
        today=datetime.now(ZoneInfo("Asia/Kolkata")).date();end=today-timedelta(days=1);start=end-timedelta(days=29)
        period={"start":start.isoformat(),"end":end.isoformat()}
        def add(resource,rows):return call(path+"/"+resource,"POST",{"rows":rows},201)
        add("customers",[{"external_id":"C1","name":"Demonstration customer","is_demo":True}])
        add("suppliers",[{"external_id":"S1","name":"Demonstration supplier","is_demo":True}])
        add("products",[{"sku":"P1","name":"Demonstration product","supplier_external_id":"S1","unit_price":"10","unit_cost":"4","initial_stock":"20","is_demo":True}])
        add("orders",[{"external_id":"O1","ordered_on":end.isoformat(),"customer_external_id":"C1","product_sku":"P1","quantity":"3","unit_price":"10","unit_cost":"4","discount_amount":"2","is_demo":True}])
        add("inventory",[{"external_id":"W1","product_sku":"P1","occurred_on":today.isoformat(),"quantity_delta":"-19","reason":"waste","is_demo":True}])
        add("expenses",[{"external_id":"E1","incurred_on":end.isoformat(),"category":"rent","amount":"5.50","is_demo":True}])
        call(path+"/expense-coverage","PUT",{"start_date":period["start"],"end_date":period["end"],"complete":True})
        current=path+f"/twin/current?start={period['start']}&end={period['end']}"
        before=call(current)["state"]["source_versions"]
        graph=call(path+"/knowledge-graph/refresh","POST")
        assert graph["node_count"]>=8 and graph["demo_nodes"]>0
        assert call(path+"/knowledge-graph/refresh","POST")["unchanged"] is True
        product=call(path+"/knowledge-graph/nodes?kind=product&search=P1")["items"][0]
        route=path+f"/knowledge-graph/nodes/{product['id']}?build_id={graph['build']['id']}"
        neighbors=call(route)
        assert {"supplies","contains","has_balance","has_movement"}<={edge["relationship"] for edge in neighbors["edges"]}
        assert call(route+"&relationship=has_balance")["total_connections"]==1
        graph_csv,headers=call(path+"/knowledge-graph/export",binary=True)
        assert "P1" in graph_csv.decode("utf-8-sig") and "supplies" in graph_csv.decode("utf-8-sig") and "attachment" in headers["Content-Disposition"]
        snapshot=call(path+"/twin/snapshots","POST",period|{"name":"Graph/report baseline"},201)
        saved=call(path+"/reports","POST",{"name":"Demonstration financial report","kind":"revenue_expenses","snapshot_id":snapshot["id"]},201)
        report_route=path+"/reports/"+saved["id"]
        values={row[0]:row[1] for row in saved["payload"]["sections"][0]["rows"]}
        assert values["revenue"]=="28.00" and values["operating_profit"]=="10.50"
        pdf,headers=call(report_route+"/export/pdf",binary=True)
        reader=PdfReader(io.BytesIO(pdf),strict=True)
        text="\n".join(page.extract_text() for page in reader.pages)
        assert "28.00" in text and "10.50" in text and "NEXORA TWIN" in text
        assert "application/pdf" in headers["Content-Type"] and "attachment" in headers["Content-Disposition"]
        csv,_=call(report_route+"/export/csv",binary=True)
        assert snapshot["content_hash"] in csv.decode("utf-8-sig")
        risk=call(path+"/reports","POST",{"name":"Stock rule report","kind":"inventory_risk","snapshot_id":snapshot["id"],"lead_days":14},201)
        assert risk["payload"]["sections"][0]["rows"][0][7]=="0.400"
        month_end=today.replace(day=1)-timedelta(days=1);month_start=month_end.replace(day=1)
        monthly_source=call(path+"/twin/snapshots","POST",{"name":"Closed calendar month","start":month_start.isoformat(),"end":month_end.isoformat()},201)
        monthly=call(path+"/reports","POST",{"name":"Monthly report","kind":"monthly","snapshot_id":monthly_source["id"]},201)
        assert monthly["payload"]["metadata"]["reporting_period"]["start"]==month_start.isoformat()
        call(other+f"/knowledge-graph?build_id={graph['build']['id']}",expected=404)
        call(other+"/reports/"+saved["id"],expected=404)
        call(other+"/reports","POST",{"name":"Foreign source","kind":"revenue_expenses","snapshot_id":snapshot["id"]},404)
        assert call(current)["state"]["source_versions"]==before
        record=call(path+"/orders")["items"][0]
        call(path+"/orders/"+record["id"],"PATCH",{"status":"refunded","reason":"After frozen report"})
        assert call(report_route)==saved
        assert call(route)["node"]["source"]["values"]["sku"]=="P1"
        result={"status":"passed","checks":["real frontend proxy","source-backed graph","idempotent graph refresh","bounded relationship filter","graph CSV","financial report totals","binary PDF preserved through proxy","strict PDF parsing","report CSV source hashes","inventory risk arithmetic","closed-month report","cross-business denial","no operational changes","frozen report after refund"],"graph_nodes":graph["node_count"],"graph_edges":graph["edge_count"],"pdf_pages":len(reader.pages),"pdf_bytes":len(pdf)}
        folder=Path(__file__).resolve().parents[1]/".local";folder.mkdir(exist_ok=True)
        (folder/"phase9-http-report.json").write_text(json.dumps(result,indent=2))
        call("auth/logout","POST",expected=204)
        print("Graph/report HTTP acceptance passed, including binary PDF parsing through Next.js.",flush=True)
    finally:
        with Session(get_engine()) as db:
            accounts=db.scalars(select(User).where(User.id.in_(users))).all()
            assert all(user.email==prefix+"@example.com" for user in accounts)
            owned=db.scalars(select(Membership.business_id).where(Membership.business_id.in_(businesses),Membership.user_id.in_(users),Membership.role=="owner")).all()
            assert set(owned)==set(businesses),"Could not verify cleanup ownership"
            db.execute(delete(AuditLog).where(AuditLog.user_id.in_(users)))
            db.execute(delete(Business).where(Business.id.in_(businesses)))
            db.execute(delete(User).where(User.id.in_(users)));db.commit()
        print("Removed only the acceptance account and its temporary businesses.",flush=True)


if __name__=="__main__":main()
