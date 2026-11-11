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

def test_rich_forecast_and_optional_measurements():
    service = WeatherService('fake', enable_cache=False)
    current = {'dt': 1800000000, 'main': {'temp': 22, 'feels_like': 23, 'humidity': 60},
               'weather': [{'description': 'cloudy'}], 'clouds': {'all': 80},
               'wind': {'speed': 5, 'gust': 8}, 'sys': {'sunrise': 1799990000, 'sunset': 1800010000}}
    periods = [dict(current, dt=1800000000 + i * 10800, pop=.4, rain={'3h': 1.2}) for i in range(20)]
    with patch.object(service, '_fetch_current_weather', return_value=current), patch.object(service, '_fetch_forecast', return_value={'list': periods}):
        result = service.get_weather_data(0, 0, 'Test')
    assert len(result['forecast']) == 16
    assert result['current_conditions']['is_day'] is True
    assert result['current_conditions']['rain_1h_mm'] is None
    assert result['forecast'][0]['precipitation_probability'] == .4
    assert result['forecast'][0]['rain_3h_mm'] == 1.2
    assert result['forecast'][0]['wind_speed_kmh'] == 18
    assert result['forecast'][0]['wind_gust_kmh'] == 28.8
    optional = service._format_forecast([{'dt': 1800000000, 'main': {'temp': 20}, 'weather': [{'description': 'clear sky'}]}])[0]
    assert optional['windSpeed'] is None
    assert optional['precipitation_probability'] is None
    assert optional['feels_like_c'] is None


def test_null_and_malformed_optional_fields_keep_forecast_period():
    service = WeatherService('fake', enable_cache=False)
    base = {'dt': 1800000000, 'main': {'temp': 20}, 'weather': [{'description': 'clear sky'}]}
    optional = dict(base, wind=None, clouds=None, rain=None, snow=None, pop=None)
    result = service._format_forecast([optional])[0]
    assert result['windSpeed'] is None
    assert result['rain_mm'] is None
    malformed = dict(base, wind={'speed': 'unknown', 'gust': float('nan')}, clouds={'all': 200}, pop=2)
    result = service._format_forecast([malformed])[0]
    assert result['windSpeed'] is None
    assert result['wind_gust_kmh'] is None
    assert result['cloud_cover_pct'] is None
    assert result['precipitation_probability'] is None
    current = service._format_current(dict(optional, sys=None))
    assert current['sunrise'] is None
    assert current['is_day'] is None


def test_configured_horizons_have_separate_cached_results(tmp_path):
    service = WeatherService('fake', enable_cache=True)
    service.cache = WeatherCache(cache_dir=tmp_path)
    current = {'dt': 1800000000, 'main': {'temp': 22}, 'weather': [{'description': 'clear sky'}]}
    periods = [dict(current, dt=1800000000 + i * 10800) for i in range(20)]
    with patch.object(service, '_fetch_current_weather', return_value=current) as fetch, patch.object(
            service, '_fetch_forecast', return_value={'list': periods}):
        day = service.get_weather_data(0, 0, 'Test', forecast_hours=24)
        two_days = service.get_weather_data(0, 0, 'Test', forecast_hours=48)
        cached_day = service.get_weather_data(0, 0, 'Test', forecast_hours=24)
        assert len(day['forecast']) == 8
        assert len(two_days['forecast']) == 16
        assert cached_day == day
        assert fetch.call_count == 2


def test_service_rejects_unsupported_forecast_horizon():
    import pytest
    service = WeatherService('fake', enable_cache=False)
    for hours in (0, 2, 49, 3.5, True):
        with pytest.raises(ValueError, match='forecast_hours'):
            service.get_weather_data(0, 0, 'Test', forecast_hours=hours)
