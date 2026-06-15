import math
import logging

logger = logging.getLogger(__name__)

# Vehicle Parameters
TANK_CAPACITY = 50.0  # gallons
FUEL_EFFICIENCY = 10.0  # miles per gallon
MAX_RANGE = TANK_CAPACITY * FUEL_EFFICIENCY  # 500 miles

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Computes the great-circle distance between two points in miles.
    """
    R = 3958.8  # Earth's radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def project_stations_to_route(path, stations, max_distance=10.0):
    """
    Projects all gas stations onto the route path, filtering those within `max_distance` miles.
    Returns sorted list of stations along the route with their cumulative distance.
    """
    # 1. Precompute cumulative distance along the path
    cum_dist = [0.0]
    for i in range(1, len(path)):
        cum_dist.append(cum_dist[-1] + haversine_distance(path[i-1][0], path[i-1][1], path[i][0], path[i][1]))
        
    # 2. Get path bounding box
    latitudes = [p[0] for p in path]
    longitudes = [p[1] for p in path]
    min_lat, max_lat = min(latitudes) - 0.2, max(latitudes) + 0.2
    min_lng, max_lng = min(longitudes) - 0.2, max(longitudes) + 0.2
    
    # 3. Quick bounding box pre-filter
    bbox_stations = [s for s in stations if min_lat <= s['lat'] <= max_lat and min_lng <= s['lng'] <= max_lng]
    
    # 4. Project stations to route using downsampled path + local search refinement
    route_stations = []
    
    # Downsample path to speed up closest-point search (take every 10th point)
    downsampled_indices = list(range(0, len(path), 10))
    if downsampled_indices[-1] != len(path) - 1:
        downsampled_indices.append(len(path) - 1)
        
    for s in bbox_stations:
        min_dist = float('inf')
        closest_idx = 0
        
        # Course-grained search
        for idx in downsampled_indices:
            p = path[idx]
            dist = haversine_distance(s['lat'], s['lng'], p[0], p[1])
            if dist < min_dist:
                min_dist = dist
                closest_idx = idx
                
        # Fine-grained local search refinement (around closest course index)
        if min_dist <= max_distance * 1.5:  # buffer for course-grained search
            start_search = max(0, closest_idx - 15)
            end_search = min(len(path), closest_idx + 15)
            for idx in range(start_search, end_search):
                p = path[idx]
                dist = haversine_distance(s['lat'], s['lng'], p[0], p[1])
                if dist < min_dist:
                    min_dist = dist
                    closest_idx = idx
                    
            if min_dist <= max_distance:
                # Copy station dict and append route projection details
                station_copy = s.copy()
                station_copy['distance_to_route'] = min_dist
                station_copy['route_dist'] = cum_dist[closest_idx]
                route_stations.append(station_copy)
                
    # Sort stations by distance along the route
    route_stations.sort(key=lambda x: x['route_dist'])
    return route_stations, cum_dist[-1]

def optimize_fuel_stops(start_lat, start_lng, end_lat, end_lng, path, stations):
    """
    Solves the continuous fuel refueling optimization problem using LP Greedy algorithm.
    """
    # 1. Project stations onto route
    route_stations, total_route_miles = project_stations_to_route(path, stations)
    
    # 2. Add START and DESTINATION nodes
    nodes = []
    nodes.append({
        'id': 'START',
        'name': 'START',
        'route_dist': 0.0,
        'price': 999.0,  # Arbitrary high price so we never buy fuel at start (start is pre-filled)
        'lat': start_lat,
        'lng': start_lng,
        'city': 'Start',
        'state': 'US'
    })
    for s in route_stations:
        nodes.append(s)
    nodes.append({
        'id': 'DESTINATION',
        'name': 'DESTINATION',
        'route_dist': total_route_miles,
        'price': 999.0,  # Destination is not a gas station
        'lat': end_lat,
        'lng': end_lng,
        'city': 'End',
        'state': 'US'
    })
    
    N_nodes = len(nodes)
    
    # 3. Check reachability before proceeding
    for i in range(N_nodes - 1):
        gap = nodes[i+1]['route_dist'] - nodes[i]['route_dist']
        if gap > MAX_RANGE:
            raise ValueError(f"Route is unreachable: distance between fuel stops exceeds the vehicle's 500-mile range. Gap of {gap:.1f} miles between {nodes[i]['name']} and {nodes[i+1]['name']}.")
            
    # 4. Initialize purchases to stay above the lower bounds
    # L[j] is min cumulative fuel bought before reaching node j
    # U[j] is max cumulative fuel bought up to node j
    L = [0.0] * N_nodes
    U = [0.0] * N_nodes
    for j in range(1, N_nodes):
        L[j] = max(0.0, nodes[j]['route_dist'] / FUEL_EFFICIENCY - TANK_CAPACITY)
        U[j] = nodes[j]['route_dist'] / FUEL_EFFICIENCY
        
    x = [0.0] * N_nodes  # Purchases at each node
    X = [0.0] * N_nodes  # Cumulative purchases
    
    # Left-to-right pass to compute minimal valid purchases
    for i in range(1, N_nodes - 1):
        required = L[i+1]
        if X[i-1] < required:
            x[i] = required - X[i-1]
            X[i] = required
        else:
            x[i] = 0.0
            X[i] = X[i-1]
    X[-1] = X[-2]
    
    # 5. Right-to-left pass to shift purchases from expensive stations to cheaper ones
    for j in range(1, N_nodes - 1):
        if x[j] <= 0.0:
            continue
            
        # Find all cheaper preceding stations i < j
        cheaper_stations = []
        for i in range(1, j):
            if nodes[i]['price'] < nodes[j]['price']:
                cheaper_stations.append((nodes[i]['price'], i))
                
        # Sort cheaper stations by price (cheapest first)
        cheaper_stations.sort()
        
        for price_i, i in cheaper_stations:
            if x[j] <= 0.0:
                break
                
            # Compute max shift amount allowed by capacity bounds U
            max_shift = x[j]
            for k in range(i, j):
                max_shift = min(max_shift, U[k] - X[k])
                
            if max_shift > 0.0:
                x[j] -= max_shift
                x[i] += max_shift
                # Update cumulative purchases
                for k in range(i, j):
                    X[k] += max_shift
                    
    # 6. Filter final refueling stops
    stops = []
    total_cost = 0.0
    for i in range(1, N_nodes - 1):
        if x[i] > 0.0:
            cost = x[i] * nodes[i]['price']
            total_cost += cost
            stops.append({
                'id': nodes[i]['id'],
                'name': nodes[i]['name'],
                'address': nodes[i]['address'],
                'city': nodes[i]['city'],
                'state': nodes[i]['state'],
                'lat': nodes[i]['lat'],
                'lng': nodes[i]['lng'],
                'price': nodes[i]['price'],
                'distance_along_route': nodes[i]['route_dist'],
                'fuel_to_buy_gallons': x[i],
                'cost': cost
            })
            
    return stops, total_cost, total_route_miles
