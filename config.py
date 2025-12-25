import os
import json
import logging
from pathlib import Path
from typing import Dict, Union, Optional, Any, List
from dataclasses import dataclass
from timezonefinder import TimezoneFinder

logger = logging.getLogger(__name__)

# Initialize timezone finder (lazy singleton)
_tf: Optional[TimezoneFinder] = None

def get_timezone_from_coords(latitude: float, longitude: float) -> str:
    """Determine timezone from coordinates using timezonefinder"""
    global _tf
    if _tf is None:
        _tf = TimezoneFinder()

    tz = _tf.timezone_at(lat=latitude, lng=longitude)
    if tz is None:
        logger.warning(f"Could not determine timezone for ({latitude}, {longitude}), defaulting to UTC")
        return 'UTC'
    return tz


class WeatherBotError(Exception):
    """Base exception for weather bot errors"""
    pass


class ConfigurationError(WeatherBotError):
    """Raised when configuration is invalid or missing"""
    pass


@dataclass
class LocationConfig:
    """Configuration for a specific location"""
    name: str
    latitude: float
    longitude: float
    timezone: str = 'Australia/Perth'
    
    def __post_init__(self) -> None:
        """Validate location configuration after initialization"""
        if not -90 <= self.latitude <= 90:
            raise ConfigurationError(f"Invalid latitude: {self.latitude}. Must be between -90 and 90.")
        if not -180 <= self.longitude <= 180:
            raise ConfigurationError(f"Invalid longitude: {self.longitude}. Must be between -180 and 180.")
        if not self.name.strip():
            raise ConfigurationError("Location name cannot be empty")


@dataclass 
class WeatherBotConfig:
    """Main configuration for the weather bot"""
    current_location: LocationConfig
    locations: List[LocationConfig]
    openweather_api_key: str
    openai_api_key: str
    gemini_api_key: Optional[str] = None
    log_level: str = 'INFO'
    forecast_hours: int = 6
    max_report_words: int = 300
    
    def __post_init__(self) -> None:
        """Validate configuration after initialization"""
        if self.forecast_hours < 3 or self.forecast_hours > 24:
            raise ConfigurationError(f"forecast_hours must be between 3 and 24, got {self.forecast_hours}")
        if self.max_report_words < 100 or self.max_report_words > 1000:
            raise ConfigurationError(f"max_report_words must be between 100 and 1000, got {self.max_report_words}")
        if self.log_level not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            raise ConfigurationError(f"Invalid log_level: {self.log_level}")


def load_env_file() -> None:
    """Load environment variables from .env file if it exists"""
    env_file: Path = Path(__file__).parent / ".env"
    if env_file.exists():
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        # Only set if not already in environment
                        if key.strip() not in os.environ:
                            os.environ[key.strip()] = value.strip()
            logger.info("Loaded environment variables from .env file")
        except Exception as e:
            logger.warning(f"Failed to load .env file: {e}")


def load_location_config() -> LocationConfig:
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
                
        lat = float(location_data['latitude'])
        lon = float(location_data['longitude'])

        # Auto-detect timezone from coordinates if not provided
        tz = location_data.get('timezone')
        if not tz:
            tz = get_timezone_from_coords(lat, lon)
            logger.info(f"Auto-detected timezone: {tz}")

        return LocationConfig(
            name=location_data.get('location_name', 'Current Location'),
            latitude=lat,
            longitude=lon,
            timezone=tz
        )
    except FileNotFoundError:
        logger.warning("location.json not found, using Perth coordinates as fallback")
        return LocationConfig(
            name="Perth, Australia",
            latitude=-31.9544,
            longitude=115.8526,
            timezone='Australia/Perth'
        )
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in location.json: {e}")
        raise ConfigurationError(f"Invalid JSON in location.json: {e}") from e
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid location data: {e}")
        raise ConfigurationError(f"Invalid location data: {e}") from e


def load_locations_config() -> List[LocationConfig]:
    """Load multiple location configurations from JSON file"""
    locations_file: Path = Path(__file__).parent / "locations.json"
    if not locations_file.exists():
        # Return single location as fallback
        return [load_location_config()]
        
    try:
        with open(locations_file, 'r') as f:
            locations_data: Dict[str, Any] = json.load(f)
            
        if 'locations' not in locations_data:
            raise ConfigurationError("Missing 'locations' array in locations.json")
            
        locations: List[LocationConfig] = []
        for loc_data in locations_data['locations']:
            locations.append(LocationConfig(
                name=loc_data.get('name', 'Unknown Location'),
                latitude=float(loc_data['latitude']),
                longitude=float(loc_data['longitude']),
                timezone=loc_data.get('timezone', 'Australia/Perth')
            ))
            
        if not locations:
            raise ConfigurationError("No valid locations found in locations.json")
            
        return locations
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in locations.json: {e}")
        raise ConfigurationError(f"Invalid JSON in locations.json: {e}") from e
    except (ValueError, TypeError, KeyError) as e:
        logger.error(f"Invalid locations data: {e}")
        raise ConfigurationError(f"Invalid locations data: {e}") from e


def load_config() -> WeatherBotConfig:
    """Load complete configuration for the weather bot"""
    # Load environment variables from .env file first
    load_env_file()
    
    # Load location configuration
    current_location: LocationConfig = load_location_config()
    all_locations: List[LocationConfig] = load_locations_config()
    
    # Validate API keys
    openai_key: Optional[str] = os.getenv('OPENAI_API_KEY')
    if not openai_key:
        raise ConfigurationError("OpenAI API key not found in environment variables")
    
    openweather_key: Optional[str] = os.getenv('OPENWEATHER_API_KEY')
    if not openweather_key:
        raise ConfigurationError("OpenWeather API key not found in environment variables")
    
    gemini_key: Optional[str] = os.getenv('GEMINI_API_KEY')
    if not gemini_key:
        logger.warning("Gemini API key not found - image generation will be skipped")
    
    # Set OpenAI API key for llm library
    os.environ["OPENAI_API_KEY"] = openai_key
    
    # Load optional configuration settings
    log_level: str = os.getenv('LOG_LEVEL', 'INFO')
    forecast_hours: int = int(os.getenv('FORECAST_HOURS', '6'))
    max_report_words: int = int(os.getenv('MAX_REPORT_WORDS', '300'))

    return WeatherBotConfig(
        current_location=current_location,
        locations=all_locations,
        openweather_api_key=openweather_key,
        openai_api_key=openai_key,
        gemini_api_key=gemini_key,
        log_level=log_level,
        forecast_hours=forecast_hours,
        max_report_words=max_report_words
    )


def validate_api_keys() -> None:
    """Validate that all required API keys are present (legacy function for backward compatibility)"""
    config = load_config()
    logger.info("API keys validated successfully")