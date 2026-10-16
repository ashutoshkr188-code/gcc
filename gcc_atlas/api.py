"""HTTP API and static web UI. Run: python -m gcc_atlas.cli serve"""
import os
import secrets
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import assistant, quality, readiness
from . import repository as repo
from .db import DEFAULT_DB, STATUSES, connect, transaction
from .verify import ReviewError, review

WEB = Path(__file__).resolve().parent.parent / "web"
Status = Literal[STATUSES]
SearchText = Annotated[str | None, Query(max_length=100)]

app = FastAPI(title="GCC Atlas API", version="1.0.0")


def get_conn():
    # FastAPI may run a sync dependency's setup and teardown on different worker threads.
    # The connection is still used by one request at a time.
    conn = connect(os.environ.get("GCC_ATLAS_DB"), check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


Conn = Annotated[object, Depends(get_conn)]


def _city(conn, name):
    if name is not None and name not in repo.city_names(conn):
        raise HTTPException(422, f"unknown city '{name}'. Valid: {', '.join(repo.city_names(conn))}")
    return name


def _found(obj, what):
    if obj is None:
        raise HTTPException(404, f"{what} not found")
    return obj


@app.get("/api/health")
def health(conn: Conn):
    conn.execute("SELECT 1")
    return {"ok": True}


@app.get("/api/overview")
def overview(conn: Conn):
    return repo.overview(conn)


@app.get("/api/cities")
def cities(conn: Conn):
    return repo.list_cities(conn)


@app.get("/api/cities/compare")
def compare(conn: Conn, cities: Annotated[list[str], Query(min_length=2, max_length=6)]):
    if len(set(cities)) != len(cities):
        raise HTTPException(422, "cities must be distinct")
    for c in cities:
        _city(conn, c)
    return repo.compare_cities(conn, cities)


@app.get("/api/companies")
def companies(conn: Conn, q: SearchText = None, industry: SearchText = None, city: SearchText = None):
    return repo.search_companies(conn, q, industry, _city(conn, city))


@app.get("/api/industries")
def industries(conn: Conn):
    return repo.industries(conn)


@app.get("/api/companies/{slug}")
def company(conn: Conn, slug: Annotated[str, Field(max_length=80)]):
    return _found(repo.company_profile(conn, slug), "company")


@app.get("/api/companies/{slug}/structure")
def structure(conn: Conn, slug: str):
    return _found(repo.company_structure(conn, slug), "company")


@app.get("/api/groups")
def groups(conn: Conn):
    return repo.groups_overview(conn)


@app.get("/api/centres")
def centres(conn: Conn, q: SearchText = None, city: SearchText = None,
            status: Literal["operating", "announced", "general_office", "unverified_lead", "closed"] | None = None,
            verification: Status | None = None, industry: SearchText = None):
    return repo.search_centres(conn, q, _city(conn, city), status, verification, industry)


@app.get("/api/costs")
def costs(conn: Conn, city: SearchText = None, category: SearchText = None,
          stage: Literal["setup", "recurring"] | None = None, verified_only: bool = False):
    return repo.cost_observations(conn, _city(conn, city), category, stage, verified_only)


@app.get("/api/policies")
def policies(conn: Conn, state: SearchText = None,
             kind: Literal["state_incentive_policy", "regulation", "scheme"] | None = None):
    return repo.list_policies(conn, state, kind)


@app.get("/api/policies/{policy_id}")
def policy(conn: Conn, policy_id: int):
    return _found(repo.policy_detail(conn, policy_id), "policy")


@app.get("/api/sources")
def sources(conn: Conn,
            status: Literal["not_attempted", "retrieved", "http_error", "network_blocked", "failed"] | None = None,
            tier: Annotated[int | None, Query(ge=1, le=7)] = None):
    return repo.list_sources(conn, status, tier)


@app.get("/api/sources/{key}")
def source(conn: Conn, key: str):
    return _found(repo.source_detail(conn, key), "source")


@app.get("/api/claims")
def claims(conn: Conn, status: Status | None = None,
           subject_type: Literal["company", "gcc_centre", "entity", "relationship", "policy", "policy_version",
                                 "incentive", "cost_observation", "talent_observation", "city"] | None = None):
    return repo.list_claims(conn, status, subject_type)


@app.get("/api/claims/{claim_id}")
def claim(conn: Conn, claim_id: int):
    return _found(repo.claim_detail(conn, claim_id), "claim")


class ReviewIn(BaseModel):
    status: Status
    reviewer: str = Field(min_length=2, max_length=80)
    note: str = Field(default="", max_length=1000)
    operational_status: Literal["operating", "announced", "general_office", "closed"] | None = None


@app.post("/api/claims/{claim_id}/review")
def review_claim(conn: Conn, claim_id: int, body: ReviewIn, x_review_token: Annotated[str | None, Header()] = None):
    expected = os.environ.get("GCC_ATLAS_REVIEW_TOKEN")
    if not expected:
        raise HTTPException(403, "reviews over the API are disabled (GCC_ATLAS_REVIEW_TOKEN not set)")
    if not x_review_token or not secrets.compare_digest(x_review_token, expected):
        raise HTTPException(401, "invalid review token")
    try:
        with transaction(conn):
            review(conn, claim_id, body.status, body.reviewer, body.note, body.operational_status)
    except ReviewError as e:
        raise HTTPException(409 if "not found" not in str(e) else 404, str(e))
    return repo.claim_detail(conn, claim_id)


@app.get("/api/verification/summary")
def verification_summary(conn: Conn):
    return repo.verification_summary(conn)


@app.get("/api/quality")
def data_quality(conn: Conn):
    return quality.run_all(conn)


@app.get("/api/readiness")
def data_readiness(conn: Conn):
    return {"metrics": readiness.metrics(conn),
            "gate": [{"criterion": n, "pass": ok, "evidence": ev} for n, ok, ev in readiness.gate(conn)]}


class ResearchIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@app.post("/api/research")
def research(conn: Conn, body: ResearchIn):
    return assistant.answer(conn, body.question)


if WEB.exists():
    app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB / "index.html")
