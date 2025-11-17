import os
import random
import json
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import Json
import requests
from bs4 import BeautifulSoup
from faker import Faker

DB_URL = os.environ.get("DATABASE_URL", "postgres://amen:amenities@db:5432/amenities")
BUILDING_LIST_URL = "https://fs.illinois.edu/building-list-by-building-number/"

def clean_text(s: str) -> str:
    """
    Remove NULs and other problematic control characters from scraped strings.
    """
    if s is None:
        return ""
    # Remove NULs explicitly
    s = s.replace("\x00", "")
    # Optionally strip other control chars below ASCII 32
    s = "".join(ch for ch in s if ord(ch) >= 32 or ch in "\n\r\t")
    return s.strip()


# --- Database Connection ---
def get_db_connection():
    conn = psycopg2.connect(DB_URL)
    return conn


# --- 1. Web Scraping: Building Names and Addresses ---
def scrape_buildings(url: str):
    """
    Scrapes building name and address from ALL tables on the UIUC Building List page.
    Returns a list of dicts with keys: name, address, lat, lon.
    """
    buildings = {}  # unique by name

    print(f"[SCRAPE] Fetching buildings from: {url}")

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        all_tables = soup.find_all("table")

        if not all_tables:
            print("[SCRAPE] WARNING: Found no tables on the page.")
            return []

        print(f"[SCRAPE] Found {len(all_tables)} table(s). Processing rows...")

        for table in all_tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    raw_name = cols[1].get_text(strip=True)
                    raw_address = cols[2].get_text(strip=True)
                    
                    building_name = clean_text(raw_name)
                    address = clean_text(raw_address)

                    if building_name and address and building_name not in buildings:
                        # Fake coords near campus
                        lat = 40.1098 + random.uniform(-0.005, 0.005)
                        lon = -88.2273 + random.uniform(-0.005, 0.005)

                        buildings[building_name] = {
                            "name": building_name,
                            "address": address,
                            "lat": lat,
                            "lon": lon,
                        }

        print(f"[SCRAPE] Collected {len(buildings)} unique buildings.")
        return list(buildings.values())

    except requests.RequestException as e:
        print(f"[SCRAPE] ERROR: Request failed: {e}")
        return []


# --- 2. Insert Buildings + Amenities ---
def insert_buildings_and_amenities(conn, buildings_data):
    """
    Inserts scraped building data into Address and Building tables, then adds amenities.
    """
    cur = conn.cursor()
    print(f"[SEED] Inserting {len(buildings_data)} buildings + amenities...")

    amenity_types = ["Bathroom", "WaterFountain", "VendingMachine"]
    floors = ["B", "1", "2", "3", "4", "5"]

    for b in buildings_data:
        # Address
        cur.execute("SELECT AddressId FROM Address WHERE Address = %s", (b["address"],))
        addr_row = cur.fetchone()
        if addr_row:
            address_id = addr_row[0]
        else:
            cur.execute(
                """
                INSERT INTO Address (Address, Lat, Lon)
                VALUES (%s, %s, %s)
                RETURNING AddressId
                """,
                (b["address"], b["lat"], b["lon"]),
            )
            address_id = cur.fetchone()[0]

        # Building
        cur.execute("SELECT BuildingId FROM Building WHERE Name = %s", (b["name"],))
        b_row = cur.fetchone()
        if b_row:
            building_id = b_row[0]
            cur.execute(
                "UPDATE Building SET AddressId = %s WHERE BuildingId = %s",
                (address_id, building_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO Building (Name, AddressId)
                VALUES (%s, %s)
                RETURNING BuildingId
                """,
                (b["name"], address_id),
            )
            building_id = cur.fetchone()[0]

        # Random amenities for this building
        for amenity_type in amenity_types:
            num_amenities = random.randint(1, 4)
            for i in range(num_amenities):
                floor = random.choice(floors)
                notes = f"Located on floor {floor}, near entrance/exit {i+1}."

                cur.execute(
                    """
                    INSERT INTO Amenity (BuildingId, Type, Floor, Notes)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (building_id, amenity_type, floor, notes),
                )

    conn.commit()
    print("[SEED] Buildings, addresses, and amenities inserted.")


# --- 3. Insert Users, Tags, and Reviews ---
def generate_and_insert_random_data(conn, num_reviews=1000, num_users=100):
    fake = Faker()
    cur = conn.cursor()

    print(f"[SEED] Inserting up to {num_users} users...")
    user_ids = []

    for _ in range(num_users):
        username = fake.user_name()
        email = fake.unique.email()
        join_date = fake.date_between(start_date="-2y", end_date="today")

        try:
            cur.execute(
                """
                INSERT INTO "User" (UserName, Email, JoinDate)
                VALUES (%s, %s, %s)
                ON CONFLICT (Email) DO NOTHING
                RETURNING UserId
                """,
                (username, email, join_date),
            )
            row = cur.fetchone()
            if row:
                user_ids.append(row[0])
        except psycopg2.IntegrityError:
            conn.rollback()

    conn.commit()
    print(f"[SEED] Users inserted: {len(user_ids)}")

    # Tags
    tags_to_insert = [
        "Clean",
        "Dirty",
        "HighPressure",
        "LowPressure",
        "OutOfOrder",
        "Modern",
        "Spacious",
        "ColdWater",
        "WarmWater",
    ]
    tag_ids = {}
    print(f"[SEED] Inserting tags: {len(tags_to_insert)}")

    for label in tags_to_insert:
        cur.execute(
            """
            INSERT INTO Tag (Label)
            VALUES (%s)
            ON CONFLICT (Label) DO NOTHING
            RETURNING TagId
            """,
            (label,),
        )
        row = cur.fetchone()
        if row:
            tag_ids[label] = row[0]
        else:
            # Already exists
            cur.execute("SELECT TagId FROM Tag WHERE Label = %s", (label,))
            tag_ids[label] = cur.fetchone()[0]

    # Amenities list
    cur.execute("SELECT AmenityId, Type FROM Amenity")
    rows = cur.fetchall()
    amenity_map = {row[0]: row[1] for row in rows}
    amenity_ids = list(amenity_map.keys())

    if not amenity_ids:
        print("[SEED] No amenities found. Skipping reviews.")
        return

    print(f"[SEED] Inserting {num_reviews} reviews...")
    base_time = datetime.now() - timedelta(days=365)
    review_rows = []
    amenity_tag_pairs = set()

    for _ in range(num_reviews):
        user_id = random.choice(user_ids)
        amenity_id = random.choice(amenity_ids)
        amenity_type = amenity_map[amenity_id]
        overall_rating = round(random.uniform(1.0, 5.0), 1)

        if amenity_type == "Bathroom":
            details = {
                "cleanliness": random.randint(1, 5),
                "privacy": random.randint(1, 5),
                "stock": random.randint(1, 5),
            }
        elif amenity_type == "WaterFountain":
            details = {
                "flow": random.randint(1, 5),
                "temperature": random.randint(1, 5),
                "filter_status": random.choice(["Good", "Needs Replacement"]),
            }
        else:  # VendingMachine
            details = {
                "selection": random.randint(1, 5),
                "working_status": random.choice(
                    ["Working", "Error", "OutOfOrder"]
                ),
                "payment_options": random.choice(
                    ["Cash Only", "Card Only", "Both"]
                ),
            }

        timestamp = fake.date_time_between(start_date=base_time, end_date="now")

        review_rows.append(
            (user_id, amenity_id, overall_rating, Json(details), timestamp)
        )

        # Random tags
        if tag_ids and random.random() < 0.6:
            chosen = random.sample(
                list(tag_ids.values()),
                k=random.randint(1, min(3, len(tag_ids))),
            )
            for tag_id in chosen:
                amenity_tag_pairs.add((amenity_id, tag_id))

    # Insert reviews, skipping duplicates of (UserId, AmenityId)
    cur.executemany(
        """
        INSERT INTO Review (UserId, AmenityId, OverallRating, RatingDetails, TimeStamp)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (UserId, AmenityId) DO NOTHING
        """,
    review_rows,
    )

    # Insert amenity-tag links
    cur.executemany(
        """
        INSERT INTO AmenityTag (AmenityId, TagId)
        VALUES (%s, %s)
        ON CONFLICT (AmenityId, TagId) DO NOTHING
        """,
        list(amenity_tag_pairs),
    )

    conn.commit()
    print(f"[SEED] Inserted {len(review_rows)} reviews and {len(amenity_tag_pairs)} amenity-tag pairs.")


def main():
    conn = get_db_connection()
    try:
        buildings = scrape_buildings(BUILDING_LIST_URL)
        if not buildings:
            print("[MAIN] No buildings scraped; aborting.")
            return

        insert_buildings_and_amenities(conn, buildings)
        generate_and_insert_random_data(conn, num_reviews=1000, num_users=100)
        print("[MAIN] Data population complete 🎉")
    finally:
        conn.close()
        print("[MAIN] Connection closed.")


if __name__ == "__main__":
    main()
