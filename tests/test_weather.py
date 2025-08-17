import unittest
from unittest.mock import patch, MagicMock
import json
import requests

from weather import WeatherService, APIError
from cache import WeatherCache


class TestWeatherService(unittest.TestCase):
    
    def setUp(self):
        self.api_key = "test_api_key"
        self.service = WeatherService(self.api_key, enable_cache=False)
        
    def test_celsius_to_fahrenheit(self):
        """Test temperature conversion"""
        self.assertEqual(self.service._celsius_to_fahrenheit(0), 32)
        self.assertEqual(self.service._celsius_to_fahrenheit(100), 212)
        self.assertIsNone(self.service._celsius_to_fahrenheit(None))
    
    def test_ms_to_mph(self):
        """Test wind speed conversion"""
        result = self.service._ms_to_mph(10)
        self.assertAlmostEqual(result, 22.37, places=2)
        self.assertIsNone(self.service._ms_to_mph(None))
    
    def test_format_forecast(self):
        """Test forecast formatting"""
        test_periods = [
            {
                'dt': 1692360000,  # Unix timestamp
                'main': {'temp': 20.5},
                'wind': {'speed': 5.0, 'deg': 180},
                'weather': [{'description': 'clear sky'}]
            }
        ]
        
        result = self.service._format_forecast(test_periods)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['temperature'], 20.5)
        self.assertEqual(result[0]['shortForecast'], 'clear sky')
        self.assertIn('startTime', result[0])
    
    def test_format_forecast_malformed_data(self):
        """Test forecast formatting with malformed data"""
        test_periods = [
            {'dt': 1692360000, 'main': {'temp': 20.5}},  # Missing wind data
            {
                'dt': 1692360000,
                'main': {'temp': 25.0},
                'wind': {'speed': 3.0, 'deg': 90},
                'weather': [{'description': 'sunny'}]
            }
        ]
        
        with patch('weather.logger'):
            result = self.service._format_forecast(test_periods)
            # Should only return the valid period
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['temperature'], 25.0)
    
    @patch('weather.requests.get')
    def test_get_weather_data_success(self, mock_get):
        """Test successful weather data retrieval"""
        # Mock API responses
        current_response = MagicMock()
        current_response.json.return_value = {
            'sys': {'country': 'AU'},
            'dt': 1692360000,
            'main': {'temp': 20.5, 'humidity': 65},
            'wind': {'speed': 5.0, 'deg': 180},
            'weather': [{'description': 'clear sky'}]
        }
        
        forecast_response = MagicMock()
        forecast_response.json.return_value = {
            'list': [
                {
                    'dt': 1692363600,
                    'main': {'temp': 22.0},
                    'wind': {'speed': 4.0, 'deg': 170},
                    'weather': [{'description': 'partly cloudy'}]
                }
            ]
        }
        
        mock_get.side_effect = [current_response, forecast_response]
        
        result = self.service.get_weather_data(-31.9544, 115.8526, "Perth")
        
        self.assertIsNotNone(result)
        self.assertEqual(result['location']['name'], "Perth")
        self.assertEqual(result['current_conditions']['temperature_c'], 20.5)
        self.assertEqual(len(result['forecast']), 1)
    
    @patch('weather.requests.get')
    def test_get_weather_data_api_error(self, mock_get):
        """Test weather data retrieval with API error"""
        mock_get.side_effect = requests.exceptions.RequestException("API Error")
        
        with self.assertRaises(APIError):
            self.service.get_weather_data(-31.9544, 115.8526, "Perth")
    
    def test_weather_service_with_cache(self):
        """Test weather service with caching enabled"""
        service_with_cache = WeatherService(self.api_key, enable_cache=True, cache_ttl=60)
        self.assertIsNotNone(service_with_cache.cache)
        self.assertEqual(service_with_cache.cache.default_ttl, 60)


if __name__ == '__main__':
    unittest.main()