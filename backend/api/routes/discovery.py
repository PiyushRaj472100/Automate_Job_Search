import itertools, time
from fastapi import APIRouter
from pydantic import BaseModel
from backend.sources.registry import SOURCES

router = APIRouter(prefix="/discovery", tags=["discovery"])


class QueryReq(BaseModel):
    target_roles: list[str] = []
    skills: list[str] = []
    locations: list[str] = []
    max_queries: int = 15


class SearchReq(BaseModel):
    queries: list[str]
    sources: list[str] | None = None


@router.get("/sources")
async def sources():
    return [{"name": s.name, "policy": s.policy, "enabled": s.enabled,
             "circuit_open": s.breaker.open, "last_error": s.breaker.last_error} for s in SOURCES.values()]


@router.get("/health")
async def health():
    return {n: {"ok": await s.health_check(), "circuit_open": s.breaker.open} for n, s in SOURCES.items()}


@router.post("/generate-queries")
async def generate(req: QueryReq):
    qs = [f"{r} {s}".strip() for r, s in itertools.product(req.target_roles or [""], req.skills[:3] or [""])]
    qs = [q for q in qs if q]
    qs += [f"{r} {l}" for r in req.target_roles for l in req.locations]
    return {"queries": list(dict.fromkeys(qs))[: req.max_queries]}


@router.post("/search")
async def search(req: SearchReq):
    t0, total, ok, failed, jobs, errors = time.time(), 0, 0, 0, [], []
    for name, src in SOURCES.items():
        if (req.sources and name not in req.sources) or not src.enabled:
            continue
        if src.breaker.open:
            errors.append({"source": name, "error": "circuit_open"})
            continue
        for q in req.queries:
            total += 1
            try:
                jobs += [j.model_dump() for j in await src.discover(q)]
                src.breaker.success()
                ok += 1
            except Exception as e:
                failed += 1
                src.breaker.failure(str(e))
                errors.append({"source": name, "query": q, "error": type(e).__name__})
    seen, unique = set(), []
    for j in jobs:
        k = (j["source"], j["source_job_id"] or j["job_url"])
        if k not in seen:
            seen.add(k)
            unique.append(j)
    return {"summary": {"total_requests": total, "successful": ok, "failed": failed,
                        "duration_s": round(time.time() - t0, 2)},
            "jobs": unique, "errors": errors,
            "note": "Jobs are NOT yet URL-verified, matched or persisted (NOT IMPLEMENTED)."}
