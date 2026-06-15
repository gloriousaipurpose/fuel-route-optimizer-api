# Fuel Route Planner API

A Django REST API that calculates the **optimal refueling stops** along any U.S. driving route — minimizing total fuel cost based on real truck-stop prices, with a 500-mile vehicle range and 10 mpg efficiency.

---

## How It Works

### Routing
- **Geocoding**: User-supplied city names are resolved to coordinates via [Nominatim (OpenStreetMap)](https://nominatim.openstreetmap.org/). One call per endpoint request.
- **Route geometry**: A single call to the [OSRM](http://project-osrm.org/) public routing API returns the full driving path as a GeoJSON polyline.

### Fuel Stop Optimization
Gas stations are sourced entirely from the provided CSV (8,151 entries). No external pricing API is used. The algorithm runs in-process:

1. **Spatial projection** — Stations are filtered by route bounding box, then each station is projected onto the route polyline using a downsampled path + local refinement search. Stations within **10 miles** of the route are kept.
2. **LP-Greedy optimizer** — An exact, continuous Linear Programming-style greedy pass finds the globally optimal fuel purchases:
   - Computes minimum purchases needed (left-to-right) to avoid running out of fuel.
   - Shifts fuel spend from expensive stations to cheaper preceding ones (right-to-left pass), respecting the 50-gallon tank capacity constraint at every point.
   - **Zero discretization error** — fuel quantities are real-valued, not rounded to gallons.
   - Runs in **< 5 ms** on any route.

---

## API Endpoints

### `GET /api/route/`

Returns the optimal refueling plan as JSON.

**Query Parameters:**

| Parameter | Required | Example |
|-----------|----------|---------|
| `start`   | ✅       | `Houston, TX` |
| `end`     | ✅       | `New York, NY` |

**Example Request:**
```
GET /api/route/?start=Houston,TX&end=New York,NY
```

**Example Response:**
```json
{
  "start_name": "Houston, TX",
  "end_name": "New York, NY",
  "start_coordinates": [29.758, -95.367],
  "end_coordinates": [40.712, -74.005],
  "total_distance_miles": 1628.4,
  "total_fuel_cost": 168.32,
  "refuel_stops": [
    {
      "name": "LOVES TRAVEL STOP #256",
      "address": "I-10, EXIT 140B",
      "city": "Van Horn",
      "state": "TX",
      "lat": 31.035,
      "lng": -104.833,
      "price": 3.649,
      "distance_along_route": 282.1,
      "fuel_to_buy_gallons": 12.5,
      "cost": 45.61
    }
  ],
  "route_geometry": [[29.758, -95.367], ...]
}
```

**Error Responses:**

| Status | Reason |
|--------|--------|
| `400`  | Missing parameters, unresolvable location, or route impossible to complete (gap > 500 miles) |
| `500`  | Upstream routing API failure |

---

### `GET /route-map/`

Opens an interactive Leaflet.js map in the browser showing the route and all refueling stops.

**Query Parameters:** Same as `/api/route/` (`start`, `end`).

---

## Setup

```bash
# 1. Clone or extract the project
cd trip/

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the development server
python manage.py runserver
```

Then open: [http://127.0.0.1:8000/route-map/](http://127.0.0.1:8000/route-map/)

---

## Running Tests

```bash
python manage.py test --verbosity=2
```

All 6 tests pass covering: Haversine accuracy, US-only station filtering, optimizer correctness, unreachable route detection, API JSON contract, and geocoding error handling.

---

## Design Decisions

**Why no heavy spatial libraries (GeoPandas, Shapely)?**  
The entire spatial index and LP optimizer is pure Python — no native C extensions. This means zero build friction on any OS, no conda environments, and a clean `pip install`.

**Why LP-Greedy over Dijkstra / DP?**  
Discretized DP introduces rounding errors (e.g., "buying" 0.3 gallons for free due to grid snapping). The LP-Greedy pass is mathematically exact, runs in O(N²) on the filtered station set (N ≤ ~150), and completes in < 5 ms.

**Why pre-cache stations in memory?**  
CSV parsing of 8,000 rows takes ~80 ms. By loading once on Django startup (`AppConfig.ready()`), subsequent API calls skip disk I/O entirely. The in-memory footprint is negligible (~2 MB).

---

## Project Structure

```
trip/
├── manage.py
├── requirements.txt
├── fuel-prices-for-be-assessment.csv   # Provided fuel price dataset
├── us_cities.csv                       # Offline US city → lat/lng lookup
├── fuel_route_project/                 # Django project config
│   ├── settings.py
│   └── urls.py
└── fuel_planner/                       # Core application
    ├── apps.py                         # Startup station pre-loading
    ├── views.py                        # API + map endpoints
    ├── urls.py
    ├── tests.py
    ├── templates/fuel_planner/
    │   └── map.html                    # Leaflet interactive map
    └── services/
        ├── fuel_data.py                # CSV loading + in-memory cache
        ├── routing.py                  # OSRM + Nominatim clients
        └── optimizer.py               # LP-Greedy fuel optimizer
```
