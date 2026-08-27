from fastapi import FastAPI

from app.api.routes import actors, auth, export, health, jobs, leads

app = FastAPI(
    title="SIH26151 Dark Web Threat Actor De-anonymization",
    description="NTRO problem statement 26151 prototype API",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(actors.router)
app.include_router(export.router)
app.include_router(leads.router)
app.include_router(jobs.router)
