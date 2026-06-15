from django.http import JsonResponse
from django.shortcuts import render
from .services.routing import geocode, get_route
from .services.optimizer import optimize_fuel_stops
from .services.fuel_data import get_stations, get_all_cities

def route_api(request):
    """
    JSON API endpoint to fetch route details and optimized fuel stops.
    Example: /api/route/?start=Houston,TX&end=Atlanta,GA
    """
    start_query = request.GET.get('start')
    end_query = request.GET.get('end')
    
    if not start_query or not end_query:
        return JsonResponse({'error': 'Both "start" and "end" query parameters are required.'}, status=400)
        
    try:
        # 1. Geocode locations
        start_coords = geocode(start_query)
        if not start_coords:
            return JsonResponse({'error': f'Could not geocode start location: "{start_query}". Please check the spelling or specify a valid U.S. city (e.g. "Houston, TX").'}, status=400)
            
        end_coords = geocode(end_query)
        if not end_coords:
            return JsonResponse({'error': f'Could not geocode finish location: "{end_query}". Please check the spelling or specify a valid U.S. city (e.g. "Atlanta, GA").'}, status=400)
            
        # 2. Fetch OSRM route details
        total_dist_miles, path = get_route(start_coords[0], start_coords[1], end_coords[0], end_coords[1])
        if not path:
            return JsonResponse({'error': 'Failed to calculate route between the specified locations.'}, status=500)
            
        # 3. Retrieve global cached stations list
        stations = get_stations()
        
        # 4. Optimize fuel stops
        stops, total_cost, total_dist_miles = optimize_fuel_stops(
            start_coords[0], start_coords[1],
            end_coords[0], end_coords[1],
            path, stations
        )
        
        # 5. Return success JSON
        return JsonResponse({
            'start_name': start_query,
            'end_name': end_query,
            'start_coordinates': [start_coords[0], start_coords[1]],
            'end_coordinates': [end_coords[0], end_coords[1]],
            'total_distance_miles': total_dist_miles,
            'total_fuel_cost': total_cost,
            'refuel_stops': stops,
            'route_geometry': path
        })
        
    except ValueError as val_err:
        # Catch range/unreachable route exception and return as validation error
        return JsonResponse({'error': str(val_err)}, status=400)
    except Exception as e:
        # Catch unexpected server exceptions
        return JsonResponse({'error': f'An unexpected error occurred: {str(e)}'}, status=500)

def map_view(request):
    """
    HTML view rendering the Leaflet map interface.
    """
    start = request.GET.get('start', 'Houston, TX')
    end = request.GET.get('end', 'Atlanta, GA')
    
    return render(request, 'fuel_planner/map.html', {
        'start': start,
        'end': end
    })

def cities_api(request):
    """
    JSON API endpoint to get the list of all U.S. cities for autocomplete dropdowns.
    """
    try:
        cities = get_all_cities()
        return JsonResponse(cities, safe=False)
    except Exception as e:
        return JsonResponse({'error': f'Failed to load cities: {str(e)}'}, status=500)
