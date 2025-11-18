import os
import random
import json
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import Json
import requests
from bs4 import BeautifulSoup
from faker import Faker
import googlemaps

# -------------------------------------------------------------------
# Config
# -------------------------------------------------------------------

DB_URL = os.environ.get("DATABASE_URL", "postgres://amen:amenities@db:5432/amenities")
BUILDING_LIST_URL = "https://fs.illinois.edu/building-list-by-building-number/"

#move this to an env var later
GMAPS_API_KEY = "AIzaSyDQtQbhBozbOKsMzZAdAsQmRNYxFYWIizQ"
gmaps = googlemaps.Client(key=GMAPS_API_KEY)


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def geocode_address(address: str):
    """
    Use Google Maps Geocoding API to get (lat, lon) for an address.
    Returns (lat, lon) or (None, None) if not found / error.
    """
    if not address:
        return None, None

    try:
        results = gmaps.geocode(address)
        if results:
            loc = results[0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
    except Exception as e:
        print(f"[ERROR] Geocoding failed for '{address}': {e}")
    return None, None


def fallback_random_coords():
    """
    Fallback: generate pseudo-random coordinates around UIUC campus.
    """
    lat = 40.1098 + random.uniform(-0.01, 0.01)
    lon = -88.2273 + random.uniform(-0.01, 0.01)
    return lat, lon


def clean_text(s: str) -> str:
    """
    Remove NULs and other problematic control characters from scraped strings.
    """
    if s is None:
        return ""
    s = s.replace("\x00", "")
    s = "".join(ch for ch in s if ord(ch) >= 32 or ch in "\n\r\t")
    return s.strip()


def get_db_connection():
    """
    Open a new connection to the Postgres DB using DB_URL.
    """
    conn = psycopg2.connect(DB_URL)
    return conn


# -------------------------------------------------------------------
# Scraping buildings: name, address, lat, lon
# -------------------------------------------------------------------

def scrape_buildings(url: str):
    """
    Scrapes building name and address from ALL tables on the UIUC Building List page.
    Returns a list of dicts with keys: name, address, lat, lon.
    """
    buildings = {}  # unique by building_name

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
                        # Geocode the address
                        lat, lon = geocode_address(address)
                        if lat is None or lon is None:
                            print(f"[WARN] No geocode match for '{address}', using fallback coords.")
                            lat, lon = fallback_random_coords()

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


# -------------------------------------------------------------------
# Insert buildings, addresses, amenities
# -------------------------------------------------------------------

def insert_buildings_and_amenities(conn, buildings_data):
    """
    Inserts scraped building data into Address and Building tables, then adds amenities.
    Expects each item in buildings_data to have: name, address, lat, lon.
    """
    cur = conn.cursor()
    print(f"[SEED] Inserting {len(buildings_data)} buildings + amenities...")

    amenity_types = ["Bathroom", "WaterFountain", "VendingMachine"]
    floors = ["B", "1", "2", "3", "4", "5"]

    for b in buildings_data:
        name = b["name"]
        address = b["address"]
        lat = b["lat"]
        lon = b["lon"]

        # Safety: fallback if somehow still None
        if lat is None or lon is None:
            lat, lon = fallback_random_coords()

        # Upsert Address by address string
        cur.execute("SELECT addressid FROM address WHERE address = %s", (address,))
        address_result = cur.fetchone()

        if address_result:
            address_id = address_result[0]
            # Optionally update lat/lon if we want them fresh
            cur.execute(
                "UPDATE address SET lat = %s, lon = %s WHERE addressid = %s",
                (lat, lon, address_id),
            )
        else:
            cur.execute(
                "INSERT INTO address (address, lat, lon) VALUES (%s, %s, %s) RETURNING addressid",
                (address, lat, lon),
            )
            address_id = cur.fetchone()[0]

        # Upsert Building by name
        cur.execute("SELECT buildingid FROM building WHERE name = %s", (name,))
        building_result = cur.fetchone()

        if building_result:
            building_id = building_result[0]
            cur.execute(
                "UPDATE building SET addressid = %s WHERE buildingid = %s",
                (address_id, building_id),
            )
        else:
            cur.execute(
                "INSERT INTO building (name, addressid) VALUES (%s, %s) RETURNING buildingid",
                (name, address_id),
            )
            building_id = cur.fetchone()[0]

        # Insert sample amenities for this building
        for amenity_type in amenity_types:
            num_amenities = random.randint(1, 4)
            for i in range(num_amenities):
                floor = random.choice(floors)
                notes = f"Located on floor {floor}, near entrance/exit {i+1}."
                cur.execute(
                    """
                    INSERT INTO amenity (buildingid, type, floor, notes)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (building_id, amenity_type, floor, notes),
                )

    conn.commit()
    print("[SEED] Buildings, addresses, and amenities inserted.")


# -------------------------------------------------------------------
# Insert users, tags, reviews, amenity-tag links
# -------------------------------------------------------------------

def generate_and_insert_random_data(conn, num_reviews=1000, num_users=100):
    """
    Generates and inserts Users, Tags, and Reviews + AmenityTag relationships.
    """
    fake = Faker()
    cur = conn.cursor()
    temp_cur = conn.cursor()

    print(f"[SEED] Inserting up to {num_users} users...")

    user_ids = []
    for _ in range(num_users):
        try:
            temp_cur.execute(
                """
                INSERT INTO "User" (UserName, Email, JoinDate)
                VALUES (%s, %s, %s)
                ON CONFLICT (Email) DO NOTHING
                RETURNING UserId
                """,
                (
                    fake.user_name(),
                    fake.unique.email(),
                    fake.date_between(start_date="-2y", end_date="today"),
                ),
            )
            result = temp_cur.fetchone()
            if result:
                user_ids.append(result[0])
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
        "OutofOrder",
        "Modern",
        "Spacious",
        "ColdWater",
        "WarmWater",
    ]
    tag_ids = {}
    print(f"[SEED] Inserting tags: {len(tags_to_insert)}")
    for label in tags_to_insert:
        temp_cur.execute(
            """
            INSERT INTO tag (label)
            VALUES (%s)
            ON CONFLICT (label) DO NOTHING
            RETURNING tagid
            """,
            (label,),
        )
        result = temp_cur.fetchone()
        if result:
            tag_ids[label] = result[0]
        else:
            temp_cur.execute("SELECT tagid FROM tag WHERE label = %s", (label,))
            existing = temp_cur.fetchone()
            if existing:
                tag_ids[label] = existing[0]

    # Map amenities
    temp_cur.execute("SELECT amenityid, type FROM amenity")
    amenity_map = {row[0]: row[1] for row in temp_cur.fetchall()}
    amenity_ids = list(amenity_map.keys())

    if not amenity_ids:
        print("[SEED] No amenities found. Cannot generate reviews.")
        return

    print(f"[SEED] Inserting {num_reviews} reviews...")

    base_time = datetime.now() - timedelta(days=365)
    review_rows = []
    amenity_tag_pairs = []

    for _ in range(num_reviews):
        user_id = random.choice(user_ids)
        amenity_id = random.choice(amenity_ids)
        amenity_type = amenity_map[amenity_id]
        overall_rating = round(random.uniform(1.0, 5.0), 1)

        # Rating details based on type
        if amenity_type == "Bathroom":
            rating_details = {
                "cleanliness": random.randint(1, 5),
                "privacy": random.randint(1, 5),
                "stock": random.randint(1, 5),
            }
        elif amenity_type == "WaterFountain":
            rating_details = {
                "flow": random.randint(1, 5),
                "temperature": random.randint(1, 5),
                "filter_status": random.choice(["Good", "Needs Replacement"]),
            }
        elif amenity_type == "VendingMachine":
            rating_details = {
                "selection": random.randint(1, 5),
                "working_status": random.choice(
                    ["Working", "Error", "OutOfOrder"]
                ),
                "payment_options": random.choice(
                    ["Cash Only", "Card Only", "Both"]
                ),
            }
        else:
            rating_details = {}

        timestamp = fake.date_time_between(
            start_date=base_time, end_date="now", tzinfo=None
        )

        review_rows.append(
            (user_id, amenity_id, overall_rating, json.dumps(rating_details), timestamp)
        )

        # Randomly assign tags to amenity
        if random.random() < 0.6 and tag_ids:
            selected_tags = random.sample(
                list(tag_ids.values()),
                k=random.randint(1, min(3, len(tag_ids))),
            )
            for tag_id in selected_tags:
                amenity_tag_pairs.append((amenity_id, tag_id))

    # Insert reviews; ignore duplicate (userid, amenityid)
    cur.executemany(
        """
        INSERT INTO review (userid, amenityid, overallrating, ratingdetails, timestamp)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (userid, amenityid) DO NOTHING
        """,
        review_rows,
    )

    # Deduplicate amenity-tag pairs
    unique_amenity_tags = list(set(amenity_tag_pairs))
    for amenity_id, tag_id in unique_amenity_tags:
        cur.execute(
            """
            INSERT INTO amenitytag (amenityid, tagid)
            VALUES (%s, %s)
            ON CONFLICT (amenityid, tagid) DO NOTHING
            """,
            (amenity_id, tag_id),
        )

    conn.commit()
    print(
        f"[SEED] Inserted {len(review_rows)} reviews and {len(unique_amenity_tags)} amenity-tag pairs."
    )


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

def main():
    conn = get_db_connection()
    if conn is None:
        print("[MAIN] ERROR: Could not connect to database.")
        return

    try:
        buildings_data = scrape_buildings(BUILDING_LIST_URL)
        if not buildings_data:
            print("[MAIN] CRITICAL: No buildings scraped. Aborting.")
            conn.close()
            return

        insert_buildings_and_amenities(conn, buildings_data)
        generate_and_insert_random_data(conn, num_reviews=1000, num_users=100)

        print("[MAIN] Data population complete 🎉")
    except Exception as e:
        print(f"[MAIN] Unexpected error: {e}")
        conn.rollback()
    finally:
        conn.close()
        print("[MAIN] Connection closed.")


if __name__ == "__main__":
    main()
