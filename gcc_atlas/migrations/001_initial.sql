-- GCC Atlas initial schema. SQLite only.
-- Verification statuses (shared by every table that carries one):
--   discovered, extracted, verified_official, verified_independent, needs_review,
--   conflicting, possibly_outdated, unverified, rejected

CREATE TABLE cities (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    state       TEXT NOT NULL,
    state_code  TEXT NOT NULL,
    aliases     TEXT NOT NULL DEFAULT ''          -- semicolon-separated, e.g. 'Bangalore'
);

CREATE TABLE sources (
    id                      INTEGER PRIMARY KEY,
    source_key              TEXT NOT NULL UNIQUE,  -- e.g. S001, stable across rebuilds
    name                    TEXT NOT NULL,
    publisher               TEXT NOT NULL,
    url                     TEXT NOT NULL UNIQUE,
    source_type             TEXT NOT NULL,
    tier                    INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 7),
    data_categories         TEXT NOT NULL DEFAULT '',
    related_entities        TEXT NOT NULL DEFAULT '',
    access_method           TEXT NOT NULL,
    publication_date        TEXT,
    publication_date_basis  TEXT NOT NULL DEFAULT 'unknown'
                            CHECK (publication_date_basis IN ('url_path','search_snippet','document','unknown')),
    access_restrictions     TEXT NOT NULL DEFAULT '',
    discovered_via          TEXT NOT NULL,
    discovery_date          TEXT NOT NULL,
    last_retrieval_attempt  TEXT,
    last_retrieval_date     TEXT,                  -- set only on a successful retrieval
    retrieval_status        TEXT NOT NULL DEFAULT 'not_attempted'
                            CHECK (retrieval_status IN ('not_attempted','retrieved','http_error','network_blocked','failed')),
    http_status             INTEGER,
    content_sha256          TEXT,
    notes                   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_sources_status ON sources(retrieval_status);
CREATE INDEX idx_sources_tier ON sources(tier);

-- Retrieved content. Needed so claims can be checked against the actual text that was fetched.
CREATE TABLE source_documents (
    id            INTEGER PRIMARY KEY,
    source_id     INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    retrieved_at  TEXT NOT NULL,
    method        TEXT NOT NULL CHECK (method IN ('http','playwright','manual_upload')),
    content_type  TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    text          TEXT NOT NULL,
    UNIQUE (source_id, sha256)
);

CREATE TABLE companies (
    id          INTEGER PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL UNIQUE,
    aliases     TEXT NOT NULL DEFAULT '',          -- semicolon-separated names used in sources
    industry    TEXT NOT NULL,
    hq_country  TEXT,
    notes       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE entities (
    id               INTEGER PRIMARY KEY,
    name             TEXT NOT NULL,
    jurisdiction     TEXT NOT NULL,
    entity_type      TEXT NOT NULL DEFAULT 'company',
    registration_id  TEXT,                         -- e.g. CIN for Indian companies
    company_id       INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    UNIQUE (name, jurisdiction)
);

CREATE TABLE claims (
    id                   INTEGER PRIMARY KEY,
    subject_type         TEXT NOT NULL CHECK (subject_type IN
                           ('company','gcc_centre','entity','relationship','policy','policy_version',
                            'incentive','cost_observation','talent_observation','city')),
    subject_id           INTEGER NOT NULL,
    field                TEXT NOT NULL,            -- e.g. 'presence', 'headcount', 'status'
    value_text           TEXT NOT NULL,
    value_num            REAL,
    unit                 TEXT,
    currency             TEXT,
    as_of_date           TEXT,                     -- date the fact describes, not the publication date
    geography            TEXT,
    source_id            INTEGER REFERENCES sources(id),
    evidence_excerpt     TEXT,                     -- verbatim text from a retrieved document
    evidence_locator     TEXT,                     -- page number, CSS path, paragraph
    evidence_match       INTEGER,                  -- 1/0 set by automated check, NULL = not checked
    verification_status  TEXT NOT NULL DEFAULT 'discovered' CHECK (verification_status IN
                           ('discovered','extracted','verified_official','verified_independent','needs_review',
                            'conflicting','possibly_outdated','unverified','rejected')),
    verification_note    TEXT NOT NULL DEFAULT '',
    reviewed_by          TEXT,
    reviewed_at          TEXT,
    claim_hash           TEXT NOT NULL UNIQUE,     -- dedup key
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_claims_subject ON claims(subject_type, subject_id);
CREATE INDEX idx_claims_status ON claims(verification_status);
CREATE INDEX idx_claims_source ON claims(source_id);

CREATE TABLE gcc_centres (
    id                   INTEGER PRIMARY KEY,
    company_id           INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    entity_id            INTEGER REFERENCES entities(id),
    city_id              INTEGER NOT NULL REFERENCES cities(id),
    name                 TEXT NOT NULL,
    operational_status   TEXT NOT NULL CHECK (operational_status IN
                           ('operating','announced','general_office','unverified_lead','closed')),
    functions            TEXT NOT NULL DEFAULT '',
    announced_date       TEXT,
    established_date     TEXT,
    verification_status  TEXT NOT NULL DEFAULT 'discovered' CHECK (verification_status IN
                           ('discovered','extracted','verified_official','verified_independent','needs_review',
                            'conflicting','possibly_outdated','unverified','rejected')),
    UNIQUE (company_id, city_id, name)
);
CREATE INDEX idx_centres_city ON gcc_centres(city_id);

CREATE TABLE company_entity_relationships (
    id                   INTEGER PRIMARY KEY,
    parent_entity_id     INTEGER NOT NULL REFERENCES entities(id),
    child_entity_id      INTEGER NOT NULL REFERENCES entities(id),
    relationship_type    TEXT NOT NULL CHECK (relationship_type IN
                           ('subsidiary','wholly_owned_subsidiary','branch','operates_gcc','affiliate')),
    effective_date       TEXT,
    source_id            INTEGER REFERENCES sources(id),
    claim_id             INTEGER REFERENCES claims(id),
    verification_status  TEXT NOT NULL DEFAULT 'discovered' CHECK (verification_status IN
                           ('discovered','extracted','verified_official','verified_independent','needs_review',
                            'conflicting','possibly_outdated','unverified','rejected')),
    CHECK (parent_entity_id <> child_entity_id),
    UNIQUE (parent_entity_id, child_entity_id, relationship_type)
);

CREATE TABLE cost_observations (
    id                   INTEGER PRIMARY KEY,
    cost_stage           TEXT NOT NULL CHECK (cost_stage IN ('setup','recurring')),
    category             TEXT NOT NULL,           -- e.g. office_rent, fit_out, cam, incorporation_fee
    city_id              INTEGER REFERENCES cities(id),
    geographic_scope     TEXT NOT NULL,           -- 'city', 'micro-market: ORR', 'India'
    building_category    TEXT,                    -- 'Grade A', etc.
    value_num            REAL,
    value_low            REAL,
    value_high           REAL,
    currency             TEXT,
    unit                 TEXT,                    -- 'per sq ft', 'per seat', 'flat'
    period               TEXT,                    -- 'per_month', 'per_year', 'one_time'
    period_start         TEXT,                    -- period the figure describes
    period_end           TEXT,
    publication_date     TEXT,
    retrieval_date       TEXT,
    methodology          TEXT,
    source_id            INTEGER REFERENCES sources(id),
    claim_id             INTEGER REFERENCES claims(id),
    verification_status  TEXT NOT NULL DEFAULT 'discovered' CHECK (verification_status IN
                           ('discovered','extracted','verified_official','verified_independent','needs_review',
                            'conflicting','possibly_outdated','unverified','rejected')),
    observed_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_costs_city_cat ON cost_observations(city_id, category);

CREATE TABLE policies (
    id                   INTEGER PRIMARY KEY,
    name                 TEXT NOT NULL,
    state                TEXT NOT NULL,           -- state name, or 'Central'
    issuing_authority    TEXT,
    policy_kind          TEXT NOT NULL CHECK (policy_kind IN ('state_incentive_policy','regulation','scheme')),
    status               TEXT NOT NULL CHECK (status IN
                           ('under_preparation','draft','announced','active','expired','superseded','unconfirmed')),
    official_source_id   INTEGER REFERENCES sources(id),
    verification_status  TEXT NOT NULL DEFAULT 'discovered' CHECK (verification_status IN
                           ('discovered','extracted','verified_official','verified_independent','needs_review',
                            'conflicting','possibly_outdated','unverified','rejected')),
    notes                TEXT NOT NULL DEFAULT '',
    UNIQUE (state, name)
);

CREATE TABLE policy_versions (
    id                   INTEGER PRIMARY KEY,
    policy_id            INTEGER NOT NULL REFERENCES policies(id) ON DELETE CASCADE,
    version_label        TEXT NOT NULL,           -- 'draft 2024-09', 'final'
    notification_ref     TEXT,
    effective_date       TEXT,
    expiry_date          TEXT,
    amendment_note       TEXT,
    source_id            INTEGER REFERENCES sources(id),
    verification_status  TEXT NOT NULL DEFAULT 'discovered' CHECK (verification_status IN
                           ('discovered','extracted','verified_official','verified_independent','needs_review',
                            'conflicting','possibly_outdated','unverified','rejected')),
    last_checked         TEXT,
    UNIQUE (policy_id, version_label)
);

CREATE TABLE incentives (
    id                   INTEGER PRIMARY KEY,
    policy_version_id    INTEGER NOT NULL REFERENCES policy_versions(id) ON DELETE CASCADE,
    benefit_type         TEXT NOT NULL,           -- capex_subsidy, payroll_subsidy, rental_subsidy, ...
    description          TEXT NOT NULL,
    amount_or_formula    TEXT,
    cap                  TEXT,
    eligibility          TEXT,
    application_process  TEXT,
    benefit_state        TEXT NOT NULL DEFAULT 'policy_provision' CHECK (benefit_state IN
                           ('policy_provision','potential_eligibility','approved','received')),
    source_id            INTEGER REFERENCES sources(id),
    claim_id             INTEGER REFERENCES claims(id),
    verification_status  TEXT NOT NULL DEFAULT 'discovered' CHECK (verification_status IN
                           ('discovered','extracted','verified_official','verified_independent','needs_review',
                            'conflicting','possibly_outdated','unverified','rejected'))
);

CREATE TABLE talent_observations (
    id                   INTEGER PRIMARY KEY,
    city_id              INTEGER REFERENCES cities(id),
    geography            TEXT NOT NULL,
    indicator            TEXT NOT NULL,           -- 'gcc_count', 'median_salary', ...
    skill_category       TEXT,
    value_num            REAL,
    unit                 TEXT,
    period_start         TEXT,
    period_end           TEXT,
    publication_date     TEXT,
    retrieval_date       TEXT,
    methodology          TEXT,
    source_id            INTEGER REFERENCES sources(id),
    claim_id             INTEGER REFERENCES claims(id),
    verification_status  TEXT NOT NULL DEFAULT 'discovered' CHECK (verification_status IN
                           ('discovered','extracted','verified_official','verified_independent','needs_review',
                            'conflicting','possibly_outdated','unverified','rejected')),
    observed_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE scrape_jobs (
    id              INTEGER PRIMARY KEY,
    source_id       INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    run_id          TEXT NOT NULL,
    stage           TEXT NOT NULL CHECK (stage IN ('fetch','extract','normalize','dedupe','validate','verify','store')),
    status          TEXT NOT NULL CHECK (status IN ('success','failed','blocked','skipped','incomplete')),
    method          TEXT,
    http_status     INTEGER,
    error           TEXT,
    content_sha256  TEXT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT
);
CREATE INDEX idx_jobs_source ON scrape_jobs(source_id);
CREATE INDEX idx_jobs_status ON scrape_jobs(status);

CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY,
    ts          TEXT NOT NULL DEFAULT (datetime('now')),
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    table_name  TEXT NOT NULL,
    record_id   INTEGER,
    detail      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_audit_table ON audit_log(table_name, record_id);
