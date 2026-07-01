import math
import json
import os


def haversine_distance(lat1, lon1, lat2, lon2, use_miles=True):
    """Calculates distance in miles between two lat/long points."""
    earth_radius_miles = 3958.8 if use_miles else 6371.0
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)

    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad

    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return earth_radius_miles * c


def load_county_data(json_path):
    """Loads county coordinate data from the JSON file."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Could not find county DB at {json_path}")
        return {}


def build_search_region(anchor_geoid, county_db, radius_miles=100.0):
    """
    Finds all counties within a specific radius of the anchor county.
    Returns a list of matching GEOIDs.
    """
    if anchor_geoid not in county_db:
        print(f"Warning: Anchor county {anchor_geoid} not in database.")
        return [anchor_geoid]  # Fallback to just the anchor to prevent crashing

    anchor_data = county_db[anchor_geoid]
    anchor_lat, anchor_lon = anchor_data['lat'], anchor_data['lon']

    region_geoids = []

    for target_geoid, coords in county_db.items():
        target_lat, target_lon = coords['lat'], coords['lon']
        dist = haversine_distance(anchor_lat, anchor_lon, target_lat, target_lon)

        if dist <= radius_miles:
            region_geoids.append(target_geoid)

    return region_geoids


if __name__ == "__main__":
    # Test it out!
    JSON_PATH = r"E:\Users\Andy\PycharmProjects\Genealogy\JSON\county_coords.json"
    db = load_county_data(JSON_PATH)

    if db:
        # Let's test Centre County, PA (GEOID 42027)
        anchor = "42027"
        RADIUS = 50.0
        print(f"Finding all counties within {RADIUS} miles of {db[anchor]['name']}...")

        region = build_search_region(anchor, db, radius_miles=RADIUS)

        print(f"\nFound {len(region)} counties in the blast radius:")
        for geoid in region:
            name = db[geoid]['name']
            dist = haversine_distance(db[anchor]['lat'], db[anchor]['lon'], db[geoid]['lat'], db[geoid]['lon'])
            print(f" - {name} ({geoid}) : {dist:.1f} miles")
