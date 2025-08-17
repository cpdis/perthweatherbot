import unittest
import tempfile
import json
import os
from pathlib import Path
from unittest.mock import patch, mock_open

from config import (
    LocationConfig, WeatherBotConfig, ConfigurationError,
    load_location_config, load_locations_config, load_config, load_env_file
)


class TestLocationConfig(unittest.TestCase):
    
    def test_valid_location_config(self):
        """Test creating a valid location configuration"""
        location = LocationConfig("Perth", -31.9544, 115.8526)
        self.assertEqual(location.name, "Perth")
        self.assertEqual(location.latitude, -31.9544)
        self.assertEqual(location.longitude, 115.8526)
        self.assertEqual(location.timezone, "Australia/Perth")
    
    def test_invalid_latitude(self):
        """Test that invalid latitude raises error"""
        with self.assertRaises(ConfigurationError):
            LocationConfig("Invalid", -100, 115.8526)
        
        with self.assertRaises(ConfigurationError):
            LocationConfig("Invalid", 100, 115.8526)
    
    def test_invalid_longitude(self):
        """Test that invalid longitude raises error"""
        with self.assertRaises(ConfigurationError):
            LocationConfig("Invalid", -31.9544, -200)
        
        with self.assertRaises(ConfigurationError):
            LocationConfig("Invalid", -31.9544, 200)
    
    def test_empty_name(self):
        """Test that empty name raises error"""
        with self.assertRaises(ConfigurationError):
            LocationConfig("", -31.9544, 115.8526)


class TestWeatherBotConfig(unittest.TestCase):
    
    def setUp(self):
        self.location = LocationConfig("Perth", -31.9544, 115.8526)
        
    def test_valid_config(self):
        """Test creating a valid weather bot configuration"""
        config = WeatherBotConfig(
            current_location=self.location,
            locations=[self.location],
            openweather_api_key="test_key",
            openai_api_key="test_key"
        )
        self.assertEqual(config.current_location, self.location)
        self.assertEqual(config.log_level, "INFO")
        self.assertEqual(config.forecast_hours, 6)
    
    def test_invalid_forecast_hours(self):
        """Test that invalid forecast hours raises error"""
        with self.assertRaises(ConfigurationError):
            WeatherBotConfig(
                current_location=self.location,
                locations=[self.location],
                openweather_api_key="test_key",
                openai_api_key="test_key",
                forecast_hours=1  # Too low
            )
    
    def test_invalid_log_level(self):
        """Test that invalid log level raises error"""
        with self.assertRaises(ConfigurationError):
            WeatherBotConfig(
                current_location=self.location,
                locations=[self.location],
                openweather_api_key="test_key",
                openai_api_key="test_key",
                log_level="INVALID"
            )


class TestConfigLoading(unittest.TestCase):
    
    def test_load_location_config_file_not_found(self):
        """Test loading location config when file doesn't exist"""
        with patch('config.Path') as mock_path:
            mock_path.return_value.__truediv__.return_value.exists.return_value = False
            mock_path.return_value.__truediv__.return_value.__str__.return_value = "/fake/path"
            
            # Mock the file open to raise FileNotFoundError
            with patch('builtins.open', side_effect=FileNotFoundError):
                location = load_location_config()
                self.assertEqual(location.name, "Perth, Australia")
                self.assertEqual(location.latitude, -31.9544)
    
    def test_load_location_config_valid_json(self):
        """Test loading valid location configuration"""
        test_data = {
            "latitude": -32.0,
            "longitude": 116.0,
            "location_name": "Test Location",
            "timezone": "Australia/Perth"
        }
        
        with patch('builtins.open', mock_open(read_data=json.dumps(test_data))):
            with patch('config.Path'):
                location = load_location_config()
                self.assertEqual(location.name, "Test Location")
                self.assertEqual(location.latitude, -32.0)
                self.assertEqual(location.longitude, 116.0)
    
    def test_load_env_file(self):
        """Test loading environment variables from .env file"""
        env_content = "TEST_VAR=test_value\n# Comment\nANOTHER_VAR=another_value"
        
        with patch('builtins.open', mock_open(read_data=env_content)):
            with patch('config.Path') as mock_path:
                mock_path.return_value.__truediv__.return_value.exists.return_value = True
                
                # Clear any existing env vars
                if 'TEST_VAR' in os.environ:
                    del os.environ['TEST_VAR']
                if 'ANOTHER_VAR' in os.environ:
                    del os.environ['ANOTHER_VAR']
                
                load_env_file()
                
                self.assertEqual(os.environ.get('TEST_VAR'), 'test_value')
                self.assertEqual(os.environ.get('ANOTHER_VAR'), 'another_value')


if __name__ == '__main__':
    unittest.main()