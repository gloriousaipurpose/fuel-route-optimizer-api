import json
import urllib.request
import urllib.parse
import logging
from .fuel_data import lookup_city_coords

logger = logging.getLogger(__name__)

USER_AGENT = 'FuelRoutePlanner/1.0 (django-backend-assessment)'

US_STATES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
    'DC', 'PR', 'VI', 'GU', 'MP', 'AS'
}

US_STATE_NAMES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware",
    "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky",
    "louisiana", "maine", "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey", "new mexico",
    "new york", "north carolina", "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania",
    "rhode island", "south carolina", "south dakota", "tennessee", "texas", "utah", "vermont",
    "virginia", "washington", "west virginia", "wisconsin", "wyoming", "district of columbia",
    "puerto rico", "virgin islands", "guam", "northern mariana islands", "american samoa"
}

FOREIGN_INDICATORS = {
    # Countries
    "india", "canada", "mexico", "china", "france", "germany", "japan", "brazil", "russia", 
    "united kingdom", "uk", "england", "australia", "italy", "spain", "pakistan", "bangladesh", 
    "indonesia", "nigeria", "turkey", "vietnam", "egypt", "thailand", "south africa", "korea", 
    "iran", "iraq", "saudi arabia", "ukraine", "poland", "argentina", "colombia", "peru", 
    "venezuela", "chile", "ecuador", "cuba", "philippines", "malaysia", "singapore", "new zealand", 
    "ireland", "sweden", "norway", "finland", "denmark", "netherlands", "belgium", "switzerland", 
    "austria", "portugal", "greece", "kenya", "morocco",
    # Cities
    "mumbai", "delhi", "bangalore", "kolkata", "chennai", "hyderabad", "pune", "ahmedabad", 
    "london", "paris", "tokyo", "beijing", "shanghai", "toronto", "vancouver", "montreal", 
    "mexico city", "berlin", "madrid", "rome", "moscow", "sydney", "melbourne", "cairo", 
    "istanbul", "bangkok", "seoul", "jakarta", "manila", "kuala lumpur", "dhaka", "karachi", 
    "lahore", "rio de janeiro", "sao paulo", "buenos aires", "lima", "bogota", "santiago", "caracas"
}

def is_query_usa_only(query):
    """
    Checks if the user query suggests a location outside the USA.
    Handles multi-part (comma separated) queries and single-word queries.
    """
    q_clean = query.strip().lower()
    parts = q_clean.split(',')
    
    # If there are 2 or more parts, check the last part
    if len(parts) >= 2:
        last_part = parts[-1].strip().replace('.', '')
        # If the last part is a valid U.S. state, abbreviation, or U.S. country, it's allowed
        if (last_part in US_STATE_NAMES or 
            last_part.upper() in US_STATES or 
            last_part in {"us", "usa", "united states", "united states of america"}):
            return True
        # If the last part isn't U.S., check if any parts contain foreign indicators
        for part in parts:
            p_clean = part.strip()
            if p_clean in FOREIGN_INDICATORS:
                return False
        return False
    else:
        # Single-word queries
        if q_clean in FOREIGN_INDICATORS:
            return False
            
    return True

def geocode(query):
    """
    Geocodes a query string (e.g., 'Houston, TX') to latitude and longitude using Nominatim.
    Restricts searches to the USA and performs validation checks.
    """
    if not query:
        return None
        
    query_stripped = query.strip()
    
    # 1. Validate that the query targets the USA
    if not is_query_usa_only(query_stripped):
        raise ValueError(f"Location '{query_stripped}' is outside the USA. This route planner only supports locations within the United States.")
        
    # 2. Try offline database lookup first
    offline_coords = lookup_city_coords(query_stripped)
    if offline_coords:
        return offline_coords
        
    # 3. Call Nominatim geocoder, strictly filtering by countrycodes=us
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "q": query_stripped,
        "format": "json",
        "limit": 1,
        "countrycodes": "us"
    })
    
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': USER_AGENT}
        )
        # 10 second timeout for reliability
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            if data:
                # Double-check: ensure the display name actually belongs to the US
                display_name = data[0].get('display_name', '').lower()
                if not any(usa_name in display_name for usa_name in ["united states", "usa", "united states of america"]):
                    raise ValueError(f"Geocoded location '{query_stripped}' resolved outside the USA.")
                return float(data[0]['lat']), float(data[0]['lon'])
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Geocoding error for query '{query_stripped}': {e}")
        
    return None

def get_route(start_lat, start_lng, end_lat, end_lng):
    """
    Calls OSRM to get driving routing distance (in miles) and path coordinates (as a list of lat/lng tuples).
    """
    # OSRM expects: longitude,latitude
    url = f"http://router.project-osrm.org/route/v1/driving/{start_lng},{start_lat};{end_lng},{end_lat}?overview=full&geometries=geojson"
    
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            if data.get('code') == 'Ok' and data.get('routes'):
                route = data['routes'][0]
                distance_meters = route['distance']
                distance_miles = distance_meters * 0.000621371 # Convert meters to miles
                
                geometry = route['geometry']['coordinates'] # OSRM returns [lng, lat]
                # Convert geometry to list of (lat, lng) for internal use
                path = [(p[1], p[0]) for p in geometry]
                return distance_miles, path
    except Exception as e:
        logger.error(f"OSRM routing error from ({start_lat},{start_lng}) to ({end_lat},{end_lng}): {e}")
        
    return None, None
