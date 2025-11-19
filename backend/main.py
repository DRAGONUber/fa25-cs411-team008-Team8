from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
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


# -------------------------------------------------
# Pydantic models for request bodies
# -------------------------------------------------

class ReviewCreate(BaseModel):
    user_id: int
    amenity_id: int
    overall_rating: float = Field(ge=0, le=5)
    rating_details: dict


class ReviewUpdate(BaseModel):
    overall_rating: Optional[float] = Field(default=None, ge=0, le=5)
    rating_details: Optional[dict] = None


class UserCreate(BaseModel):
    username: str = Field(..., max_length=255)
    email: EmailStr


class UserUpdate(BaseModel):
    username: Optional[str] = Field(default=None, max_length=255)
    email: Optional[EmailStr] = None


class BuildingCreate(BaseModel):
    name: str = Field(..., max_length=255)
    address_id: int


class BuildingWithAddressCreate(BaseModel):
    name: str = Field(..., max_length=255)
    address: str = Field(..., max_length=255)
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class BuildingUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    address_id: Optional[int] = None


class AmenityCreate(BaseModel):
    building_id: int
    type: str = Field(..., max_length=40)
    floor: str = Field(..., max_length=20)
    notes: Optional[str] = None


class AmenityUpdate(BaseModel):
    building_id: Optional[int] = None
    type: Optional[str] = Field(default=None, max_length=40)
    floor: Optional[str] = Field(default=None, max_length=20)
    notes: Optional[str] = None


class TagCreate(BaseModel):
    label: str = Field(..., max_length=40)


class TagUpdate(BaseModel):
    label: Optional[str] = Field(default=None, max_length=40)


class AmenityTagCreate(BaseModel):
    tag_id: int


# -------------------------------------------------
# FastAPI app + CORS
# -------------------------------------------------

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
    limit: int = Query(default=50, ge=1, le=1500),
    offset: int = Query(default=0, ge=0),
):
    """
    List amenities with optional keyword search and type filter.
    Returns building name, address, amenity info, and average rating.
    """
    conn = get_conn()
    cur = conn.cursor()

    query = """
        SELECT
            a.amenityid,
            a.buildingid,
            a.type,
            a.floor,
            a.notes,
            b.name      AS building_name,
            ad.address  AS address,
            ad.lat,
            ad.lon,
            COALESCE(AVG(r.overallrating), 0) AS avg_rating,
            COUNT(r.reviewid)                 AS review_count
        FROM amenity a
        JOIN building b ON a.buildingid = b.buildingid
        JOIN address ad ON b.addressid = ad.addressid
        LEFT JOIN review r ON r.amenityid = a.amenityid
    """

    where_clauses = []
    params: List = []

    if amenity_type:
        where_clauses.append("a.type = %s")
        params.append(amenity_type)

    if keyword:
        kw = f"%{keyword.strip()}%"
        where_clauses.append(
            "(b.name ILIKE %s OR ad.address ILIKE %s OR a.notes ILIKE %s)"
        )
        params.extend([kw, kw, kw])

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    query += """
        GROUP BY
            a.amenityid,
            a.buildingid,
            a.type,
            a.floor,
            a.notes,
            b.buildingid,
            b.name,
            ad.address,
            ad.lat,
            ad.lon
        ORDER BY
            avg_rating DESC,
            review_count DESC,
            a.amenityid ASC
        LIMIT %s
        OFFSET %s
    """

    params.extend([limit, offset])

    try:
        cur.execute(query, params)
        rows = cur.fetchall()
        return rows
    except psycopg2.Error as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


# -------------------------------------------------------
# GET /amenities/{amenity_id} - single amenity details
# -------------------------------------------------------
@app.get("/amenities/{amenity_id}")
def get_amenity(amenity_id: int):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
                a.amenityid,
                a.buildingid,
                a.type,
                a.floor,
                a.notes,
                b.name      AS building_name,
                ad.address  AS address,
                ad.lat,
                ad.lon
            FROM amenity a
            JOIN building b ON a.buildingid = b.buildingid
            JOIN address ad ON b.addressid = ad.addressid
            WHERE a.amenityid = %s
            """,
            (amenity_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Amenity not found")
        return row
    finally:
        conn.close()


# ---------------------------------
# POST /amenities - Create amenity
# ---------------------------------
@app.post("/amenities")
def create_amenity(payload: AmenityCreate):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO amenity (buildingid, type, floor, notes)
            VALUES (%s, %s, %s, %s)
            RETURNING amenityid, buildingid, type, floor, notes
            """,
            (payload.building_id, payload.type, payload.floor, payload.notes),
        )
        row = cur.fetchone()
        conn.commit()
        return row
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


# -----------------------------------------
# PUT /amenities/{amenity_id} - Update amenity
# -----------------------------------------
@app.put("/amenities/{amenity_id}")
def update_amenity(amenity_id: int, payload: AmenityUpdate):
    conn = get_conn()
    cur = conn.cursor()
    try:
        set_clauses = []
        params: List = []

        if payload.building_id is not None:
            set_clauses.append("buildingid = %s")
            params.append(payload.building_id)
        if payload.type is not None:
            set_clauses.append("type = %s")
            params.append(payload.type)
        if payload.floor is not None:
            set_clauses.append("floor = %s")
            params.append(payload.floor)
        if payload.notes is not None:
            set_clauses.append("notes = %s")
            params.append(payload.notes)

        if not set_clauses:
            raise HTTPException(status_code=400, detail="No fields provided to update")

        params.append(amenity_id)
        query = f"""
            UPDATE amenity
            SET {", ".join(set_clauses)}
            WHERE amenityid = %s
            RETURNING amenityid, buildingid, type, floor, notes
        """

        cur.execute(query, params)
        row = cur.fetchone()
        if not row:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Amenity not found")

        conn.commit()
        return row
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


# --------------------------------------------
# DELETE /amenities/{amenity_id} - Delete amenity
# --------------------------------------------
@app.delete("/amenities/{amenity_id}")
def delete_amenity(amenity_id: int):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            DELETE FROM amenity
            WHERE amenityid = %s
            RETURNING amenityid
            """,
            (amenity_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Amenity not found")

        conn.commit()
        return {"deleted_amenity_id": row["amenityid"]}
    finally:
        conn.close()


# ----------------------------------------------------------------
# GET /amenities/{amenity_id}/reviews - list reviews for amenity
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


# -----------------------------------------------
# POST /reviews/upsert - Call stored procedure
# -----------------------------------------------
@app.post("/reviews/upsert")
def upsert_review(review: ReviewCreate):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "CALL sp_upsert_review(%s, %s, %s, %s)",
            (
                review.user_id,
                review.amenity_id,
                review.overall_rating,
                Json(review.rating_details),
            ),
        )
        conn.commit()
        return {"message": "Review upserted successfully"}
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


# -----------------------------------------
# USER CRUD
# -----------------------------------------

@app.post("/users")
def create_user(user: UserCreate):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO "User" (UserName, Email)
            VALUES (%s, %s)
            RETURNING UserId, UserName, Email, JoinDate
            """,
            (user.username, user.email),
        )
        row = cur.fetchone()
        conn.commit()
        return row
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.get("/users")
def list_users(limit: int = Query(default=50, ge=1, le=500), offset: int = Query(0, ge=0)):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT UserId, UserName, Email, JoinDate
            FROM "User"
            ORDER BY UserId
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        rows = cur.fetchall()
        return rows
    finally:
        conn.close()


@app.get("/users/{user_id}")
def get_user(user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT UserId, UserName, Email, JoinDate
            FROM "User"
            WHERE UserId = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return row
    finally:
        conn.close()


@app.put("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate):
    conn = get_conn()
    cur = conn.cursor()
    try:
        set_clauses = []
        params: List = []

        if payload.username is not None:
            set_clauses.append("UserName = %s")
            params.append(payload.username)
        if payload.email is not None:
            set_clauses.append("Email = %s")
            params.append(payload.email)

        if not set_clauses:
            raise HTTPException(status_code=400, detail="No fields provided to update")

        params.append(user_id)
        query = f"""
            UPDATE "User"
            SET {", ".join(set_clauses)}
            WHERE UserId = %s
            RETURNING UserId, UserName, Email, JoinDate
        """

        cur.execute(query, params)
        row = cur.fetchone()
        if not row:
            conn.rollback()
            raise HTTPException(status_code=404, detail="User not found")

        conn.commit()
        return row
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.delete("/users/{user_id}")
def delete_user(user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            DELETE FROM "User"
            WHERE UserId = %s
            RETURNING UserId
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            raise HTTPException(status_code=404, detail="User not found")

        conn.commit()
        return {"deleted_user_id": row["userid"]}
    finally:
        conn.close()


# -----------------------------------------
# BUILDING CRUD
# -----------------------------------------

@app.get("/buildings")
def list_buildings(limit: int = Query(default=200, ge=1, le=2000), offset: int = Query(0, ge=0)):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
                b.buildingid,
                b.name,
                ad.address,
                ad.lat,
                ad.lon
            FROM building b
            JOIN address ad ON b.addressid = ad.addressid
            ORDER BY b.name
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        rows = cur.fetchall()
        return rows
    finally:
        conn.close()


@app.get("/buildings/{building_id}")
def get_building(building_id: int):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
                b.buildingid,
                b.name,
                ad.address,
                ad.lat,
                ad.lon
            FROM building b
            JOIN address ad ON b.addressid = ad.addressid
            WHERE b.buildingid = %s
            """,
            (building_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Building not found")
        return row
    finally:
        conn.close()


@app.post("/buildings")
def create_building(payload: BuildingCreate):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO building (name, addressid)
            VALUES (%s, %s)
            RETURNING buildingid, name, addressid
            """,
            (payload.name, payload.address_id),
        )
        row = cur.fetchone()
        conn.commit()
        return row
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.put("/buildings/{building_id}")
def update_building(building_id: int, payload: BuildingUpdate):
    conn = get_conn()
    cur = conn.cursor()
    try:
        set_clauses = []
        params: List = []

        if payload.name is not None:
            set_clauses.append("name = %s")
            params.append(payload.name)
        if payload.address_id is not None:
            set_clauses.append("addressid = %s")
            params.append(payload.address_id)

        if not set_clauses:
            raise HTTPException(status_code=400, detail="No fields provided to update")

        params.append(building_id)
        query = f"""
            UPDATE building
            SET {", ".join(set_clauses)}
            WHERE buildingid = %s
            RETURNING buildingid, name, addressid
        """

        cur.execute(query, params)
        row = cur.fetchone()
        if not row:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Building not found")

        conn.commit()
        return row
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.delete("/buildings/{building_id}")
def delete_building(building_id: int):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            DELETE FROM building
            WHERE buildingid = %s
            RETURNING buildingid
            """,
            (building_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Building not found")

        conn.commit()
        return {"deleted_building_id": row["buildingid"]}
    finally:
        conn.close()


# -----------------------------------------
# TAG CRUD
# -----------------------------------------

@app.post("/tags")
def create_tag(payload: TagCreate):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO tag (label)
            VALUES (%s)
            RETURNING tagid, label
            """,
            (payload.label,),
        )
        row = cur.fetchone()
        conn.commit()
        return row
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.get("/tags")
def list_tags():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT tagid, label
            FROM tag
            ORDER BY label
            """
        )
        rows = cur.fetchall()
        return rows
    finally:
        conn.close()


@app.put("/tags/{tag_id}")
def update_tag(tag_id: int, payload: TagUpdate):
    conn = get_conn()
    cur = conn.cursor()
    try:
        if payload.label is None:
            raise HTTPException(status_code=400, detail="No fields provided to update")

        cur.execute(
            """
            UPDATE tag
            SET label = %s
            WHERE tagid = %s
            RETURNING tagid, label
            """,
            (payload.label, tag_id),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Tag not found")

        conn.commit()
        return row
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.delete("/tags/{tag_id}")
def delete_tag(tag_id: int):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            DELETE FROM tag
            WHERE tagid = %s
            RETURNING tagid
            """,
            (tag_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Tag not found")

        conn.commit()
        return {"deleted_tag_id": row["tagid"]}
    finally:
        conn.close()


# -----------------------------------------
# AMENITY-TAG RELATION (AmenityTag)
# -----------------------------------------

@app.post("/amenities/{amenity_id}/tags")
def attach_tag_to_amenity(amenity_id: int, payload: AmenityTagCreate):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO amenitytag (amenityid, tagid)
            VALUES (%s, %s)
            ON CONFLICT (amenityid, tagid) DO NOTHING
            RETURNING amenityid, tagid
            """,
            (amenity_id, payload.tag_id),
        )
        row = cur.fetchone()
        conn.commit()
        # If row is None, it already existed
        if not row:
            return {"message": "Tag already attached to amenity"}
        return row
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.delete("/amenities/{amenity_id}/tags/{tag_id}")
def detach_tag_from_amenity(amenity_id: int, tag_id: int):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            DELETE FROM amenitytag
            WHERE amenityid = %s AND tagid = %s
            RETURNING amenityid, tagid
            """,
            (amenity_id, tag_id),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Amenity-tag relationship not found")

        conn.commit()
        return {"removed_amenity_id": row["amenityid"], "removed_tag_id": row["tagid"]}
    finally:
        conn.close()


# ----------------------------------------------------------------
# Leaderboard Endpoints - Advanced SQL Queries
# ----------------------------------------------------------------

@app.get("/leaderboard/clean-bathrooms-vending")
def leaderboard_clean_bathrooms_vending():
    """
    Query 1: Top 15 Buildings for Clean Bathrooms AND a Vending Machine
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        query = """
            SELECT
                B.Name AS building_name,
                A.Type AS amenity_type,
                ROUND(CAST(AVG(R.OverallRating) AS NUMERIC), 2) AS avg_bathroom_rating,
                A_D.Address AS address
            FROM Building B
            JOIN Amenity A ON B.BuildingId = A.BuildingId
            JOIN Review R ON A.AmenityId = R.AmenityId
            JOIN Address A_D ON B.AddressId = A_D.AddressId
            JOIN Amenity A2 ON A2.BuildingId = B.BuildingId AND A2.Type = 'VendingMachine'
            WHERE A.Type = 'Bathroom'
            GROUP BY B.Name, A.Type, A_D.Address
            ORDER BY Avg_Bathroom_Rating DESC
            LIMIT 15
        """
        cur.execute(query)
        rows = cur.fetchall()
        return rows
    except psycopg2.Error as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.get("/leaderboard/coldest-fountains")
def leaderboard_coldest_fountains():
    """
    Query 2: Coldest Water Fountain Ranking - Top 15 Fountains
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        query = """
            SELECT
                B.Name AS building_name,
                A.Floor AS floor,
                A.Notes AS notes,
                ROUND(CAST(AVG(R.OverallRating) AS NUMERIC), 2) AS avg_rating,
                CT.Cold_Tag_Count AS cold_tag_count
            FROM Building B
            JOIN Amenity A ON B.BuildingId = A.BuildingId
            JOIN Review R ON A.AmenityId = R.AmenityId
            JOIN (
                SELECT A2.AmenityId, COUNT(AT.TagId) AS Cold_Tag_Count
                FROM Amenity A2
                JOIN AmenityTag AT ON A2.AmenityId = AT.AmenityId
                JOIN Tag T ON AT.TagId = T.TagId
                WHERE A2.Type = 'WaterFountain' AND T.Label = 'ColdWater'
                GROUP BY A2.AmenityId
            ) AS CT ON A.AmenityId = CT.AmenityId
            GROUP BY B.Name, A.Floor, A.Notes, CT.Cold_Tag_Count
            ORDER BY CT.Cold_Tag_Count DESC, Avg_Rating DESC
            LIMIT 15
        """
        cur.execute(query)
        rows = cur.fetchall()
        return rows
    except psycopg2.Error as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.get("/leaderboard/overall-amenities")
def leaderboard_overall_amenities():
    """
    Query 4: Overall Amenity Ranking by Rating (Top 15)
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        query = """
            SELECT
                B.Name AS building_name,
                A.Type AS type,
                A.Floor AS floor,
                ROUND(CAST(AVG(R.OverallRating) AS NUMERIC), 2) AS avg_rating,
                COUNT(R.ReviewId) AS review_count
            FROM Building B
            JOIN Amenity A ON B.BuildingId = A.BuildingId
            JOIN Review R ON A.AmenityId = R.AmenityId
            GROUP BY B.Name, A.Type, A.Floor
            ORDER BY Avg_Rating DESC, Review_Count DESC
            LIMIT 15
        """
        cur.execute(query)
        rows = cur.fetchall()
        return rows
    except psycopg2.Error as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()



class AmenityWithTagsCreate(BaseModel):
    building_id: int
    type: str = Field(..., max_length=40)
    floor: str = Field(..., max_length=20)
    notes: Optional[str] = None
    tag_ids: List[int] = Field(default=[], description="List of tag IDs to attach")


@app.post("/amenities/with-tags")
def create_amenity_with_tags(payload: AmenityWithTagsCreate):
    
    conn = get_conn()
    cur = conn.cursor()
    
    # Set transaction isolation level
    cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
    
    try:
        # Begin transaction (implicit, but explicit for clarity)
        conn.set_session(autocommit=False)
        
        # Advanced Query 1: Insert the amenity
        cur.execute(
            """
            INSERT INTO amenity (buildingid, type, floor, notes)
            VALUES (%s, %s, %s, %s)
            RETURNING amenityid
            """,
            (payload.building_id, payload.type, payload.floor, payload.notes),
        )
        amenity_result = cur.fetchone()
        if not amenity_result:
            raise Exception("Failed to create amenity")
        amenity_id = amenity_result["amenityid"]
        
        # Advanced Query 2: Insert multiple amenity-tag relationships
        inserted_tags = []
        for tag_id in payload.tag_ids:
            cur.execute(
                """
                INSERT INTO amenitytag (amenityid, tagid)
                VALUES (%s, %s)
                ON CONFLICT (amenityid, tagid) DO NOTHING
                RETURNING tagid
                """,
                (amenity_id, tag_id),
            )
            tag_result = cur.fetchone()
            if tag_result:
                inserted_tags.append(tag_result["tagid"])
        
        # Commit transaction
        conn.commit()
        
        return {
            "amenity_id": amenity_id,
            "attached_tags": inserted_tags,
            "message": "Amenity created with tags successfully"
        }
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Transaction failed: {str(e)}")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()



# ----------------------------------------------------------------
# Simple Transaction: Create Building with Address
# ----------------------------------------------------------------

@app.post("/buildings/with-address")
def create_building_with_address(payload: BuildingWithAddressCreate):
    
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # Set transaction isolation level
        cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
        conn.set_session(autocommit=False)
        
        # Advanced Query 1: Insert the address, get back the new AddressId
        cur.execute(
            """
            INSERT INTO address (address, lat, lon)
            VALUES (%s, %s, %s)
            RETURNING addressid
            """,
            (payload.address, payload.lat, payload.lon),
        )
        address_result = cur.fetchone()
        if not address_result:
            raise Exception("Failed to create address")
        address_id = address_result["addressid"]
        
        # Advanced Query 2: Insert the building using the AddressId from step 1
        cur.execute(
            """
            INSERT INTO building (name, addressid)
            VALUES (%s, %s)
            RETURNING buildingid, name, addressid
            """,
            (payload.name, address_id),
        )
        building_result = cur.fetchone()
        if not building_result:
            raise Exception("Failed to create building")
        
        # Commit transaction
        conn.commit()
        
        return {
            "building_id": building_result["buildingid"],
            "name": building_result["name"],
            "address_id": building_result["addressid"],
            "address": payload.address,
            "lat": payload.lat,
            "lon": payload.lon,
            "message": "Building and address created successfully"
        }
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Transaction failed: {str(e)}")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


# ----------------------------------------------------------------
# Stored Procedure Endpoints
# ----------------------------------------------------------------

@app.get("/amenities/{amenity_id}/stats")
def get_amenity_statistics(amenity_id: int):
    """
    Call stored function fn_get_amenity_stats to get comprehensive statistics.
    Uses the function version which returns a table for easier consumption.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Call the function that returns a table
        cur.execute(
            "SELECT * FROM fn_get_amenity_stats(%s)",
            (amenity_id,)
        )
        result = cur.fetchone()
        if result:
            return {
                "amenity_id": amenity_id,
                "avg_rating": float(result["avg_rating"]) if result["avg_rating"] is not None else 0,
                "review_count": result["review_count"] if result["review_count"] is not None else 0,
                "latest_review_date": result["latest_review_date"].isoformat() if result["latest_review_date"] is not None else None,
                "building_name": result["building_name"] if result["building_name"] is not None else None
            }
        else:
            raise HTTPException(status_code=404, detail="Amenity not found")
    except psycopg2.Error as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()
