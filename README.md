# Asset Management System

Week 1 foundation for the Asset Management System course project. This repository now includes:

- `backend/`: FastAPI app scaffold, SQLAlchemy models, Alembic migrations, and demo seed script
- `frontend/`: React + Vite monorepo frontend shell
- `docs/`: requirements, roadmap, and design references

## Repository layout

```text
.
├── backend
│   ├── alembic
│   ├── app
│   └── scripts
├── frontend
│   ├── public
│   └── src
└── docs
```

## Quick start

### 0. Start MySQL

```bash
docker compose up -d mysql
```

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
alembic upgrade head
python scripts/seed_demo_data.py
uvicorn app.main:app --reload
```

FastAPI docs will be available at `http://localhost:8000/docs`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend dev server defaults to `http://localhost:5173`.

## Environment

Backend defaults are stored in [backend/.env.example](/Users/jnes0/cloud_native/Asset-Management-System/backend/.env.example:1).
Update `DATABASE_URL` to point to your local MySQL instance before running migrations or seed data.
If you use the bundled [docker-compose.yml](/Users/jnes0/cloud_native/Asset-Management-System/docker-compose.yml:1),
the default `DATABASE_URL` already matches the container settings.
