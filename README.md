# fa25-cs411-team008-Team8
# Campus Amenities Rating – Backend + Database

This project is a campus amenities rating app for UIUC.  
It stores information about **buildings, bathrooms, water fountains, vending machines, tags, and reviews**, and exposes a REST API for use by a frontend.

This README documents the **backend + database stack we have set up so far**, including:

- Dockerized **PostgreSQL** + **FastAPI** backend
- Schema definition (`db/init.sql`)
- Data seeding script (`backend/scripts/seed_data.py`)
- The REST API endpoints currently implemented

---

## 1. Prerequisites

You need:

- **Git**
- **Docker Desktop** (running)  
  - macOS: launch Docker Desktop app and wait until it says “Docker is running”.
- A terminal (macOS Terminal / iTerm / VS Code terminal, etc.)

No local Python / venv is required — everything runs inside Docker.

---

## 2. Repository Structure (Relevant Parts)

We’re mainly working with this structure:

```bash
fa25-cs411-team008-Team8/
├── backend/
│   ├── main.py                 # FastAPI app with REST API endpoints
│   ├── requirements.txt        # Python dependencies (installed inside Docker)
│   ├── Dockerfile              # Backend container definition
│   └── scripts/
│       └── seed_data.py        # Scraper + random data seeder
│
├── db/
│   └── init.sql                # Database schema (tables, constraints, indexes)
│
├── docker-compose.yml          # Orchestrates db + backend containers
└── README.md                   # (this file)

3. Docker Services Overview

docker-compose runs 2 services:

db (PostgreSQL 16)

Internal port: 5432

Exposed as: 5433 (avoids conflicts)

Initializes using db/init.sql

backend (FastAPI + Uvicorn)

Built from backend/Dockerfile

Exposed at:
http://localhost:8000

4. Database Schema (Defined in db/init.sql)
Tables

User

Address

Building

Amenity

Review

Tag

AmenityTag

Key Features

Full relational model using foreign keys

JSONB ratingdetails field

Trigram indexes for keyword search (pg_trgm)

Unique constraint:
A user can only review an amenity once
→ (userid, amenityid) unique

5. Running the System
5.1. Terminal #1 — Start containers
cd /path/to/fa25-cs411-team008-Team8
docker compose up --build


This:

Builds backend image

Starts Postgres (amenities-db)

Starts FastAPI (amenities-backend)

Leave this terminal open — it streams logs.

5.2. Terminal #2 — For commands

Open a second terminal and cd into the repo again:

cd /path/to/fa25-cs411-team008-Team8

6. Seeding the Database

Run the seeding script inside the backend container:

docker compose exec backend python scripts/seed_data.py


This performs:

Scrape UIUC buildings

Insert buildings/addresses

Generate amenities

Insert 100 users

Insert tags

Insert 1000 reviews

Generate amenity–tag mappings

Expected final lines:

[SEED] Inserted 1000 reviews and XXXX amenity-tag pairs.
[MAIN] Data population complete 🎉

7. Verifying Data Counts

Run from Terminal #2:

docker compose exec db psql -U amen -d amenities -c "SELECT COUNT(*) FROM building;"
docker compose exec db psql -U amen -d amenities -c "SELECT COUNT(*) FROM amenity;"
docker compose exec db psql -U amen -d amenities -c "SELECT COUNT(*) FROM review;"


Typical results:

1159  -- buildings
17447 -- amenities
1000  -- reviews

8. Testing the API

Backend is at:

👉 http://localhost:8000
8.1. API alive check
curl http://localhost:8000/


Returns:

{"message":"API is running"}

9. API Endpoints
9.1. GET /amenities

List amenities, with full filtering and keyword search.

Example — first 5 amenities
curl "http://localhost:8000/amenities?limit=5"

Example — keyword search
curl "http://localhost:8000/amenities?keyword=Grainger&limit=5"

9.2. GET /amenities/{amenity_id}/reviews
curl "http://localhost:8000/amenities/10301/reviews"


Example response:

[
  {
    "reviewid": 1454,
    "userid": 172,
    "amenityid": 10301,
    "overallrating": 5.0,
    "ratingdetails": {
      "flow": 4,
      "temperature": 4,
      "filter_status": "Needs Replacement"
    },
    "timestamp": "2025-03-27T10:04:17.545992+00:00"
  }
]

9.3. POST /reviews — Create Review
curl -X POST "http://localhost:8000/reviews" \
  -H "Content-Type: application/json" \
  -d '{
        "user_id": 1,
        "amenity_id": 10573,
        "overall_rating": 4.0,
        "rating_details": {"flow": 4, "temperature": 4}
      }'


Response:

{
  "review_id": 2001,
  "timestamp": "2025-11-17T05:30:12.123456+00:00"
}

9.4. GET /reviews/{review_id} — Read Review
curl "http://localhost:8000/reviews/2001"

9.5. PUT /reviews/{review_id} — Update Review
curl -X PUT "http://localhost:8000/reviews/2001" \
  -H "Content-Type: application/json" \
  -d '{
        "overall_rating": 3.5,
        "rating_details": {"flow": 3, "temperature": 4}
      }'

9.6. DELETE /reviews/{review_id} — Delete Review
curl -X DELETE "http://localhost:8000/reviews/2001"

10. Development Workflow
Start system
docker compose up --build

Stop system

Press Ctrl + C in Terminal #1, then:

docker compose down

Rebuild after backend code changes
docker compose down
docker compose up --build

Re-seed database
docker compose exec backend python scripts/seed_data.py

Fresh DB (optional)
docker compose down
docker volume rm fa25-cs411-team008-team8_db_data
docker compose up --build

11. Next Steps (Planned — Not Yet Implemented)

These features will complete Stage 4:

✓ Stored procedure (PL/pgSQL)

Upsert review

Auto-normalize ratings

Custom logic (update timestamps, maintain stats)

✓ Trigger + helper table

Maintain rolling average rating

Maintain review counts

Update stats instantly on insert/update/delete

✓ Transactional endpoints

Endpoint that calls stored procedure

Endpoint that runs multi-step transaction

✓ Frontend (React)

Search UI

Amenity detail pages

Review submission + editing

Tag display

This README reflects the system as currently implemented and will be updated as new DB features and frontend components are added.