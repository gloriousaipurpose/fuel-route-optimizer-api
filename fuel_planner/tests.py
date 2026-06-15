from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch
from .services.optimizer import haversine_distance, optimize_fuel_stops
from .services.fuel_data import get_stations

class FuelPlannerTests(TestCase):
    
    def test_haversine_distance(self):
        """
        Verify that Haversine distance matches expected values (e.g., Houston to Atlanta).
        """
        houston = (29.7589382, -95.3676974)
        atlanta = (33.7544657, -84.3898151)
        dist = haversine_distance(houston[0], houston[1], atlanta[0], atlanta[1])
        self.assertAlmostEqual(dist, 700.0, delta=50.0)  # rough geographical distance check

    def test_gas_stations_data(self):
        """
        Ensure stations database loaded from CSV contains US-only stations.
        """
        stations = get_stations()
        self.assertGreater(len(stations), 7000)
        
        # Check that none of the stations belong to Canadian provinces
        canada_provinces = {'AB', 'BC', 'MB', 'NB', 'NL', 'NS', 'NT', 'NU', 'ON', 'PE', 'QC', 'SK', 'YT'}
        for s in stations:
            self.assertNotIn(s['state'].upper(), canada_provinces)
            
        # Verify every station has valid coordinates
        for s in stations:
            self.assertTrue(-180 <= s['lng'] <= 180, f"Invalid longitude for {s['name']}")
            self.assertTrue(-90 <= s['lat'] <= 90, f"Invalid latitude for {s['name']}")

    def test_optimizer_logic(self):
        """
        Tests the mathematical correctness of our LP optimizer.
        """
        # Create a dense route of 600 miles with 601 points (1 point per mile)
        mock_path = []
        for i in range(601):
            lat = 0.0
            lng = i * (8.7 / 600.0)  # 8.7 degrees longitude total
            mock_path.append((lat, lng))
            
        mock_stations = [
            # Station at 100 miles, price $3.30
            {
                'id': 'S1',
                'name': 'Station 1',
                'address': '100 Hwy',
                'city': 'City 1',
                'state': 'US',
                'lat': 0.0,
                'lng': 100 * (8.7 / 600.0),
                'price': 3.30
            },
            # Station at 250 miles, price $2.50 (very cheap)
            {
                'id': 'S2',
                'name': 'Station 2',
                'address': '250 Hwy',
                'city': 'City 2',
                'state': 'US',
                'lat': 0.0,
                'lng': 250 * (8.7 / 600.0),
                'price': 2.50
            },
            # Station at 400 miles, price $3.40
            {
                'id': 'S3',
                'name': 'Station 3',
                'address': '400 Hwy',
                'city': 'City 3',
                'state': 'US',
                'lat': 0.0,
                'lng': 400 * (8.7 / 600.0),
                'price': 3.40
            }
        ]
        
        stops, total_cost, total_dist = optimize_fuel_stops(0.0, 0.0, 0.0, 8.7, mock_path, mock_stations)
        
        # Verify route distance is ~600
        self.assertAlmostEqual(total_dist, 600.0, delta=10.0)
        
        # We start with 500 miles range. We can easily reach Station 2 (250 miles).
        # Remaining distance is 350 miles. We buy 10 gallons at Station 2 ($2.50) = $25.00
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0]['id'], 'S2')
        self.assertAlmostEqual(stops[0]['fuel_to_buy_gallons'], 10.0, delta=1.0)
        self.assertAlmostEqual(total_cost, 25.0, delta=2.5)

    def test_optimizer_unreachable_exception(self):
        """
        Verify that optimizer raises a ValueError if there is an unreachable gap (>500 miles).
        """
        mock_path = []
        for i in range(601):
            lat = 0.0
            lng = i * (8.7 / 600.0)
            mock_path.append((lat, lng))
            
        with self.assertRaises(ValueError):
            optimize_fuel_stops(0.0, 0.0, 0.0, 8.7, mock_path, [])

    @patch('fuel_planner.views.geocode')
    @patch('fuel_planner.views.get_route')
    def test_api_view_success(self, mock_get_route, mock_geocode):
        """
        Verify that the route API returns correct JSON format and status.
        """
        # Setup mocks: mock a 300-mile route so it doesn't need to refuel and is reachable
        mock_geocode.side_effect = lambda q: (29.7, -95.3) if 'Houston' in q else (30.0, -90.0)
        mock_get_route.return_value = (300.0, [(29.7, -95.3), (30.0, -90.0)])
        
        client = Client()
        response = client.get(reverse('route_api'), {'start': 'Houston, TX', 'end': 'New Orleans, LA'})
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('start_name', data)
        self.assertIn('end_name', data)
        self.assertIn('total_fuel_cost', data)
        self.assertIn('refuel_stops', data)
        self.assertIn('route_geometry', data)
        
    @patch('fuel_planner.views.geocode')
    def test_api_view_validation_error(self, mock_geocode):
        """
        Verify geocoding failure returns a 400 Bad Request.
        """
        mock_geocode.return_value = None
        
        client = Client()
        response = client.get(reverse('route_api'), {'start': 'NonexistentCity', 'end': 'Atlanta, GA'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    def test_geocode_foreign_city(self):
        """
        Verify that geocoding a foreign city raises a ValueError or rejects it.
        """
        from .services.routing import geocode
        
        # Geocoding Mumbai, India should raise ValueError
        with self.assertRaises(ValueError) as ctx:
            geocode("Mumbai, India")
        self.assertIn("outside the USA", str(ctx.exception))
        
        with self.assertRaises(ValueError) as ctx:
            geocode("Toronto, Canada")
        self.assertIn("outside the USA", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            geocode("Paris, France")
        self.assertIn("outside the USA", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            geocode("Mumbai")
        self.assertIn("outside the USA", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            geocode("Toronto")
        self.assertIn("outside the USA", str(ctx.exception))

    def test_lookup_city_coords(self):
        """
        Verify that lookup_city_coords correctly resolves both regular and override U.S. cities offline.
        """
        from .services.fuel_data import lookup_city_coords
        
        # Test standard city from database
        houston_coords = lookup_city_coords("Houston, TX")
        self.assertIsNotNone(houston_coords)
        self.assertAlmostEqual(houston_coords[0], 29.76, delta=0.5)
        
        # Test unmatched override city
        override_coords = lookup_city_coords("brookpark, OH")
        self.assertIsNotNone(override_coords)
        self.assertAlmostEqual(override_coords[0], 41.3995, delta=0.01)
        
        # Test invalid queries
        self.assertIsNone(lookup_city_coords(""))
        self.assertIsNone(lookup_city_coords("Houston"))
        self.assertIsNone(lookup_city_coords("Nonexistent, ZZ"))

    @patch('urllib.request.urlopen')
    def test_geocode_offline(self, mock_urlopen):
        """
        Verify that geocode uses the offline database and bypasses Nominatim for matched cities.
        """
        from .services.routing import geocode
        
        # Geocode a valid city, which should return coordinates offline without calling urlopen
        coords = geocode("Atlanta, GA")
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords[0], 33.75, delta=0.5)
        mock_urlopen.assert_not_called()

    def test_cities_api(self):
        """
        Verify that the cities API endpoint returns the full list of U.S. cities.
        """
        client = Client()
        response = client.get(reverse('cities_api'))
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 20000) # Check that the entire list of ~29k cities is loaded
        
        # Verify formatting
        self.assertIn("Houston, TX", data)
        self.assertIn("Adak, AK", data)
