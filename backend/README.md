# Backend

FastAPI backend scaffold with SQLAlchemy ORM, Alembic migrations, and demo seed data.

## Commands

```bash
pip install -e .[dev]
alembic upgrade head
python scripts/seed_demo_data.py
uvicorn app.main:app --reload
```
