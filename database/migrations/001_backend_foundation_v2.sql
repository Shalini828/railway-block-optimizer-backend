-- ============================================================
-- IR-ABPS / Railway Block Optimizer
-- Database Foundation V2
-- ============================================================

BEGIN;

-- ============================================================
-- 1. ROLES
-- ============================================================

CREATE TABLE IF NOT EXISTS roles (
    role_id VARCHAR(30) PRIMARY KEY,
    role_name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT
);


-- ============================================================
-- 2. DEPARTMENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS departments (
    department_id VARCHAR(30) PRIMARY KEY,
    department_code VARCHAR(20) NOT NULL UNIQUE,
    department_name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    active BOOLEAN DEFAULT TRUE
);


-- ============================================================
-- 3. USERS
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(30) PRIMARY KEY,
    employee_code VARCHAR(30) UNIQUE,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash TEXT,
    role_id VARCHAR(30) NOT NULL,
    department_id VARCHAR(30),
    team_id VARCHAR(30),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT users_role_fk
        FOREIGN KEY (role_id)
        REFERENCES roles(role_id),

    CONSTRAINT users_department_fk
        FOREIGN KEY (department_id)
        REFERENCES departments(department_id),

    CONSTRAINT users_team_fk
        FOREIGN KEY (team_id)
        REFERENCES teams(team_id)
);


-- ============================================================
-- 4. CORRIDOR SECTIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS corridor_sections (
    section_id VARCHAR(30) PRIMARY KEY,
    corridor_id VARCHAR(20) NOT NULL,
    section_code VARCHAR(30) NOT NULL,
    section_name VARCHAR(150),
    start_station VARCHAR(100),
    end_station VARCHAR(100),
    start_km NUMERIC(8,3),
    end_km NUMERIC(8,3),
    line_name VARCHAR(50),
    electrified BOOLEAN DEFAULT TRUE,
    operational_status VARCHAR(30) DEFAULT 'ACTIVE',

    CONSTRAINT corridor_sections_corridor_fk
        FOREIGN KEY (corridor_id)
        REFERENCES corridors(corridor_id),

    CONSTRAINT corridor_sections_unique
        UNIQUE (corridor_id, section_code)
);


-- ============================================================
-- 5. SPECIAL TRAIN SERVICES
-- ============================================================

CREATE TABLE IF NOT EXISTS special_train_services (
    special_train_id VARCHAR(30) PRIMARY KEY,
    train_number VARCHAR(20),
    train_name VARCHAR(150) NOT NULL,
    special_type VARCHAR(50) NOT NULL,
    corridor_id VARCHAR(20) NOT NULL,
    service_date DATE NOT NULL,
    arrival_time TIME,
    departure_time TIME,
    direction VARCHAR(20),
    operational_priority INTEGER DEFAULT 3,
    expected_passengers INTEGER DEFAULT 0,
    reason TEXT,
    active BOOLEAN DEFAULT TRUE,

    CONSTRAINT special_train_corridor_fk
        FOREIGN KEY (corridor_id)
        REFERENCES corridors(corridor_id),

    CONSTRAINT special_train_priority_check
        CHECK (operational_priority BETWEEN 1 AND 5)
);


-- ============================================================
-- 6. EMERGENCY INCIDENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS emergency_incidents (
    incident_id VARCHAR(30) PRIMARY KEY,
    corridor_id VARCHAR(20),
    section_id VARCHAR(30),
    incident_type VARCHAR(80) NOT NULL,
    severity INTEGER NOT NULL,
    incident_date DATE NOT NULL,
    reported_time TIME NOT NULL,
    estimated_resolution_min INTEGER,
    description TEXT,
    status VARCHAR(30) DEFAULT 'OPEN',
    reported_by VARCHAR(30),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT emergency_corridor_fk
        FOREIGN KEY (corridor_id)
        REFERENCES corridors(corridor_id),

    CONSTRAINT emergency_section_fk
        FOREIGN KEY (section_id)
        REFERENCES corridor_sections(section_id),

    CONSTRAINT emergency_severity_check
        CHECK (severity BETWEEN 1 AND 5)
);


-- ============================================================
-- 7. INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_users_role
    ON users(role_id);

CREATE INDEX IF NOT EXISTS idx_users_department
    ON users(department_id);

CREATE INDEX IF NOT EXISTS idx_users_team
    ON users(team_id);

CREATE INDEX IF NOT EXISTS idx_sections_corridor
    ON corridor_sections(corridor_id);

CREATE INDEX IF NOT EXISTS idx_special_trains_corridor_date
    ON special_train_services(corridor_id, service_date);

CREATE INDEX IF NOT EXISTS idx_special_trains_date
    ON special_train_services(service_date);

CREATE INDEX IF NOT EXISTS idx_emergency_corridor
    ON emergency_incidents(corridor_id);

CREATE INDEX IF NOT EXISTS idx_emergency_date
    ON emergency_incidents(incident_date);

CREATE INDEX IF NOT EXISTS idx_emergency_status
    ON emergency_incidents(status);


-- ============================================================
-- 8. DEFAULT ROLES
-- ============================================================

INSERT INTO roles (role_id, role_name, description)
VALUES
    ('ROLE-ADMIN', 'System Administrator',
     'Manages system configuration, users and master data'),

    ('ROLE-PLANNER', 'Planning / DRM',
     'Manages railway block planning and optimization'),

    ('ROLE-TMS', 'TMS Head',
     'Manages track maintenance requests and assets'),

    ('ROLE-SMMS', 'SMMS Head',
     'Manages signalling and telecommunications work'),

    ('ROLE-TDMS', 'TDMS Head',
     'Manages traction and OHE related work'),

    ('ROLE-CONTROLLER', 'Control Officer',
     'Reviews operational conflicts and planned blocks')

ON CONFLICT (role_id) DO NOTHING;


-- ============================================================
-- 9. DEFAULT DEPARTMENTS
-- ============================================================

INSERT INTO departments
    (department_id, department_code, department_name, description)
VALUES
    ('DEPT-TMS', 'TMS', 'Track Maintenance',
     'Track maintenance and engineering operations'),

    ('DEPT-SMMS', 'SMMS', 'Signal & Telecommunication',
     'Signal and telecommunications maintenance'),

    ('DEPT-TDMS', 'TDMS', 'Traction / OHE',
     'Traction and overhead equipment operations'),

    ('DEPT-OPS', 'OPS', 'Operations',
     'Train operations and traffic control'),

    ('DEPT-PLN', 'PLN', 'Planning',
     'Block planning and optimization'),

    ('DEPT-ADMIN', 'ADMIN', 'Administration',
     'System administration')

ON CONFLICT (department_id) DO NOTHING;


-- ============================================================
-- 10. COMMENTS
-- ============================================================

COMMENT ON TABLE roles IS
    'Application roles used for backend RBAC';

COMMENT ON TABLE departments IS
    'Railway operational departments';

COMMENT ON TABLE users IS
    'Application users mapped to roles, departments and teams';

COMMENT ON TABLE corridor_sections IS
    'Operational sections within railway corridors';

COMMENT ON TABLE special_train_services IS
    'Special, festival and event-related train services';

COMMENT ON TABLE emergency_incidents IS
    'Emergency incidents used for advisory planning and replanning';


COMMIT;