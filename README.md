# Quotation-to-Invoice API

FastAPI · PostgreSQL · SQLAlchemy (async) · JWT Authentication

## Quick Start

```bash
# 1. Clone & enter project
cd quotation_invoice

# 2. Create virtual environment
python -m venv .venv && source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env   # then edit .env with your values

# 5. Run migrations
alembic upgrade head

# 6. Start server
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

## Project Structure

```
quotation_invoice/
├── app/
│   ├── main.py            # App factory + lifespan
│   ├── config.py          # Pydantic settings (reads .env)
│   ├── database.py        # Async engine, session, Base
│   ├── models/            # SQLAlchemy ORM models
│   ├── schemas/           # Pydantic request/response schemas
│   ├── routers/           # FastAPI route handlers
│   ├── services/          # Business logic layer
│   ├── middleware/        # Auth dependency (JWT validation)
│   └── utils/             # Shared helpers (security, pagination…)
├── alembic/               # DB migrations
├── tests/                 # Pytest test suite
├── .env.example
├── alembic.ini
└── requirements.txt
```

## API Modules (v1)

| Prefix                  | Description                            |
|-------------------------|----------------------------------------|
| `/api/v1/auth`          | Login, token refresh, register         |
| `/api/v1/users`         | User management                        |
| `/api/v1/clients`       | Client/customer records                |
| `/api/v1/quotations`    | Create, approve, reject quotations     |
| `/api/v1/invoices`      | Convert quotations → invoices, payment |
