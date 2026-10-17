"""Synthetic in-process API workload; never contacts external providers."""
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
tmp = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = 'sqlite:///' + tmp.name + '/benchmark.db'
os.environ['DEMO_MODE'] = 'true'
os.environ['APP_ENV'] = 'local'
os.environ['LOCAL_JWT_SECRET'] = 'benchmark-only-key-not-for-real-users'
from fastapi.testclient import TestClient
from app.main import app
from app.seed.seed_data import run
from app.database import SessionLocal
from app.models.catalog import SupplierInventory

run()
# Rate limiting is measured separately; remove its 200/min ceiling for capacity experiment.
app.state.limiter.enabled = False
client = TestClient(app)

def login(email):
    r = client.post('/api/auth/login', json={'email': email, 'password': 'demo1234'})
    r.raise_for_status()
    return {'Authorization': 'Bearer ' + r.json()['access_token']}

merchant = login('merchant1@example.com')
suppliers = {name: login(email) for name, email in [('Anand Wholesale Grains','anand@example.com'), ('Lakshmi Traders','lakshmi@example.com'), ('Sri Balaji Provisions','balaji@example.com'), ('NewCo Supplies (joined this month)','newco@example.com')]}
rice = next(p['id'] for p in client.get('/api/products').json() if p['name'] == 'Rice')
with SessionLocal() as db:
    db.query(SupplierInventory).filter(SupplierInventory.stock_qty_base_unit > 0).update({'stock_qty_base_unit': 100000})
    db.commit()

def summary(samples):
    data = sorted(samples)
    return {'p50_ms': round(statistics.median(data), 3), 'p95_ms': round(data[int(.95*(len(data)-1))], 3), 'p99_ms': round(data[int(.99*(len(data)-1))], 3)}

recovery = []
results = []
started = time.perf_counter()
for _ in range(30):
    r = client.post('/api/orders', headers=merchant, json={'items':[{'product_id':rice,'requested_qty_base_unit':100}], 'min_reliability':0.0,'price_tolerance_pct':20,'budget_cap':6000})
    r.raise_for_status(); oid = r.json()['id']
    r = client.post(f'/api/orders/{oid}/plan', headers=merchant); r.raise_for_status()
    plan = next(p for p in r.json()['plans'] if p['objective_profile']=='cheapest')
    client.post(f'/api/orders/{oid}/select-plan',headers=merchant,json={'plan_id':plan['id']}).raise_for_status()
    a = plan['allocations'][0]
    begin = time.perf_counter()
    r = client.post(f"/api/allocations/{a['id']}/confirm",headers=suppliers[a['supplier_name']],json={'confirmed_qty_base_unit':40,'ready_by':'2026-11-01T10:00:00Z'})
    recovery.append((time.perf_counter()-begin)*1000);r.raise_for_status()
    evidence = client.get(f'/api/orders/{oid}/evidence',headers=merchant).json()
    row = evidence['items'][0]
    assert row['confirmed'] == 40 and row['proposed'] == 60 and row['uncovered'] == 0
    assert evidence['budget_respected'] and evidence['supplier_limit_respected']
    results.append({'baseline_coverage_kg':40,'recovered_plan_coverage_kg':100,'delivered_kg':row['delivered'],'cost_inr':evidence['landed_cost']})
workflow_duration = time.perf_counter()-started

def read(_):
    start=time.perf_counter()
    r=client.get(f'/api/orders/{oid}/evidence',headers=merchant)
    return ((time.perf_counter()-start)*1000,r.status_code)
start=time.perf_counter()
with ThreadPoolExecutor(max_workers=4) as pool:
    reads=list(pool.map(read,range(200)))
duration=time.perf_counter()-start
out={'runtime':platform.python_version(),'platform':platform.platform(),'logical_cpus':os.cpu_count(),'method':'FastAPI TestClient in-process, SQLite, 4 read threads; rate limiter disabled only in benchmark; not a network or production benchmark','dataset':'30 new one-SKU orders, 9 catalog products, 4 suppliers, 20 seeded offers; stock raised to 100000 synthetic units','recovery_runs':30,'workflow_duration_s':round(workflow_duration,3),'recovery_latency':summary(recovery),'baseline':results[0],'api_reads':200,'concurrency':4,'read_duration_s':round(duration,3),'throughput_rps':round(200/duration,2),'read_latency':summary([x[0] for x in reads]),'errors':sum(x[1]!=200 for x in reads),'all_recovery_cases_passed':True}
output=Path(sys.argv[1] if len(sys.argv)>1 else 'benchmark-results.json');output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
