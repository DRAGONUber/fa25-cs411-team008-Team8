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
    Lon       DECIMAL(9,6) NOT NULL
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
    Notes      TEXT
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
