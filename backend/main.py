from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
import os
import psycopg2
from psycopg2.extras import RealDictCursor, Json

# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgres://amen:amenities@db:5432/amenities"
)


def get_conn():
    """
    Open a new database connection using RealDictCursor so we get dict-like rows.
    """
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


# Pydantic models for request bodies
class ReviewCreate(BaseModel):
    user_id: int
    amenity_id: int
    overall_rating: float = Field(ge=0, le=5)
    rating_details: dict


class ReviewUpdate(BaseModel):
    overall_rating: Optional[float] = Field(default=None, ge=0, le=5)
    rating_details: Optional[dict] = None


app = FastAPI(title="Campus Amenities API", version="0.1.0")

# CORS for frontend (for now allow all; you can tighten later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # in prod, set to your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "API is running"}


# -------------------------------------------------------
# GET /amenities  - list amenities with optional filters
# -------------------------------------------------------
@app.get("/amenities")
def list_amenities(
    keyword: Optional[str] = Query(
        default=None,
        description="Search across building name, address, and amenity notes.",
    ),
    amenity_type: Optional[str] = Query(
        default=None,
        description="Filter by amenity type: Bathroom, WaterFountain, VendingMachine.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """
    List amenities with optional keyword search and type filter.
    Returns building name, address, amenity info, and average rating.
    """
    conn = get_conn()
    cur = conn.cursor()

    # Base SELECT/JOIN part
    query = """
        SELECT
            a.amenityid,
            a.type,
            a.floor,
            a.notes,
            b.name      AS building_name,
            ad.address  AS address,
            COALESCE(AVG(r.overallrating), 0) AS avg_rating,
            COUNT(r.reviewid)                 AS review_count
        FROM amenity a
        JOIN building b ON a.buildingid = b.buildingid
        JOIN address ad ON b.addressid = ad.addressid
        LEFT JOIN review r ON r.amenityid = a.amenityid
    """

    # Dynamic WHERE conditions
    where_clauses = []
    params: List = []

    # Type filter
    if amenity_type:
        where_clauses.append("a.type = %s")
        params.append(amenity_type)

    # Keyword filter — using %...% in params instead of concatenation
    if keyword:
        kw = f"%{keyword.strip()}%"
        where_clauses.append(
            "(b.name ILIKE %s OR ad.address ILIKE %s OR a.notes ILIKE %s)"
        )
        params.extend([kw, kw, kw])

    # Attach WHERE clause if we have any conditions
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    # GROUP BY, ORDER, LIMIT/OFFSET
    query += """
        GROUP BY
            a.amenityid,
            a.type,
            a.floor,
            a.notes,
            b.name,
            ad.address
        ORDER BY
            avg_rating DESC,
            review_count DESC,
            a.amenityid ASC
        LIMIT %s
        OFFSET %s
    """

    # Add limit/offset params at the end
    params.extend([limit, offset])

    try:
        cur.execute(query, params)
        rows = cur.fetchall()
        return rows
    except psycopg2.Error as e:
        # This will give you a clear DB error instead of a generic 500
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()



# ----------------------------------------------------------------
# GET /amenities/{amenity_id}/reviews - list reviews for an amenity
# ----------------------------------------------------------------
@app.get("/amenities/{amenity_id}/reviews")
def get_reviews_for_amenity(amenity_id: int):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
                reviewid,
                userid,
                amenityid,
                overallrating,
                ratingdetails,
                timestamp
            FROM review
            WHERE amenityid = %s
            ORDER BY timestamp DESC
            """,
            (amenity_id,),
        )
        rows = cur.fetchall()
        return rows
    finally:
        conn.close()


# ---------------------------------
# POST /reviews - Create a review
# ---------------------------------
@app.post("/reviews")
def create_review(review: ReviewCreate):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO review (userid, amenityid, overallrating, ratingdetails)
            VALUES (%s, %s, %s, %s)
            RETURNING reviewid, timestamp
            """,
            (
                review.user_id,
                review.amenity_id,
                review.overall_rating,
                Json(review.rating_details),
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return {
            "review_id": row["reviewid"],
            "timestamp": row["timestamp"],
        }
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


# ----------------------------------------
# GET /reviews/{review_id} - Read a review
# ----------------------------------------
@app.get("/reviews/{review_id}")
def get_review(review_id: int):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
                reviewid,
                userid,
                amenityid,
                overallrating,
                ratingdetails,
                timestamp
            FROM review
            WHERE reviewid = %s
            """,
            (review_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Review not found")
        return row
    finally:
        conn.close()


# -----------------------------------------
# PUT /reviews/{review_id} - Update review
# -----------------------------------------
@app.put("/reviews/{review_id}")
def update_review(review_id: int, update: ReviewUpdate):
    conn = get_conn()
    cur = conn.cursor()
    try:
        set_clauses = []
        params: List = []

        if update.overall_rating is not None:
            set_clauses.append("overallrating = %s")
            params.append(update.overall_rating)

        if update.rating_details is not None:
            set_clauses.append("ratingdetails = %s")
            params.append(Json(update.rating_details))

        if not set_clauses:
            raise HTTPException(
                status_code=400, detail="No fields provided to update"
            )

        params.append(review_id)
        query = f"""
            UPDATE review
            SET {", ".join(set_clauses)}
            WHERE reviewid = %s
            RETURNING
                reviewid,
                userid,
                amenityid,
                overallrating,
                ratingdetails,
                timestamp
        """

        cur.execute(query, params)
        row = cur.fetchone()
        if not row:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Review not found")

        conn.commit()
        return row
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


# --------------------------------------------
# DELETE /reviews/{review_id} - Delete review
# --------------------------------------------
@app.delete("/reviews/{review_id}")
def delete_review(review_id: int):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            DELETE FROM review
            WHERE reviewid = %s
            RETURNING reviewid
            """,
            (review_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Review not found")

        conn.commit()
        return {"deleted_review_id": row["reviewid"]}
    finally:
        conn.close()
