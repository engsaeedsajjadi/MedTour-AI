"""Section 31 reporting: tenant/role isolation, totals and CSV."""
import csv,io
from app.models import Case

def test_aggregate_reports_are_private_and_consistent(seeded):
    (client,auth,tids,Session),a,patient,case=seeded
    b=auth("b")
    operator=auth("a","operator@example.test")
    url="/api/v1/analytics/overview"
    assert client.get(url).status_code==401
    assert client.get(url,headers=operator).status_code==403
    mine=client.get(url,headers=a)
    assert mine.status_code==200,mine.text
    data=mine.json()
    assert data["patients"]==1 and data["cases"]==1
    assert data["case_status_counts"]["new"]==1
    assert data["includes_phi"] is False
    assert patient["id"] not in str(data)
    assert case["id"] not in str(data)
    other=client.get(url,headers=b)
    assert other.status_code==200
    assert other.json()["patients"]==0 and other.json()["cases"]==0
    csv_result=client.get(url+".csv",headers=a)
    assert csv_result.status_code==200
    assert csv_result.headers["cache-control"]=="no-store, private"
    rows=list(csv.reader(io.StringIO(csv_result.text)))
    assert ["cases","total","1"] in rows
    assert patient["id"] not in csv_result.text
    assert case["id"] not in csv_result.text
    assert client.get(url+".csv",headers=operator).status_code==403
    assert client.get(url+".csv",headers=b).status_code==200
