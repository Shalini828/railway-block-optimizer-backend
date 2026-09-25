from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import psycopg
import importlib
import pkgutil

from db_config import DB_CONFIG
from auth.security import RBACForbiddenException, require_permission, get_current_user, CurrentUser


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="RailWise AI API",
    version="1.0.0",
    description="AI-powered railway maintenance block planning and optimization API",
)


@app.exception_handler(RBACForbiddenException)
async def rbac_forbidden_handler(request, exc: RBACForbiddenException):
    return JSONResponse(
        status_code=403,
        content={
            "detail": exc.detail,
            "code": "FORBIDDEN",
            "required": exc.required,
            "role": exc.role,
        },
    )


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():
    return {
        "status": "success",
        "message": "RailWise AI API is running",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "RailWise AI API",
    }


# ============================================================
# AUTOMATIC ROUTER REGISTRATION
# ============================================================
#
# Every Python file inside backend/routes that exposes
#   router = APIRouter(...)
# will automatically be registered.
#
# This avoids hard-coding filenames such as:
# routes.requests
# routes.maintenance
# etc.
#
# ============================================================

def register_routers():

    import routes

    registered = []

    for module_info in pkgutil.iter_modules(routes.__path__):

        module_name = module_info.name

        # Skip Python cache / private modules
        if module_name.startswith("_"):
            continue

        try:
            module = importlib.import_module(
                f"routes.{module_name}"
            )

            router = getattr(module, "router", None)

            if router is not None:
                app.include_router(router)
                registered.append(module_name)

        except Exception as exc:
            print(
                f"[WARNING] Could not load router "
                f"'routes.{module_name}': {exc}"
            )

    print(
        f"[INFO] Registered routers: "
        f"{', '.join(registered) if registered else 'None'}"
    )


register_routers()


# ============================================================
# LEGACY MAINTENANCE TASKS ENDPOINT
# ============================================================

@app.get("/api/maintenance-tasks", dependencies=[Depends(require_permission("tasks.view"))])
def get_maintenance_tasks(user: CurrentUser = Depends(get_current_user)):

    connection = None
    cursor = None

    try:

        connection = psycopg.connect(**DB_CONFIG)
        cursor = connection.cursor()

        if user.scope != "network":
            cursor.execute("""
                SELECT
                    task_id,
                    asset_id,
                    department,
                    task_type,
                    description,
                    due_date,
                    estimated_duration_min,
                    overdue_days,
                    safety_risk,
                    priority_score,
                    priority_category,
                    task_status
                FROM maintenance_tasks
                WHERE UPPER(department) = %s
                ORDER BY priority_score DESC NULLS LAST
            """, (user.dept.upper(),))
        else:
            cursor.execute("""
                SELECT
                    task_id,
                    asset_id,
                    department,
                    task_type,
                    description,
                    due_date,
                    estimated_duration_min,
                    overdue_days,
                    safety_risk,
                    priority_score,
                    priority_category,
                    task_status
                FROM maintenance_tasks
                ORDER BY priority_score DESC NULLS LAST
            """)

        rows = cursor.fetchall()

        return [
            {
                "task_id": row[0],
                "asset_id": row[1],
                "department": row[2],
                "task_type": row[3],
                "description": row[4],
                "due_date": str(row[5]) if row[5] else None,
                "estimated_duration_min": row[6],
                "overdue_days": row[7],
                "safety_risk": row[8],
                "ai_priority_score": (
                    float(row[9])
                    if row[9] is not None
                    else 0
                ),
                "priority_category": row[10],
                "task_status": row[11],
            }
            for row in rows
        ]

    finally:

        if cursor:
            cursor.close()

        if connection:
            connection.close()