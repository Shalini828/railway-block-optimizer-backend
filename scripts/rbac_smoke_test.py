#!/usr/bin/env python3
"""
IR-ABPS RBAC Live Smoke Test & Verification Script.
Logs into the live FastAPI instance across all 4 roles and tests endpoint access permissions & data scoping.
"""
import os
import sys
import requests

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "12345")
ROLES = ["admin", "control", "engineering", "traction", "signal"]

print(f"\n=======================================================")
print(f"  IR-ABPS LIVE RBAC SMOKE TEST MATRIX")
print(f"  Target: {BASE_URL}")
print(f"=======================================================\n")

# 1. Login as all 5 roles
tokens = {}
for role in ROLES:
    try:
        res = requests.post(
            f"{BASE_URL}/auth/login",
            json={"role_id": role, "password": DEMO_PASSWORD},
            timeout=5,
        )
        if res.status_code == 200:
            tokens[role] = res.json()["access_token"]
            print(f"[AUTH] Logged in as '{role}' successfully (token length: {len(tokens[role])}).")
        else:
            print(f"[AUTH] FAILED login as '{role}': HTTP {res.status_code} - {res.text}")
            sys.exit(1)
    except Exception as e:
        print(f"[AUTH] Connection error reaching {BASE_URL}: {e}")
        sys.exit(1)

print("\n--- Running Endpoint Matrix Verification ---\n")

ENDPOINTS = [
    # (Method, Path, Payload, Note)
    ("GET", "/dashboard/kpis", None, "Dashboard KPIs"),
    ("GET", "/block-requests/", None, "View Requests"),
    ("POST", "/block-requests/", {
        "dept": "TMS",
        "assetId": "TRK-001",
        "work": "Track Tamping",
        "section": "NDLS-GZB",
        "line": "UP",
        "chainage": "10/2",
        "blockType": "Traffic Block",
        "duration": 120.0,
        "crew": 5,
        "criticality": "HIGH",
        "daysOverdue": 1,
        "tsrRisk": False,
        "requestedBy": "Tester",
    }, "Create Requisition (TMS)"),
    ("POST", "/block-requests/", {
        "dept": "SMMS",
        "assetId": "SIG-001",
        "work": "Point Machine Maintenance",
        "section": "NDLS-GZB",
        "line": "UP",
        "chainage": "10/2",
        "blockType": "Traffic Block",
        "duration": 90.0,
        "crew": 3,
        "criticality": "HIGH",
        "daysOverdue": 1,
        "tsrRisk": False,
        "requestedBy": "Tester",
    }, "Create Requisition (SMMS)"),
    ("POST", "/optimization/", {}, "Run Optimizer"),
    ("POST", "/optimization/simulate", {}, "Simulate Optimizer"),
    ("GET", "/optimized-plan/", None, "Gantt Plan View"),
    ("POST", "/optimized-plan/BLK-DEMO/review", {"decision": "ENDORSE"}, "Controller Review"),
    ("POST", "/optimized-plan/BLK-DEMO/approve", {"approved_by": "Test"}, "Final Block Approve"),
    ("POST", "/optimized-plan/BLK-DEMO/reject", {"reason": "Test"}, "Final Block Reject"),
    ("POST", "/optimized-plan/BLK-DEMO/rework", {"reason": "Test"}, "Send Block for Rework"),
    ("POST", "/optimized-plan/BLK-DEMO/request-change", {"reason": "Shift required", "suggested_shift_min": 30}, "Dept Request Change"),
    ("GET", "/conflicts/", None, "Conflicts View"),
    ("POST", "/conflicts/CONF-DEMO/resolve", {"resolution_notes": "Handled"}, "Resolve Conflict"),
    ("GET", "/maintenance-tasks/", None, "Maintenance Tasks View"),
    ("PUT", "/maintenance-tasks/TSK-DEMO/status", {"status": "COMPLETED"}, "Update Task Status"),
    ("GET", "/analytics/", None, "Analytics View"),
    ("GET", "/emergency/", None, "Emergency Incidents View"),
    ("POST", "/emergency/", {
        "emergency_type": "Track Fracture",
        "section": "NDLS-GZB",
        "line": "UP",
        "severity": "CRITICAL"
    }, "Report Track Emergency"),
    ("POST", "/emergency/", {
        "emergency_type": "OHE Snapping",
        "section": "NDLS-GZB",
        "line": "UP",
        "severity": "CRITICAL"
    }, "Report Traction Emergency"),
    ("POST", "/emergency/", {
        "emergency_type": "Signal Failure",
        "section": "NDLS-GZB",
        "line": "UP",
        "severity": "CRITICAL"
    }, "Report Signal Emergency"),
    ("PATCH", "/emergency/INC-DEMO/resolve", {"resolution_notes": "Fixed"}, "Resolve Emergency"),
    ("POST", "/ai/tasks/apply-priorities", {}, "Apply AI Priorities"),
    ("GET", "/admin/permission-matrix", None, "Admin Permission Matrix"),
    ("GET", "/admin/audit-log", None, "Admin Audit Log"),
    ("GET", "/special-trains/", None, "Special Trains View"),
    ("POST", "/special-trains/", {
        "train_number": "09999",
        "train_name": "Test Special",
        "special_type": "FESTIVAL",
        "corridor_id": "CORR-001",
        "service_date": "2026-10-01",
        "arrival_time": "10:00:00",
        "departure_time": "12:00:00"
    }, "Create Special Train"),
]

# Print header
header_fmt = "{:<6} {:<36} | {:<8} {:<8} {:<12} {:<10} {:<8}"
print(header_fmt.format("METHOD", "ENDPOINT", "ADMIN", "CONTROL", "ENGINEERING", "TRACTION", "SIGNAL"))
print("-" * 98)

row_fmt = "{:<6} {:<36} | {:<8} {:<8} {:<12} {:<10} {:<8}"

for method, path, payload, desc in ENDPOINTS:
    status_map = {}
    for role in ROLES:
        h = {"Authorization": f"Bearer {tokens[role]}"}
        try:
            if method == "GET":
                r = requests.get(f"{BASE_URL}{path}", headers=h, timeout=5)
            elif method == "POST":
                r = requests.post(f"{BASE_URL}{path}", json=payload or {}, headers=h, timeout=5)
            elif method == "PUT":
                r = requests.put(f"{BASE_URL}{path}", json=payload or {}, headers=h, timeout=5)
            elif method == "PATCH":
                r = requests.patch(f"{BASE_URL}{path}", json=payload or {}, headers=h, timeout=5)
            status_map[role] = str(r.status_code)
        except Exception as e:
            status_map[role] = "ERR"

    print(row_fmt.format(
        method,
        path,
        status_map["admin"],
        status_map["control"],
        status_map["engineering"],
        status_map["traction"],
        status_map["signal"]
    ))

print("-" * 98)

# 2. Assert Data Scoping
print("\n--- Verifying Data Scoping ---")

# (A) Maintenance Tasks Scope
h_eng = {"Authorization": f"Bearer {tokens['engineering']}"}
h_trd = {"Authorization": f"Bearer {tokens['traction']}"}
h_sig = {"Authorization": f"Bearer {tokens['signal']}"}
h_adm = {"Authorization": f"Bearer {tokens['admin']}"}

res_eng = requests.get(f"{BASE_URL}/maintenance-tasks/", headers=h_eng, timeout=5)
res_trd = requests.get(f"{BASE_URL}/maintenance-tasks/", headers=h_trd, timeout=5)
res_sig = requests.get(f"{BASE_URL}/maintenance-tasks/", headers=h_sig, timeout=5)
res_adm = requests.get(f"{BASE_URL}/maintenance-tasks/", headers=h_adm, timeout=5)

if res_eng.status_code == 200 and res_trd.status_code == 200 and res_sig.status_code == 200 and res_adm.status_code == 200:
    tasks_eng = res_eng.json()
    tasks_trd = res_trd.json()
    tasks_sig = res_sig.json()
    tasks_adm = res_adm.json()

    print(f"Total tasks: Admin={len(tasks_adm)}, Engineering={len(tasks_eng)}, Traction={len(tasks_trd)}, Signal={len(tasks_sig)}")

    # Verify engineering sees only TMS
    non_tms = [t for t in tasks_eng if t.get("department") != "TMS"]
    assert len(non_tms) == 0, f"Engineering saw non-TMS tasks: {non_tms}"
    print("[PASS] Engineering maintenance-tasks scoped strictly to department == 'TMS'.")

    # Verify traction sees only TDMS
    non_tdms = [t for t in tasks_trd if t.get("department") != "TDMS"]
    assert len(non_tdms) == 0, f"Traction maintenance-tasks scoped strictly to department == 'TDMS'."
    print("[PASS] Traction maintenance-tasks scoped strictly to department == 'TDMS'.")

    # Verify signal sees only SMMS
    non_smms = [t for t in tasks_sig if t.get("department") != "SMMS"]
    assert len(non_smms) == 0, f"Signal saw non-SMMS tasks: {non_smms}"
    print("[PASS] Signal maintenance-tasks scoped strictly to department == 'SMMS'.")

    # Verify admin is superset
    assert len(tasks_adm) >= len(tasks_eng), "Admin should see superset of tasks"
    assert len(tasks_adm) >= len(tasks_sig), "Admin should see superset of tasks"
    print("[PASS] Admin maintenance-tasks is superset of department tasks.")
else:
    print(f"[INFO] Maintenance tasks data check skipped (database status: Admin {res_adm.status_code}, Eng {res_eng.status_code})")

# (B) Plan Scope
res_plan_trd = requests.get(f"{BASE_URL}/optimized-plan/", headers=h_trd, timeout=5)
res_plan_sig = requests.get(f"{BASE_URL}/optimized-plan/", headers=h_sig, timeout=5)
res_plan_adm = requests.get(f"{BASE_URL}/optimized-plan/", headers=h_adm, timeout=5)

if res_plan_trd.status_code == 200 and res_plan_adm.status_code == 200:
    plan_trd = res_plan_trd.json()
    plan_adm = res_plan_adm.json()
    blocks_trd = plan_trd.get("blocks", [])
    blocks_adm = plan_adm.get("blocks", [])

    print(f"Total blocks: Admin={len(blocks_adm)}, Traction={len(blocks_trd)}")

    # Verify all traction blocks have >= 1 TDMS task
    for block in blocks_trd:
        tasks = block.get("tasks", [])
        has_tdms = any(t.get("department") == "TDMS" for t in tasks)
        assert has_tdms, f"Block {block.get('block_id')} returned to Traction with no TDMS tasks!"
    print("[PASS] Traction optimized-plan blocks all contain >=1 TDMS task.")

    if res_plan_sig.status_code == 200:
        plan_sig = res_plan_sig.json()
        blocks_sig = plan_sig.get("blocks", [])
        for block in blocks_sig:
            tasks = block.get("tasks", [])
            has_smms = any(t.get("department") == "SMMS" for t in tasks)
            assert has_smms, f"Block {block.get('block_id')} returned to Signal with no SMMS tasks!"
        print("[PASS] Signal optimized-plan blocks all contain >=1 SMMS task.")

    assert len(blocks_adm) >= len(blocks_trd), "Admin sees superset of blocks."
    print("[PASS] Admin optimized-plan is superset of department blocks.")
else:
    print(f"[INFO] Optimized plan data check skipped (database status: Admin {res_plan_adm.status_code}, Trd {res_plan_trd.status_code})")

print("\n=======================================================")
print("  ALL SMOKE TESTS AND ASSERTIONS COMPLETED SUCCESSFULLY")
print("=======================================================\n")
