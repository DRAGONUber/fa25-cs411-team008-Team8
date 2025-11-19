-- Enable useful extension(s)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Drop tables if they already exist (dev convenience)
DROP TABLE IF EXISTS AmenityTag CASCADE;
DROP TABLE IF EXISTS Review CASCADE;
DROP TABLE IF EXISTS Amenity CASCADE;
DROP TABLE IF EXISTS Tag CASCADE;
DROP TABLE IF EXISTS Building CASCADE;
DROP TABLE IF EXISTS Address CASCADE;
DROP TABLE IF EXISTS "User" CASCADE;

------------------------------------------------------------
-- User
------------------------------------------------------------
CREATE TABLE "User" (
    UserId   SERIAL PRIMARY KEY,
    UserName VARCHAR(255) NOT NULL,
    Email    VARCHAR(255) NOT NULL UNIQUE,
    JoinDate DATE NOT NULL DEFAULT CURRENT_DATE
);

------------------------------------------------------------
-- Address
------------------------------------------------------------
CREATE TABLE Address (
    AddressId SERIAL PRIMARY KEY,
    Address   VARCHAR(255) NOT NULL,
    Lat       DECIMAL(9,6) NOT NULL,
    Lon       DECIMAL(9,6) NOT NULL,
    -- Attribute-level constraint: UIUC campus bounds (approximately)
    CONSTRAINT chk_uiuc_lat CHECK (Lat BETWEEN 40.09 AND 40.12),
    CONSTRAINT chk_uiuc_lon CHECK (Lon BETWEEN -88.25 AND -88.20)
);

------------------------------------------------------------
-- Building
------------------------------------------------------------
CREATE TABLE Building (
    BuildingId SERIAL PRIMARY KEY,
    Name       VARCHAR(255) NOT NULL,
    AddressId  INT NOT NULL REFERENCES Address(AddressId)
);

------------------------------------------------------------
-- Amenity
------------------------------------------------------------
CREATE TABLE Amenity (
    AmenityId  SERIAL PRIMARY KEY,
    BuildingId INT NOT NULL REFERENCES Building(BuildingId),
    Type       VARCHAR(40) NOT NULL CHECK (Type IN ('Bathroom','WaterFountain','VendingMachine')),
    Floor      VARCHAR(20) NOT NULL,
    Notes      TEXT,
    ReviewCount INT NOT NULL DEFAULT 0
);

------------------------------------------------------------
-- Review
------------------------------------------------------------
CREATE TABLE Review (
    ReviewId      SERIAL PRIMARY KEY,
    UserId        INT NOT NULL REFERENCES "User"(UserId),
    AmenityId     INT NOT NULL REFERENCES Amenity(AmenityId),
    OverallRating NUMERIC(2,1) NOT NULL CHECK (OverallRating BETWEEN 0 AND 5),
    RatingDetails JSONB NOT NULL,
    TimeStamp     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Extra useful constraint: a user can only have one review per amenity
ALTER TABLE Review
ADD CONSTRAINT unique_user_amenity_review
UNIQUE (UserId, AmenityId);

-- Attribute-level constraint: Email must contain @ symbol
ALTER TABLE "User"
ADD CONSTRAINT chk_email_format CHECK (Email LIKE '%@%' AND Email LIKE '%.%');

------------------------------------------------------------
-- Tag
------------------------------------------------------------
CREATE TABLE Tag (
    TagId SERIAL PRIMARY KEY,
    Label VARCHAR(40) NOT NULL UNIQUE
);

------------------------------------------------------------
-- AmenityTag (junction table)
------------------------------------------------------------
CREATE TABLE AmenityTag (
    AmenityId INT NOT NULL REFERENCES Amenity(AmenityId) ON DELETE CASCADE,
    TagId     INT NOT NULL REFERENCES Tag(TagId) ON DELETE CASCADE,
    PRIMARY KEY (AmenityId, TagId)
);

------------------------------------------------------------
-- Helpful indexes for keyword search (for later use)
------------------------------------------------------------

-- Building name & address fuzzy search
CREATE INDEX IF NOT EXISTS idx_building_name_trgm
ON Building
USING gin (Name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_address_trgm
ON Address
USING gin (Address gin_trgm_ops);

-- Amenity notes search
CREATE INDEX IF NOT EXISTS idx_amenity_notes_trgm
ON Amenity
USING gin (Notes gin_trgm_ops);

----------------------------------------------------------

------------------------------------------------------------
-- Stored Procedures
------------------------------------------------------------

CREATE OR REPLACE PROCEDURE sp_upsert_review(
    p_user_id INT,
    p_amenity_id INT,
    p_rating DECIMAL,
    p_details JSONB
)
LANGUAGE plpgsql
AS $$
BEGIN
    -- Control Structure: IF/ELSE
    IF EXISTS (SELECT 1 FROM Review WHERE UserId = p_user_id AND AmenityId = p_amenity_id) THEN
        -- Advanced Query 1: Update existing
        UPDATE Review
        SET OverallRating = p_rating,
            RatingDetails = p_details,
            TimeStamp = NOW()
        WHERE UserId = p_user_id AND AmenityId = p_amenity_id;
    ELSE
        -- Advanced Query 2: Insert new
        INSERT INTO Review (UserId, AmenityId, OverallRating, RatingDetails)
        VALUES (p_user_id, p_amenity_id, p_rating, p_details);
    END IF;
END;
$$;

-- Stored Procedure 2: Calculate and return amenity statistics
CREATE OR REPLACE FUNCTION fn_get_amenity_stats(p_amenity_id INT)
RETURNS TABLE (
    avg_rating NUMERIC,
    review_count BIGINT,
    latest_review_date TIMESTAMPTZ,
    building_name VARCHAR
)
LANGUAGE plpgsql
AS $$
BEGIN
    -- Advanced Query 1: Aggregate statistics with JOIN
    RETURN QUERY
    SELECT 
        COALESCE(AVG(R.OverallRating), 0)::NUMERIC,
        COUNT(R.ReviewId),
        MAX(R.TimeStamp),
        B.Name
    FROM Amenity A
    JOIN Building B ON A.BuildingId = B.BuildingId
    LEFT JOIN Review R ON A.AmenityId = R.AmenityId
    WHERE A.AmenityId = p_amenity_id
    GROUP BY A.AmenityId, B.Name;
    
    -- Control Structure: IF statement for validation (handled by COALESCE above)
END;
$$;

------------------------------------------------------------
-- Triggers
------------------------------------------------------------

-- Trigger 1: Prevent duplicate emails (case-insensitive check)
CREATE OR REPLACE FUNCTION fn_check_duplicate_email()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    -- Event: BEFORE INSERT OR UPDATE on User
    -- Condition: IF email already exists (case-insensitive)
    IF EXISTS (
        SELECT 1 FROM "User" 
        WHERE LOWER(Email) = LOWER(NEW.Email) 
        AND UserId != COALESCE(NEW.UserId, -1)
    ) THEN
        -- Action: Raise exception (prevent insert/update)
        RAISE EXCEPTION 'Email % already exists', NEW.Email;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_prevent_duplicate_email
BEFORE INSERT OR UPDATE ON "User"
FOR EACH ROW
EXECUTE FUNCTION fn_check_duplicate_email();

-- Trigger 2: Auto-update review count on Amenity when reviews are added/deleted
CREATE OR REPLACE FUNCTION fn_update_review_count()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    -- Event: AFTER INSERT, UPDATE, or DELETE on Review
    IF TG_OP = 'INSERT' THEN
        -- Action: Increment review count for the amenity
        UPDATE Amenity
        SET ReviewCount = ReviewCount + 1
        WHERE AmenityId = NEW.AmenityId;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        -- Action: Decrement review count for the amenity
        UPDATE Amenity
        SET ReviewCount = GREATEST(ReviewCount - 1, 0)  -- Prevent negative counts
        WHERE AmenityId = OLD.AmenityId;
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        -- Condition: IF amenity changed (user updated review for different amenity)
        IF OLD.AmenityId != NEW.AmenityId THEN
            -- Action: Decrement old amenity, increment new amenity
            UPDATE Amenity
            SET ReviewCount = GREATEST(ReviewCount - 1, 0)
            WHERE AmenityId = OLD.AmenityId;
            
            UPDATE Amenity
            SET ReviewCount = ReviewCount + 1
            WHERE AmenityId = NEW.AmenityId;
        END IF;
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_update_review_count
AFTER INSERT OR UPDATE OR DELETE ON Review
FOR EACH ROW
EXECUTE FUNCTION fn_update_review_count();