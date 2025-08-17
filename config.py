import os
import json
import logging
from pathlib import Path
from typing import Dict, Union, Optional, Any

logger = logging.getLogger(__name__)


class WeatherBotError(Exception):
    """Base exception for weather bot errors"""
    pass


class ConfigurationError(WeatherBotError):
    """Raised when configuration is invalid or missing"""
    pass


def load_location_config() -> Dict[str, Union[float, str]]:
    """Load location configuration from JSON file"""
    location_file: Path = Path(__file__).parent / "location.json"
    try:
        with open(location_file, 'r') as f:
            location_data: Dict[str, Any] = json.load(f)
            
        # Validate required fields
        required_fields = ['latitude', 'longitude']
        for field in required_fields:
            if field not in location_data:
                raise ConfigurationError(f"Missing required field '{field}' in location.json")
                
        return {
            'latitude': float(location_data['latitude']),
            'longitude': float(location_data['longitude']),
            'location_name': location_data.get('location_name', 'Current Location')
        }
    except FileNotFoundError:
        logger.warning("location.json not found, using Perth coordinates as fallback")
        return {
            'latitude': -31.9544,
            'longitude': 115.8526,
            'location_name': "Perth, Australia"
        }
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in location.json: {e}")
        raise ConfigurationError(f"Invalid JSON in location.json: {e}") from e
    except (ValueError, KeyError) as e:
        logger.error(f"Invalid location data: {e}")
        raise ConfigurationError(f"Invalid location data: {e}") from e


def validate_api_keys() -> None:
    """Validate that all required API keys are present"""
    openai_key: Optional[str] = os.getenv('OPENAI_API_KEY')
    if not openai_key:
        raise ConfigurationError("OpenAI API key not found in environment variables")
    
    openweather_key: Optional[str] = os.getenv('OPENWEATHER_API_KEY')
    if not openweather_key:
        raise ConfigurationError("OpenWeather API key not found in environment variables")
    
    elevenlabs_key: Optional[str] = os.getenv('ELEVENLABS_API_KEY')
    if not elevenlabs_key:
        logger.warning("ElevenLabs API key not found - audio generation will be skipped")
    
    # Set OpenAI API key for llm library
    os.environ["OPENAI_API_KEY"] = openai_key