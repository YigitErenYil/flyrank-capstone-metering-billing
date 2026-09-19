from fastapi import FastAPI

from app.database import Base, engine
from app.routers import generate, usage

# Phase 2 note: table creation via metadata.create_all for now.
# Will move to Alembic migrations before final submission (Section 6:
# "schema as migrations").
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Usage Metering & Billing Engine")

app.include_router(generate.router, tags=["metering"])
app.include_router(usage.router, tags=["usage"])


@app.get("/health")
def health():
    return {"status": "ok"}
