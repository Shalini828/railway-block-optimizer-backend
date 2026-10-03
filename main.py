from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import psycopg
import importlib
import random
from datetime import date,time, timedelta
import pkgutil

from db_config import DB_CONFIG
from auth.security import (
    RBACForbiddenException,
    require_permission,
    get_current_user,
    CurrentUser,
)


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
# DATABASE AUTO-MIGRATION (SAFE & IDEMPOTENT)
# ============================================================

def ensure_database_schema():
    connection = None
    try:
        connection = psycopg.connect(**DB_CONFIG)
        with connection.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.emergency_incidents (
                    incident_id VARCHAR(50) PRIMARY KEY,
                    emergency_type VARCHAR(100) NOT NULL DEFAULT 'Other Critical Hazard',
                    incident_type VARCHAR(100),
                    section VARCHAR(100),
                    section_id VARCHAR(50),
                    corridor_id VARCHAR(50),
                    line VARCHAR(50),
                    severity INT DEFAULT 1,
                    incident_date DATE DEFAULT CURRENT_DATE,
                    reported_time TIME DEFAULT CURRENT_TIME,
                    estimated_resolution_min INT DEFAULT 60,
                    description TEXT,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(50) DEFAULT 'ACTIVE',
                    control_notified BOOLEAN DEFAULT FALSE,
                    traffic_protection_status VARCHAR(50) DEFAULT 'PENDING',
                    reported_by VARCHAR(50),
                    resolved_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                ALTER TABLE IF EXISTS public.emergency_incidents
                    ADD COLUMN IF NOT EXISTS emergency_type VARCHAR(100) DEFAULT 'Other Critical Hazard',
                    ADD COLUMN IF NOT EXISTS incident_type VARCHAR(100),
                    ADD COLUMN IF NOT EXISTS section VARCHAR(100),
                    ADD COLUMN IF NOT EXISTS line VARCHAR(50),
                    ADD COLUMN IF NOT EXISTS severity INT DEFAULT 1,
                    ADD COLUMN IF NOT EXISTS started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'ACTIVE',
                    ADD COLUMN IF NOT EXISTS control_notified BOOLEAN DEFAULT FALSE,
                    ADD COLUMN IF NOT EXISTS traffic_protection_status VARCHAR(50) DEFAULT 'PENDING',
                    ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP,
                    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

                CREATE TABLE IF NOT EXISTS public.optimization_history (
                    history_id BIGSERIAL PRIMARY KEY,
                    run_timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    blocks_generated INT DEFAULT 0,
                    total_train_impact NUMERIC(8,2) DEFAULT 0,
                    execution_time_ms NUMERIC(10,2) DEFAULT 0,
                    optimization_score NUMERIC(7,2) DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );

                ALTER TABLE IF EXISTS public.optimized_blocks
                    ADD COLUMN IF NOT EXISTS approved_by VARCHAR(150),
                    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ,
                    ADD COLUMN IF NOT EXISTS block_status VARCHAR(30) DEFAULT 'PENDING',
                    ADD COLUMN IF NOT EXISTS ai_decision_confidence JSONB,
                    ADD COLUMN IF NOT EXISTS ai_reasons JSONB,
                    ADD COLUMN IF NOT EXISTS ai_explanation JSONB;

                ALTER TABLE IF EXISTS public.block_requests
                    ADD COLUMN IF NOT EXISTS review_status VARCHAR(30) DEFAULT 'PENDING',
                    ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR(150),
                    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ,
                    ADD COLUMN IF NOT EXISTS rejection_reason TEXT,
                    ADD COLUMN IF NOT EXISTS submitted_date DATE,
                    ADD COLUMN IF NOT EXISTS criticality VARCHAR(30),
                    ADD COLUMN IF NOT EXISTS safety_risk VARCHAR(30);

                CREATE TABLE IF NOT EXISTS public.block_review_events (
                    event_id BIGSERIAL PRIMARY KEY,
                    block_id VARCHAR(30) NOT NULL,
                    actor_role VARCHAR(30) NOT NULL,
                    actor_name VARCHAR(150),
                    actor_dept VARCHAR(20),
                    action VARCHAR(40) NOT NULL,
                    note TEXT,
                    payload JSONB,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS public.audit_log (
                    audit_id BIGSERIAL PRIMARY KEY,
                    ts TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    actor_role VARCHAR(30),
                    actor_name VARCHAR(150),
                    method VARCHAR(10),
                    path TEXT,
                    action VARCHAR(60),
                    target_type VARCHAR(40),
                    target_id VARCHAR(60),
                    outcome VARCHAR(10),
                    detail JSONB
                );

                ALTER TABLE IF EXISTS public.special_train_services
                    ADD COLUMN IF NOT EXISTS origin_station VARCHAR(100),
                    ADD COLUMN IF NOT EXISTS destination_station VARCHAR(100),
                    ADD COLUMN IF NOT EXISTS created_by VARCHAR(150),
                    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

                CREATE SEQUENCE IF NOT EXISTS special_train_seq START 1;
            """)
            connection.commit()
            print("[INFO] Database schema migration verified successfully.")
            return {"status": "success", "message": "Schema migration applied."}
    except Exception as exc:
        print(f"[WARNING] Database schema auto-migration check: {exc}")
        return {"status": "error", "message": str(exc)}
    finally:
        if connection:
            connection.close()


# Run migration on startup
ensure_database_schema()


from fastapi import Request

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    origin = request.headers.get("origin")
    allowed = origin if origin else "*"
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "status": "error"},
        headers={
            "Access-Control-Allow-Origin": allowed,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )


# ============================================================
# DEBUG: DATABASE USER & CONNECTION (FOR VERCEL DEPLOYMENT)
# ============================================================

@app.get("/debug/migrate")
def debug_migrate():
    return ensure_database_schema()

@app.get("/debug/db-user")
def debug_db_user():
    import os
    env_user = os.getenv("DB_USER")
    config_user = DB_CONFIG.get("user")
    return {
        "env_user_exists": env_user is not None,
        "env_user_is_pooler_format": (
            env_user.startswith("postgres.") if env_user else False
        ),
        "config_user_exists": config_user is not None,
        "config_user_is_pooler_format": (
            config_user.startswith("postgres.") if config_user else False
        ),
        "config_user_is_plain_postgres": (config_user == "postgres"),
    }


@app.get("/debug/db-connection")
def debug_db_connection():
    connection = None
    try:
        connection = psycopg.connect(**DB_CONFIG)
        return {
            "database_connection": "success",
            "db_user_configured": True,
        }
    except Exception as exc:
        return {
            "database_connection": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    finally:
        if connection:
            connection.close()

@app.get("/debug/data-counts")
def debug_data_counts():
    connection = None
    try:
        connection = psycopg.connect(**DB_CONFIG)
        cursor = connection.cursor()

        tables = [
            "zones_divisions",
            "corridors",
            "assets",
            "trains",
            "defects",
            "maintenance_tasks",
            "teams",
            "block_requests",
            "optimized_blocks",
            "goods_train_forecast",
            "maintenance_history",
        ]

        counts = {}

        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]

            cursor.execute("""
                SELECT request_status, COUNT(*)
                FROM block_requests
                GROUP BY request_status
                ORDER BY request_status
            """)

            status_counts = {
                row[0]: row[1]
                for row in cursor.fetchall()
            }

        cursor.close()

        return {
            "status": "success",
            "counts": counts,
            "block_request_statuses": status_counts
        }

    except Exception as exc:
        return {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)
        }

    finally:
        if connection:
            connection.close()


@app.get("/debug/seed-zones")
def seed_zones():
    connection = None
    try:
        connection = psycopg.connect(**DB_CONFIG)
        cursor = connection.cursor()

        zones = [
            ("Northern Railway", "Division 1", "Delhi"),
            ("Western Railway", "Division 2", "Mumbai"),
            ("Eastern Railway", "Division 3", "Kolkata"),
            ("Southern Railway", "Division 4", "Chennai"),
            ("Central Railway", "Division 5", "Bhopal"),
        ]

        for i, (zone_name, division_name, headquarters) in enumerate(zones, start=1):
            cursor.execute("""
                INSERT INTO zones_divisions
                (division_id, zone_name, division_name, headquarters)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (division_id) DO NOTHING
            """, (i, zone_name, division_name, headquarters))

        connection.commit()
        cursor.close()

        return {
            "status": "success",
            "message": "Zones/divisions seeded successfully"
        }

    except Exception as exc:
        return {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)
        }

    finally:
        if connection:
            connection.close()


@app.get("/debug/seed-corridors")
def seed_corridors():
    connection = None
    try:
        connection = psycopg.connect(**DB_CONFIG)
        cursor = connection.cursor()

        corridors = [
            ("C02", 1, "Delhi-Ghaziabad Main Corridor", "Delhi", "Ghaziabad"),
            ("C03", 2, "Ghaziabad-Meerut Main Corridor", "Ghaziabad", "Meerut"),
            ("C04", 3, "Delhi-Panipat Main Corridor", "Delhi", "Panipat"),
            ("C05", 4, "Panipat-Ambala Main Corridor", "Panipat", "Ambala"),
            ("C06", 5, "Mumbai-Thane Main Corridor", "Mumbai", "Thane"),
            ("C07", 1, "Thane-Nashik Main Corridor", "Thane", "Nashik"),
            ("C08", 2, "Chennai-Arakkonam Main Corridor", "Chennai", "Arakkonam"),
            ("C09", 3, "Kolkata-Howrah Main Corridor", "Kolkata", "Howrah"),
            ("C10", 4, "Bhopal-Itarsi Main Corridor", "Bhopal", "Itarsi"),
            ("C11", 5, "Pune-Lonavala Main Corridor", "Pune", "Lonavala"),
        ]

        for corridor in corridors:
            cursor.execute("""
                INSERT INTO corridors (
                    corridor_id, division_id, corridor_name,
                    source_station, destination_station,
                    distance_km, traffic_level,
                    electrified, max_block_duration_min
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (corridor_id) DO NOTHING
            """, (
                corridor[0], corridor[1], corridor[2],
                corridor[3], corridor[4],
                100, "HIGH", True, 120
            ))

        connection.commit()
        cursor.close()

        return {
            "status": "success",
            "message": "Corridors seeded successfully"
        }

    except Exception as exc:
        return {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)
        }

    finally:
        if connection:
            connection.close()

@app.get("/debug/seed-assets")
def seed_assets():
    connection = None
    try:
        connection = psycopg.connect(**DB_CONFIG)
        cursor = connection.cursor()

        cursor.execute("""
            SELECT corridor_id, distance_km
            FROM corridors
        """)
        corridors = cursor.fetchall()

        if not corridors:
            return {
                "status": "failed",
                "message": "No corridors found"
            }

        asset_types = {
            "ENGINEERING": ["Track", "Bridge", "Point & Crossing"],
            "S&T": ["Signal", "Axle Counter", "Point Machine"],
            "TRD": ["OHE", "Transformer", "Section Insulator"]
        }

        import random
        from datetime import date, timedelta

        cursor.execute("SELECT asset_id FROM assets")
        existing_assets = {row[0] for row in cursor.fetchall()}

        today = date(2026, 8, 27)
        created = 0
        asset_number = 1

        while created < 100:
            asset_id = f"AST-{asset_number:04d}"
            asset_number += 1

            if asset_id in existing_assets:
                continue

            corridor_id, corridor_distance = random.choice(corridors)
            department = random.choice(list(asset_types.keys()))
            asset_type = random.choice(asset_types[department])

            location_km = round(
                random.uniform(0, float(corridor_distance)), 3
            )

            criticality = random.choices(
                [1, 2, 3, 4, 5],
                weights=[10, 15, 30, 30, 15]
            )[0]

            health_score = round(random.uniform(40, 100), 2)

            failure_risk = round(
                max(
                    1,
                    min(
                        99,
                        100 - health_score
                        + (criticality * 5)
                        + random.uniform(-10, 10)
                    )
                ),
                2
            )

            installation_date = date(
                random.randint(2005, 2024),
                random.randint(1, 12),
                random.randint(1, 28)
            )

            last_inspection_date = today - timedelta(
                days=random.randint(1, 365)
            )

            operational_status = random.choices(
                ["OPERATIONAL", "DEGRADED", "UNDER_MAINTENANCE"],
                weights=[90, 7, 3]
            )[0]

            cursor.execute("""
                INSERT INTO assets (
                    asset_id,
                    corridor_id,
                    department,
                    asset_type,
                    location_km,
                    criticality,
                    health_score,
                    failure_risk,
                    installation_date,
                    last_inspection_date,
                    operational_status
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (asset_id) DO NOTHING
            """, (
                asset_id,
                corridor_id,
                department,
                asset_type,
                location_km,
                criticality,
                health_score,
                failure_risk,
                installation_date,
                last_inspection_date,
                operational_status
            ))

            created += 1

        connection.commit()
        cursor.close()

        return {
            "status": "success",
            "message": f"{created} assets seeded successfully"
        }

    except Exception as exc:
        return {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)
        }

    finally:
        if connection:
            connection.close()


@app.get("/debug/seed-trains")
def seed_trains():
    connection = None
    try:
        connection = psycopg.connect(**DB_CONFIG)
        cursor = connection.cursor()

        trains = [
            ("TR-106", "12952", "Mumbai Rajdhani", "Express", "C02",
             "2026-08-30", "20:30", "20:35", "DOWN", 5),
            ("TR-107", "12001", "Bhopal Shatabdi", "Express", "C03",
             "2026-08-30", "21:15", "21:20", "UP", 4),
            ("TR-108", "12432", "Rajdhani Express", "Express", "C04",
             "2026-08-30", "22:00", "22:05", "DOWN", 5),
            ("TR-109", "12012", "Kalka Shatabdi", "Express", "C05",
             "2026-08-30", "23:00", "23:05", "UP", 3),
            ("TR-110", "12138", "Punjab Mail", "Passenger", "C06",
             "2026-08-30", "23:30", "23:35", "DOWN", 2)
        ]

        for train in trains:
            cursor.execute("""
                INSERT INTO trains (
                    train_id, train_number, train_name, train_type,
                    corridor_id, travel_date, arrival_time,
                    departure_time, direction, operational_priority
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (train_id) DO NOTHING
            """, train)

        connection.commit()
        cursor.close()

        return {
            "status": "success",
            "message": "Train data seeded successfully",
            "count": len(trains)
        }

    except Exception as exc:
        return {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)
        }

    finally:
        if connection:
            connection.close()


@app.get("/debug/seed-defects")
def seed_defects():
    connection = None
    try:
        connection = psycopg.connect(**DB_CONFIG)
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                asset_id,
                department,
                criticality,
                health_score,
                failure_risk
            FROM assets
        """)
        assets = cursor.fetchall()

        if not assets:
            return {
                "status": "failed",
                "message": "No assets found"
            }

        import random
        from datetime import date, timedelta

        defect_types = {
            "ENGINEERING": [
                "Rail Crack",
                "Track Geometry Deviation",
                "Sleeper Damage",
                "Point & Crossing Wear"
            ],
            "S&T": [
                "Signal Malfunction",
                "Axle Counter Failure",
                "Point Machine Failure",
                "Relay Fault"
            ],
            "TRD": [
                "Insulator Damage",
                "OHE Wire Wear",
                "Transformer Issue",
                "Pantograph Interaction Issue"
            ]
        }

        cursor.execute("SELECT defect_id FROM defects")
        existing_defects = {row[0] for row in cursor.fetchall()}

        today = date(2026, 8, 27)
        created = 0
        defect_number = 1

        while created < 80:
            defect_id = f"DEF-{defect_number:04d}"
            defect_number += 1

            if defect_id in existing_defects:
                continue

            asset = random.choice(assets)

            asset_id = asset[0]
            department = asset[1]
            criticality = asset[2]
            health_score = float(asset[3])
            failure_risk = float(asset[4])

            risk_factor = (
                (100 - health_score) * 0.4
                + failure_risk * 0.4
                + criticality * 4
            )

            defect_probability = min(0.95, risk_factor / 120)

            if random.random() > defect_probability:
                continue

            defect_type = random.choice(defect_types[department])

            if risk_factor >= 75:
                severity = "CRITICAL"
                safety_impact = random.choice([4, 5])
            elif risk_factor >= 55:
                severity = "HIGH"
                safety_impact = random.choice([3, 4, 5])
            elif risk_factor >= 35:
                severity = "MEDIUM"
                safety_impact = random.choice([2, 3])
            else:
                severity = "LOW"
                safety_impact = random.choice([1, 2])

            detected_date = today - timedelta(
                days=random.randint(1, 90)
            )

            repeat_failure = (
                random.random() < min(0.8, failure_risk / 130)
            )

            status = random.choices(
                ["OPEN", "IN_PROGRESS", "RESOLVED"],
                weights=[65, 20, 15]
            )[0]

            if severity == "CRITICAL":
                status = random.choice(["OPEN", "IN_PROGRESS"])

            if severity == "CRITICAL":
                days_to_resolve = random.randint(1, 3)
            elif severity == "HIGH":
                days_to_resolve = random.randint(2, 7)
            elif severity == "MEDIUM":
                days_to_resolve = random.randint(5, 14)
            else:
                days_to_resolve = random.randint(10, 30)

            target_resolution_date = (
                detected_date + timedelta(days=days_to_resolve)
            )

            description = (
                f"{defect_type} detected on "
                f"{department} asset during inspection"
            )

            cursor.execute("""
                INSERT INTO defects (
                    defect_id,
                    asset_id,
                    defect_type,
                    severity,
                    detected_date,
                    description,
                    safety_impact,
                    repeat_failure,
                    status,
                    target_resolution_date
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                ON CONFLICT (defect_id) DO NOTHING
            """, (
                defect_id,
                asset_id,
                defect_type,
                severity,
                detected_date,
                description,
                safety_impact,
                repeat_failure,
                status,
                target_resolution_date
            ))

            created += 1

        connection.commit()
        cursor.close()

        return {
            "status": "success",
            "message": f"{created} defects seeded successfully",
            "count": created
        }

    except Exception as exc:
        return {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)
        }

    finally:
        if connection:
            connection.close()


@app.get("/debug/seed-maintenance-tasks")
def seed_maintenance_tasks():
    connection = None
    try:
        connection = psycopg.connect(**DB_CONFIG)
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                d.defect_id,
                d.asset_id,
                d.defect_type,
                d.severity,
                d.detected_date,
                d.safety_impact,
                d.repeat_failure,
                d.target_resolution_date,
                a.department,
                a.criticality,
                a.failure_risk
            FROM defects d
            JOIN assets a
                ON d.asset_id = a.asset_id
            WHERE d.status != 'RESOLVED'
        """)

        defects = cursor.fetchall()

        if not defects:
            return {
                "status": "failed",
                "message": "No unresolved defects found"
            }

        from datetime import date

        cursor.execute("SELECT task_id FROM maintenance_tasks")
        existing_tasks = {row[0] for row in cursor.fetchall()}

        today = date(2026, 8, 27)
        created = 0
        task_number = 1

        for defect in defects:

            (
                defect_id,
                asset_id,
                defect_type,
                severity,
                detected_date,
                safety_impact,
                repeat_failure,
                target_resolution_date,
                department,
                criticality,
                failure_risk
            ) = defect

            while f"T-AUTO-{task_number:04d}" in existing_tasks:
                task_number += 1

            task_id = f"T-AUTO-{task_number:04d}"
            task_number += 1

            if department == "ENGINEERING":
                duration = 120
            elif department == "S&T":
                duration = 90
            else:
                duration = 100

            overdue_days = max(
                0,
                (today - target_resolution_date).days
            )

            priority_score = (
                criticality * 20
                + float(failure_risk) * 0.30
                + int(safety_impact) * 10
                + min(overdue_days, 30) * 1.5
                + (10 if repeat_failure else 0)
            )

            priority_score = round(
                min(100, priority_score),
                2
            )

            if priority_score >= 85:
                priority_category = "CRITICAL"
            elif priority_score >= 70:
                priority_category = "HIGH"
            elif priority_score >= 50:
                priority_category = "MEDIUM"
            else:
                priority_category = "LOW"

            if severity in ["CRITICAL", "HIGH"]:
                task_type = "Corrective Maintenance"
            else:
                task_type = "Preventive Maintenance"

            description = (
                f"Resolve {defect_type} on asset {asset_id}"
            )

            cursor.execute("""
                INSERT INTO maintenance_tasks (
                    task_id,
                    asset_id,
                    department,
                    task_type,
                    description,
                    created_date,
                    due_date,
                    estimated_duration_min,
                    overdue_days,
                    safety_risk,
                    task_status,
                    priority_score,
                    priority_category
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (task_id) DO NOTHING
            """, (
                task_id,
                asset_id,
                department,
                task_type,
                description,
                today,
                target_resolution_date,
                duration,
                overdue_days,
                safety_impact,
                "PENDING",
                priority_score,
                priority_category
            ))

            created += 1

        connection.commit()
        cursor.close()

        return {
            "status": "success",
            "message": f"{created} maintenance tasks seeded successfully",
            "count": created
        }

    except Exception as exc:
        return {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)
        }

    finally:
        if connection:
            connection.close()



# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://railway-block-optimizer-frontend.vercel.app",
    ],
    allow_origin_regex=r"^https://.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# ROOT & HEALTH
# ============================================================

@app.get("/")
@app.get("/api")
def root():
    return {
        "status": "success",
        "message": "RailWise AI API is running",
    }


@app.get("/health")
@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "service": "RailWise AI API",
    }

@app.get("/debug/seed-teams")
def debug_seed_teams():
    connection = None
    try:
        connection = psycopg.connect(**DB_CONFIG)
        cursor = connection.cursor()

        teams = [
            (
                "ENG-01",
                "ENGINEERING",
                "Engineering Maintenance Team",
                "Track & Civil Engineering",
                "Division HQ",
                8.0,
                True
            ),
            (
                "SNT-01",
                "S&T",
                "Signal & Telecom Maintenance Team",
                "Signalling & Telecom",
                "Division HQ",
                8.0,
                True
            ),
            (
                "TRD-01",
                "TRD",
                "Traction Distribution Team",
                "Electrical Traction",
                "Division HQ",
                8.0,
                True
            ),
        ]

        for team in teams:
            cursor.execute(
                """
                INSERT INTO teams
                (team_id, department, team_name, skill_type,
                 base_location, max_daily_hours, available)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (team_id) DO NOTHING
                """,
                team
            )

        connection.commit()
        cursor.close()

        return {
            "status": "success",
            "message": "Teams seeded successfully",
            "teams": ["ENG-01", "SNT-01", "TRD-01"]
        }

    except Exception as exc:
        if connection:
            connection.rollback()
        return {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)
        }

    finally:
        if connection:
            connection.close()



@app.get("/debug/seed-history")
def debug_seed_history():
    connection = None

    try:
        connection = psycopg.connect(**DB_CONFIG)
        cursor = connection.cursor()

        cursor.execute("""
            SELECT asset_id, department, failure_risk
            FROM assets
        """)
        assets = cursor.fetchall()

        team_mapping = {
            "ENGINEERING": "ENG-01",
            "S&T": "SNT-01",
            "TRD": "TRD-01"
        }

        maintenance_types = {
            "ENGINEERING": [
                "Preventive Inspection",
                "Track Maintenance",
                "Corrective Repair"
            ],
            "S&T": [
                "Signal Inspection",
                "Telecom Maintenance",
                "Corrective Repair"
            ],
            "TRD": [
                "Electrical Inspection",
                "Traction Maintenance",
                "Corrective Repair"
            ]
        }

        history_created = 0

        for asset_id, department, failure_risk in assets:

            events = random.randint(1, 5)

            for _ in range(events):

                maintenance_date = date.today() - timedelta(
                    days=random.randint(30, 700)
                )

                maintenance_type = random.choice(
                    maintenance_types[department]
                )

                if maintenance_type == "Corrective Repair":
                    duration_min = random.randint(60, 180)
                else:
                    duration_min = random.randint(30, 120)

                team_id = team_mapping[department]

                failure_probability = min(
                    0.75,
                    float(failure_risk) / 140
                )

                failure_after_maintenance = (
                    random.random() < failure_probability
                )

                remarks = (
                    "Repeat issue observed after maintenance"
                    if failure_after_maintenance
                    else "Maintenance completed successfully"
                )

                cursor.execute(
                    """
                    INSERT INTO maintenance_history
                    (
                        asset_id,
                        maintenance_type,
                        maintenance_date,
                        duration_min,
                        team_id,
                        failure_after_maintenance,
                        remarks
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        asset_id,
                        maintenance_type,
                        maintenance_date,
                        duration_min,
                        team_id,
                        failure_after_maintenance,
                        remarks
                    )
                )

                history_created += 1

        connection.commit()
        cursor.close()

        return {
            "status": "success",
            "message": "Maintenance history seeded successfully",
            "records_created": history_created
        }

    except Exception as exc:
        if connection:
            connection.rollback()

        return {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)
        }

    finally:
        if connection:
            connection.close()


@app.get("/debug/seed-block-requests")
def debug_seed_block_requests():
    connection = None

    try:
        connection = psycopg.connect(**DB_CONFIG)
        cursor = connection.cursor()

        TODAY = date(2026, 8, 27)

        cursor.execute("""
            SELECT request_id
            FROM block_requests
        """)

        existing_requests = {
            row[0] for row in cursor.fetchall()
        }

        cursor.execute("""
            SELECT
                t.task_id,
                t.department,
                t.estimated_duration_min,
                t.priority_score,
                a.corridor_id
            FROM maintenance_tasks t
            JOIN assets a
                ON t.asset_id = a.asset_id
            WHERE t.task_status = 'PENDING'
        """)

        tasks = cursor.fetchall()

        if not tasks:
            cursor.close()
            return {
                "status": "failed",
                "message": "No pending maintenance tasks found"
            }

        team_mapping = {
            "ENGINEERING": "ENG-01",
            "S&T": "SNT-01",
            "TRD": "TRD-01"
        }

        start_times = [
            time(0, 0),
            time(1, 0),
            time(2, 0),
            time(3, 0),
            time(4, 0),
            time(10, 0),
            time(11, 0),
            time(12, 0),
            time(14, 0),
            time(22, 0)
        ]

        created = 0
        request_number = 1

        for task in tasks:

            (
                task_id,
                department,
                estimated_duration,
                priority_score,
                corridor_id
            ) = task

            while f"BR-AUTO-{request_number:04d}" in existing_requests:
                request_number += 1

            request_id = f"BR-AUTO-{request_number:04d}"
            request_number += 1

            team_id = team_mapping[department]

            requested_date = TODAY + timedelta(
                days=random.randint(1, 7)
            )

            start = random.choice(start_times)

            duration = int(estimated_duration)

            start_minutes = start.hour * 60 + start.minute
            end_minutes = start_minutes + duration

            end = time(
                (end_minutes // 60) % 24,
                end_minutes % 60
            )

            block_type = (
                "FULL_BLOCK"
                if duration >= 120
                else "PARTIAL_BLOCK"
            )

            cursor.execute(
                """
                INSERT INTO block_requests
                (
                    request_id,
                    task_id,
                    team_id,
                    corridor_id,
                    requested_date,
                    requested_start,
                    requested_end,
                    requested_duration_min,
                    block_type,
                    request_status,
                    submitted_date
                )
                VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    request_id,
                    task_id,
                    team_id,
                    corridor_id,
                    requested_date,
                    start,
                    end,
                    duration,
                    block_type,
                    "PENDING",
                    TODAY
                )
            )

            existing_requests.add(request_id)
            created += 1

        connection.commit()
        cursor.close()

        return {
            "status": "success",
            "message": "Block requests seeded successfully",
            "records_created": created
        }

    except Exception as exc:
        if connection:
            connection.rollback()

        return {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)
        }

    finally:
        if connection:
            connection.close()



# ============================================================
# AUTOMATIC ROUTER REGISTRATION
# ============================================================
#
# Every Python file inside backend/routes that exposes
#   router = APIRouter(...)
# will automatically be registered under both / and /api.
#
# ============================================================

def register_routers():
    import routes

    registered = []

    for module_info in pkgutil.iter_modules(routes.__path__):
        module_name = module_info.name

        # Skip Python cache / private modules / backup files
        if module_name.startswith("_") or "WORKING" in module_name:
            continue

        try:
            module = importlib.import_module(f"routes.{module_name}")
            router = getattr(module, "router", None)

            if router is not None:
                app.include_router(router)
                app.include_router(router, prefix="/api")
                registered.append(module_name)

        except Exception as exc:
            import traceback
            traceback.print_exc()
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

@app.get(
    "/api/maintenance-tasks",
    dependencies=[Depends(require_permission("tasks.view"))],
)
def get_maintenance_tasks(
    user: CurrentUser = Depends(get_current_user),
):

    connection = None
    cursor = None

    try:

        connection = psycopg.connect(**DB_CONFIG)
        cursor = connection.cursor()

        if user.scope != "network":
            cursor.execute(
                """
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
                """,
                (user.dept.upper(),),
            )
        else:
            cursor.execute(
                """
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
                """
            )

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