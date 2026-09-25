import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure backend directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app
from auth.security import create_access_token
from auth.permissions import ROLE_TABLE

# Use raise_server_exceptions=False so that DB offline errors (500) do not mask RBAC status codes
client = TestClient(app, raise_server_exceptions=False)

# Helper to get auth header
def get_auth_header(role_id: str) -> dict:
    token = create_access_token(role_id)
    return {"Authorization": f"Bearer {token}"}

# 1. Test token creation, tampering, and expiration
def test_token_validation():
    # Valid token
    admin_header = get_auth_header("admin")
    res = client.get("/auth/me", headers=admin_header)
    assert res.status_code == 200
    assert res.json()["user"]["role_id"] == "admin"

    # Tampered token
    tampered_header = {"Authorization": admin_header["Authorization"] + "tampered"}
    res = client.get("/auth/me", headers=tampered_header)
    assert res.status_code == 401

    # Malformed header
    res = client.get("/auth/me", headers={"Authorization": "NotBearer xyz"})
    assert res.status_code == 401

    # Expired token
    expired_token = create_access_token("admin", custom_ttl_minutes=-10)
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code == 401


# 2. Test that unauthenticated calls to all protected endpoints return 401
def test_unauthenticated_access_returns_401():
    PUBLIC_ROUTES = {
        ("/", "get"),
        ("/health", "get"),
        ("/ai/health", "get"),
        ("/auth/login", "post"),
        ("/openapi.json", "get"),
        ("/docs", "get"),
        ("/docs/oauth2-redirect", "get"),
        ("/redoc", "get"),
    }

    openapi_paths = app.openapi().get("paths", {})
    tested = 0
    for path, methods in openapi_paths.items():
        for method in methods.keys():
            if method in ("options", "head"):
                continue
            if (path, method.lower()) in PUBLIC_ROUTES:
                continue

            # Parameterize path with dummy id if needed
            test_path = (
                path.replace("{block_id}", "BLK-TEST-001")
                .replace("{task_id}", "TSK-TEST-001")
                .replace("{conflict_id}", "CONF-TEST-001")
                .replace("{incident_id}", "INC-TEST-001")
                .replace("{id}", "TEST-001")
                .replace("{asset_id}", "AST-TEST-001")
                .replace("{request_id}", "REQ-TEST-001")
            )

            # Request without token
            m = method.upper()
            if m == "GET":
                res = client.get(test_path)
            elif m == "POST":
                res = client.post(test_path, json={})
            elif m == "PUT":
                res = client.put(test_path, json={})
            elif m == "PATCH":
                res = client.patch(test_path, json={})
            elif m == "DELETE":
                res = client.delete(test_path)
            else:
                continue

            assert res.status_code == 401, f"Expected 401 for unauthenticated {m} {test_path}, got {res.status_code}"
            tested += 1

    assert tested >= 30, f"Expected to test >=30 protected routes, tested {tested}"


# 3. Table-driven role x endpoint 403 matrix assertions
MATRIX_403_CASES = [
    # (method, path, body, role_id, description)
    ("POST", "/optimized-plan/BLK-1/approve", {"approved_by": "Someone"}, "engineering", "Engineering cannot approve"),
    ("POST", "/optimized-plan/BLK-1/approve", {"approved_by": "Someone"}, "traction", "Traction cannot approve"),
    ("POST", "/optimized-plan/BLK-1/approve", {"approved_by": "Someone"}, "signal", "Signal cannot approve"),
    ("POST", "/optimized-plan/BLK-1/approve", {"approved_by": "Someone"}, "control", "Control cannot approve"),
    ("POST", "/optimized-plan/BLK-1/reject", {"reason": "Test"}, "engineering", "Engineering cannot reject"),
    ("POST", "/optimized-plan/BLK-1/reject", {"reason": "Test"}, "traction", "Traction cannot reject"),
    ("POST", "/optimized-plan/BLK-1/reject", {"reason": "Test"}, "signal", "Signal cannot reject"),
    ("POST", "/optimized-plan/BLK-1/reject", {"reason": "Test"}, "control", "Control cannot reject"),
    ("POST", "/optimization/", {}, "engineering", "Engineering cannot run optimizer"),
    ("POST", "/optimization/", {}, "traction", "Traction cannot run optimizer"),
    ("POST", "/optimization/", {}, "signal", "Signal cannot run optimizer"),
    ("POST", "/optimization/recommend-windows", {}, "engineering", "Engineering cannot recommend windows"),
    ("POST", "/optimization/simulate", {}, "traction", "Traction cannot simulate"),
    ("POST", "/optimization/simulate", {}, "signal", "Signal cannot simulate"),
    ("PUT", "/maintenance-tasks/TSK-1/status", {"status": "COMPLETED"}, "control", "Control cannot update task status"),
    ("POST", "/block-requests/", {"work": "Test", "dept": "COA"}, "control", "Control cannot create block request"),
    ("PATCH", "/emergency/INC-1/resolve", {"resolution_notes": "Done"}, "engineering", "Engineering cannot resolve emergency"),
    ("PATCH", "/emergency/INC-1/resolve", {"resolution_notes": "Done"}, "traction", "Traction cannot resolve emergency"),
    ("PATCH", "/emergency/INC-1/resolve", {"resolution_notes": "Done"}, "signal", "Signal cannot resolve emergency"),
    ("POST", "/ai/tasks/apply-priorities", {}, "control", "Control cannot apply AI priorities"),
    ("POST", "/ai/tasks/apply-priorities", {}, "engineering", "Engineering cannot apply AI priorities"),
    ("POST", "/ai/tasks/apply-priorities", {}, "traction", "Traction cannot apply AI priorities"),
    ("POST", "/ai/tasks/apply-priorities", {}, "signal", "Signal cannot apply AI priorities"),
    ("GET", "/admin/permission-matrix", None, "control", "Control cannot view admin permission matrix"),
    ("GET", "/admin/permission-matrix", None, "engineering", "Engineering cannot view admin permission matrix"),
    ("GET", "/admin/permission-matrix", None, "traction", "Traction cannot view admin permission matrix"),
    ("GET", "/admin/permission-matrix", None, "signal", "Signal cannot view admin permission matrix"),
    ("GET", "/admin/audit-log", None, "control", "Control cannot view admin audit log"),
    ("GET", "/admin/audit-log", None, "signal", "Signal cannot view admin audit log"),
    ("POST", "/special-trains/", {}, "engineering", "Engineering cannot create special trains"),
    ("POST", "/special-trains/", {}, "traction", "Traction cannot create special trains"),
    ("POST", "/special-trains/", {}, "signal", "Signal cannot create special trains"),
    ("PUT", "/special-trains/SPL-1", {}, "engineering", "Engineering cannot update special trains"),
    ("PATCH", "/special-trains/SPL-1/active", {"active": False}, "traction", "Traction cannot toggle special trains"),
]

@pytest.mark.parametrize("method,path,body,role_id,desc", MATRIX_403_CASES)
def test_role_forbidden_endpoints(method, path, body, role_id, desc):
    headers = get_auth_header(role_id)
    if method == "GET":
        res = client.get(path, headers=headers)
    elif method == "POST":
        res = client.post(path, json=body or {}, headers=headers)
    elif method == "PUT":
        res = client.put(path, json=body or {}, headers=headers)
    elif method == "PATCH":
        res = client.patch(path, json=body or {}, headers=headers)
    elif method == "DELETE":
        res = client.delete(path, headers=headers)
    else:
        pytest.fail(f"Unsupported method {method}")

    assert res.status_code == 403, f"{desc}: expected 403, got {res.status_code} ({res.text})"
    data = res.json()
    assert data.get("code") == "FORBIDDEN"


# 4. Department mismatch checks
def test_department_mismatch_block_request():
    # Engineering attempting to create request for TDMS
    headers = get_auth_header("engineering")
    payload = {
        "dept": "TDMS",
        "assetId": "TRD-OHE-101",
        "work": "OHE repair",
        "section": "NDLS-GZB",
        "line": "UP",
        "chainage": "12/4",
        "blockType": "Power Block",
        "duration": 120.0,
        "crew": 4,
        "criticality": "HIGH",
        "daysOverdue": 3,
        "tsrRisk": False,
        "requestedBy": "SSE PWay",
    }
    res = client.post("/block-requests/", json=payload, headers=headers)
    assert res.status_code == 403
    assert "You may only raise requisitions for your own department" in res.json().get("detail", "")

    # Signal attempting to create request for TMS -> 403
    sig_headers = get_auth_header("signal")
    payload["dept"] = "TMS"
    res = client.post("/block-requests/", json=payload, headers=sig_headers)
    assert res.status_code == 403
    assert "You may only raise requisitions for your own department" in res.json().get("detail", "")


# 5. Emergency domain group enforcement
def test_emergency_domain_enforcement():
    eng_headers = get_auth_header("engineering")
    # Engineering reporting Traction emergency (OHE Snapping) -> 403
    payload = {
        "emergency_type": "OHE Snapping",
        "section": "NDLS-GZB",
        "line": "UP",
        "severity": "CRITICAL",
    }
    res = client.post("/emergency/", json=payload, headers=eng_headers)
    assert res.status_code == 403
    assert "not authorized to report" in res.json().get("detail", "")

    # Traction reporting Track Fracture -> 403
    trd_headers = get_auth_header("traction")
    payload["emergency_type"] = "Track Fracture"
    res = client.post("/emergency/", json=payload, headers=trd_headers)
    assert res.status_code == 403
    assert "not authorized to report" in res.json().get("detail", "")

    # Signal reporting Track Fracture -> 403
    sig_headers = get_auth_header("signal")
    payload["emergency_type"] = "Track Fracture"
    res = client.post("/emergency/", json=payload, headers=sig_headers)
    assert res.status_code == 403
    assert "not authorized to report" in res.json().get("detail", "")

    # Signal reporting Signal Failure -> passes RBAC check (not 401 or 403)
    payload["emergency_type"] = "Signal Failure"
    res = client.post("/emergency/", json=payload, headers=sig_headers)
    assert res.status_code not in (401, 403)


# 6. Allowed roles get not 401/403
ALLOWED_ROLE_CASES = [
    ("GET", "/dashboard/kpis", "admin"),
    ("GET", "/dashboard/kpis", "control"),
    ("GET", "/dashboard/kpis", "engineering"),
    ("GET", "/dashboard/kpis", "traction"),
    ("GET", "/dashboard/kpis", "signal"),
    ("GET", "/maintenance-tasks/", "engineering"),
    ("GET", "/maintenance-tasks/", "traction"),
    ("GET", "/maintenance-tasks/", "signal"),
    ("GET", "/maintenance-tasks/", "admin"),
    ("GET", "/maintenance-tasks/", "control"),
    ("GET", "/admin/permission-matrix", "admin"),
    ("GET", "/block-requests/", "signal"),
    ("GET", "/optimized-plan/", "signal"),
    ("GET", "/conflicts/", "signal"),
    ("GET", "/analytics/", "signal"),
    ("GET", "/emergency/", "signal"),
]

@pytest.mark.parametrize("method,path,role_id", ALLOWED_ROLE_CASES)
def test_allowed_roles_not_denied(method, path, role_id):
    headers = get_auth_header(role_id)
    if method == "GET":
        res = client.get(path, headers=headers)
    else:
        res = client.post(path, json={}, headers=headers)
    # The call must pass RBAC; it must not be 401 or 403
    assert res.status_code not in (401, 403), f"Role {role_id} was improperly denied {method} {path} with {res.status_code}"


# 7. Test approver spoofing cannot override token identity
def test_approver_identity_from_token():
    # Only Admin has planner.approve
    admin_headers = get_auth_header("admin")
    # Even if client sends approved_by = "Hacker / Fake DRM", server must accept admin request to route level
    # (and not fail with 403 / 401)
    res = client.post(
        "/optimized-plan/BLK-NONEXISTENT/approve",
        json={"approved_by": "Fake DRM Spoofed"},
        headers=admin_headers
    )
    # Status code will either be 404 (block not found) or 400 (already approved) or 500 (db down), NOT 403 or 401
    assert res.status_code in (400, 404, 500)
    assert res.status_code not in (401, 403)


# 8. Test Signal Team authentication, /auth/me, and scoping helpers
def test_signal_authentication_and_profile():
    from auth.permissions import is_network_scope, department_of, dept_id_of, can_report_emergency_type

    # Verify pure helpers
    assert not is_network_scope("signal")
    assert department_of("signal") == "SMMS"
    assert dept_id_of("signal") == "DEPT-SMMS"
    assert can_report_emergency_type("signal", "Signal Failure")
    assert can_report_emergency_type("signal", "Point Machine Failure")
    assert not can_report_emergency_type("signal", "Track Fracture")
    assert not can_report_emergency_type("signal", "OHE Snapping")

    # Login via /auth/login
    login_res = client.post("/auth/login", json={"role_id": "signal", "password": "12345"})
    assert login_res.status_code == 200
    data = login_res.json()
    assert "access_token" in data
    user = data["user"]
    assert user["role_id"] == "signal"
    assert user["name"] == "SSE / S&T"
    assert user["title"] == "SIGNAL TEAM"
    assert user["dept"] == "SMMS"
    assert user["scope"] == "department"
    assert user["system"] == "SMMS Requisition Portal"
    assert "S&T" in user["reportable_emergency_groups"]

    # Verify /auth/me
    token = data["access_token"]
    me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["user"]["role_id"] == "signal"
    assert me_data["user"]["dept"] == "SMMS"
    assert "requests.create" in me_data["permissions"]
    assert "planner.approve" not in me_data["permissions"]
    assert "optimizer.run" not in me_data["permissions"]

