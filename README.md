# fa25-cs411-team008-Team8
# Campus Amenities Rating – Full Stack Application

This project is a campus amenities rating app for UIUC.  
It stores information about **buildings, bathrooms, water fountains, vending machines, tags, and reviews**, and provides both a REST API backend and an interactive React frontend with map visualization.

This README documents the **complete full-stack application**, including:

- Dockerized **PostgreSQL** + **FastAPI** backend
- **React** frontend with **Leaflet** interactive map
- Schema definition (`db/init.sql`)
- Data seeding script (`backend/scripts/seed_data.py`)
- Complete REST API endpoints
- Interactive map features and leaderboards

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
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # Main React component with map and UI
│   │   ├── App.css             # Component styles
│   │   ├── main.jsx            # React entry point
│   │   └── index.css            # Global styles
│   ├── package.json            # Node.js dependencies
│   └── vite.config.js          # Vite build configuration
│
├── db/
│   └── init.sql                # Database schema (tables, constraints, indexes, stored procedures)
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

9.7. POST /reviews/upsert — Upsert Review (via Stored Procedure)
curl -X POST "http://localhost:8000/reviews/upsert" \
  -H "Content-Type: application/json" \
  -d '{
        "user_id": 1,
        "amenity_id": 10573,
        "overall_rating": 4.5,
        "rating_details": {"flow": 4, "temperature": 5}
      }'

9.8. GET /leaderboard/clean-bathrooms-vending — Top 15 Buildings with Clean Bathrooms + Vending
Returns buildings that have both highly-rated bathrooms and vending machines.
curl "http://localhost:8000/leaderboard/clean-bathrooms-vending"

9.9. GET /leaderboard/coldest-fountains — Top 15 Coldest Water Fountains
Returns water fountains ranked by cold water tag count and average rating.
curl "http://localhost:8000/leaderboard/coldest-fountains"

9.10. GET /leaderboard/overall-amenities — Top 15 Overall Amenities
Returns the highest-rated amenities across all types, sorted by rating and review count.
curl "http://localhost:8000/leaderboard/overall-amenities"

10. Frontend Application

The frontend is a React application built with Vite and uses Leaflet for interactive map visualization.

10.1. Running the Frontend

From the `frontend/` directory:

```bash
cd frontend
npm install          # First time only
npm run dev          # Start development server
```

The frontend will be available at `http://localhost:5173` (or the port Vite assigns).

10.2. Frontend Features

**Interactive Map (Leaflet)**
- Real-time map visualization of all amenities in Champaign-Urbana
- Color-coded markers by amenity type:
  - 🔵 Blue: Water Fountains
  - 🟣 Purple: Bathrooms
  - 🟠 Orange: Vending Machines
- Click markers to view detailed information
- Map legend overlay in upper-right corner

**Search Functionality**
- Keyword search across building names, addresses, and amenity notes
- Real-time filtering of map markers
- Search bar located at the top of the sidebar

**Amenity Details Panel**
- Displays when an amenity marker is clicked
- Shows building name, address, floor, and notes
- Community rating display with star visualization
- Review count and average rating

**Rating Submission**
- Interactive 5-star rating system
- Submit ratings directly from the map interface
- Real-time feedback on submission status
- Ratings are stored via POST /reviews endpoint

**Leaderboard System**
- Accessible via "🏆 Leaderboard" button below search bar
- Three interactive tabs:
  1. Clean Bathrooms + Vending: Top 15 buildings with highly-rated bathrooms that also have vending machines
  2. Coldest Fountains: Top 15 water fountains ranked by cold water tags and ratings
  3. Overall Top Amenities: Top 15 amenities across all types by rating and review count
- Lazy-loaded data (fetches when tab is first opened)
- Ranked display (#1-#15) with detailed information

**Responsive Design**
- Optimized for desktop and mobile viewports
- No-scroll layout that fits within viewport at 100% zoom
- Mobile-friendly popup modals and navigation

10.3. Frontend Technology Stack

- React 19.2.0
- Vite 7.2.2 (build tool)
- Leaflet 1.9.4 (map library)
- Modern CSS with flexbox and responsive design

11. Advanced Database Features

11.1. Stored Procedures

✓ `sp_upsert_review` — Upsert review logic
- Automatically updates existing reviews or inserts new ones
- Called via POST /reviews/upsert endpoint
- Implements IF/ELSE control structures

11.2. Constraints

✓ CHECK constraints on rating values (0-5)
✓ CHECK constraints on amenity types
✓ UNIQUE constraint: One review per user per amenity
✓ Foreign key relationships across all tables

11.3. Advanced SQL Queries

The leaderboard endpoints implement complex SQL queries including:
- Multi-table JOINs with subqueries
- Aggregations (AVG, COUNT)
- GROUP BY and ORDER BY with multiple criteria
- Filtering by amenity types and tags

12. API Integration

The frontend communicates with the backend API using:
- Base URL: `http://localhost:8000` (configurable via `VITE_API_BASE` environment variable)
- CORS enabled for local development
- JSON request/response format

13. Development Workflow

13.1. Start Backend System
```bash
docker compose up --build
```

13.2. Start Frontend (Separate Terminal)
```bash
cd frontend
npm run dev
```

13.3. Stop System

Press Ctrl + C in backend terminal, then:
```bash
docker compose down
```

13.4. Rebuild After Backend Code Changes
```bash
docker compose down
docker compose up --build
```

13.5. Re-seed Database
```bash
docker compose exec backend python scripts/seed_data.py
```

13.6. Fresh DB (Optional)
```bash
docker compose down
docker volume rm fa25-cs411-team008-team8_db_data
docker compose up --build
```

13.7. Frontend Build for Production
```bash
cd frontend
npm run build
```

Built files will be in `frontend/dist/` directory.

14. Project Status

✅ **Completed Features:**

- Full CRUD operations for Reviews (Create, Read, Update, Delete)
- Keyword search across buildings, addresses, and amenity notes
- Advanced SQL queries with complex JOINs and aggregations
- Stored procedure for review upsert operations
- Database constraints (CHECK, UNIQUE, Foreign Keys)
- React frontend with interactive Leaflet map
- Real-time search and filtering
- Interactive rating submission system
- Leaderboard system with three categories
- Responsive design for desktop and mobile
- Map legend overlay
- Amenity detail panels with community ratings
