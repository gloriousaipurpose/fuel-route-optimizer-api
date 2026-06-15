import csv
import os
from django.conf import settings

# In-memory cache
STATIONS_CACHE = []
CITIES_COORDS_CACHE = {}
CITIES_LIST_CACHE = []

# Manual coordinates overrides for the 6 U.S. cities not found in the standard cities database
UNMATCHED_OVERRIDES = {
    ('brookpark', 'oh'): (41.3995, -81.8212),
    ('elizabethport', 'nj'): (40.6640, -74.2107),
    ('evergreen', 'al'): (31.4329, -86.9544),
    ('henrico', 'va'): (37.5314, -77.3489),
    ('port wentworth', 'ga'): (32.1488, -81.1632),
    ('university park', 'il'): (41.4467, -87.6837),
}

def load_cities_db():
    global CITIES_COORDS_CACHE
    if CITIES_COORDS_CACHE:
        return CITIES_COORDS_CACHE
        
    cities_path = os.path.join(settings.BASE_DIR, 'us_cities.csv')
    cities_coords = {}
    if not os.path.exists(cities_path):
        raise FileNotFoundError(f"Offline cities database not found at {cities_path}")
        
    with open(cities_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            city = row['CITY'].strip().lower()
            state = row['STATE_CODE'].strip().upper()
            cities_coords[(city, state)] = (float(row['LATITUDE']), float(row['LONGITUDE']))
            
    CITIES_COORDS_CACHE = cities_coords
    return CITIES_COORDS_CACHE

def get_all_cities():
    global CITIES_LIST_CACHE
    if CITIES_LIST_CACHE:
        return CITIES_LIST_CACHE
        
    cities_path = os.path.join(settings.BASE_DIR, 'us_cities.csv')
    if not os.path.exists(cities_path):
        return []
        
    cities = []
    with open(cities_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            city = row['CITY'].strip()
            state = row['STATE_CODE'].strip().upper()
            if city and state:
                cities.append(f"{city}, {state}")
                
    cities.sort()
    CITIES_LIST_CACHE = cities
    return CITIES_LIST_CACHE

def lookup_city_coords(query):
    if not query:
        return None
    parts = query.split(',')
    if len(parts) == 2:
        city = parts[0].strip().lower()
        state = parts[1].strip()
        cities_coords = load_cities_db()
        coords = cities_coords.get((city, state.upper())) or UNMATCHED_OVERRIDES.get((city, state.lower()))
        if coords:
            return coords
    return None

def initialize_stations():
    global STATIONS_CACHE
    if STATIONS_CACHE:
        return STATIONS_CACHE

    cities_coords = load_cities_db()
    fuel_path = os.path.join(settings.BASE_DIR, 'fuel-prices-for-be-assessment.csv')
    
    if not os.path.exists(fuel_path):
        raise FileNotFoundError(f"Fuel prices dataset not found at {fuel_path}")
        
    stations = []
    # Canadian provinces to filter out
    canada_provinces = {'AB', 'BC', 'MB', 'NB', 'NL', 'NS', 'NT', 'NU', 'ON', 'PE', 'QC', 'SK', 'YT'}
    
    with open(fuel_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Clean keys and values
            row = {k.strip() if k else k: v.strip() if v else v for k, v in row.items()}
            city = row['City'].strip().lower()
            state = row['State'].strip().upper()
            
            if state in canada_provinces:
                continue
                
            coords = cities_coords.get((city, state)) or UNMATCHED_OVERRIDES.get((city, state))
            if coords:
                stations.append({
                    'id': row['OPIS Truckstop ID'],
                    'name': row['Truckstop Name'],
                    'address': row['Address'],
                    'city': row['City'].strip(),
                    'state': row['State'].strip(),
                    'lat': coords[0],
                    'lng': coords[1],
                    'price': float(row['Retail Price'])
                })
    STATIONS_CACHE = stations
    return STATIONS_CACHE

def get_stations():
    if not STATIONS_CACHE:
        initialize_stations()
    return STATIONS_CACHE
