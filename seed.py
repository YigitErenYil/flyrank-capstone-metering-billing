"""
Run inside the api container (or locally with DATABASE_URL pointed at the
running Postgres) to seed plans + one demo tenant on the Free plan.

Usage (per capstone.yaml's `seed:` command):
    docker compose exec api python seed.py
"""
from app.database import SessionLocal, Base, engine
from app.models import Plan, Tenant, Subscription
from app.config import PLAN_QUOTAS

Base.metadata.create_all(bind=engine)

db = SessionLocal()

for plan_id, quotas in PLAN_QUOTAS.items():
    existing = db.query(Plan).filter(Plan.id == plan_id).first()
    if existing:
        continue
    db.add(Plan(
        id=plan_id,
        name=plan_id.capitalize(),
        monthly_api_calls=quotas["api_calls"],
        monthly_ai_tokens=quotas["ai_tokens"],
    ))

db.commit()

demo_tenant = db.query(Tenant).filter(Tenant.name == "Demo Tenant").first()
if not demo_tenant:
    demo_tenant = Tenant(name="Demo Tenant")
    db.add(demo_tenant)
    db.commit()
    db.refresh(demo_tenant)

    db.add(Subscription(tenant_id=demo_tenant.id, plan_id="free", status="active"))
    db.commit()

print(f"Seeded. Demo tenant id: {demo_tenant.id}")

db.close()
