from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import actors, auth, dashboard, export, health, jobs, leads
from app.core.config import settings

app = FastAPI(
    title="Argus — Threat Actor Attribution API",
    description="Dark web infrastructure, relationship, and stylometric attribution API",
    version="0.1.0",
)

# The frontend calls this API's HTTPS domain directly rather than through a
# same-origin server-side proxy, so the browser issues a real preflight
# OPTIONS request that FastAPI otherwise has no handler for (405). The
# allow_origin_regex additionally covers Vercel's per-deployment preview
# URLs for this project, not just the production alias.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()],
    allow_origin_regex=r"https://argus-frontend-[a-z0-9]+-rohans-projects-98f5ed53\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(actors.router)
app.include_router(export.router)
app.include_router(leads.router)
app.include_router(jobs.router)
app.include_router(dashboard.router)
