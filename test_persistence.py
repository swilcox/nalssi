#!/usr/bin/env python3
"""
Test script to verify SQLite data persistence to disk.

Run this script, then immediately query the database file with sqlite3
to verify data has been written to disk.
"""

import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import SessionLocal, engine, Base
from app.models.location import Location

# Create tables
Base.metadata.create_all(bind=engine)

print("Creating test location...")
db = SessionLocal()

try:
    # Create a test location
    location = Location(
        name="Persistence Test Location",
        latitude=37.7749,
        longitude=-122.4194,
        country_code="US",
        enabled=True,
    )

    db.add(location)
    db.commit()
    db.refresh(location)

    print(f"✓ Created location with ID: {location.id}")
    print(f"✓ Name: {location.name}")
    print(f"✓ Coordinates: {location.latitude}, {location.longitude}")
    print()
    print("Data has been committed to the database.")
    print()
    print("To verify persistence, run this command in another terminal:")
    print(
        f"  sqlite3 nalssi.db \"SELECT * FROM locations WHERE name LIKE '%Persistence Test%';\""
    )
    print()
    print(
        "You should see the location immediately without needing to close this script."
    )

finally:
    db.close()

print("\nScript complete. Database connection closed.")
