import requests
import json
import logging
from datetime import datetime, timezone as tz
from typing import Dict, List, Optional, Any
from config import WeatherBotError
from cache import WeatherCache
from utils import retry_with_backoff, RateLimiter, create_cache_key, log_performance

logger = logging.getLogger(__name__)


class APIError(WeatherBotError):
    """Raised when API calls fail"""
    pass


class WeatherService:
    def __init__(self, api_key: str, enable_cache: bool = True, cache_ttl: int = 300) -> None:
        self.base_url: str = "https://api.openweathermap.org/data/2.5"
        self.api_key: str = api_key
        self.cache: Optional[WeatherCache] = WeatherCache(default_ttl=cache_ttl) if enable_cache else None
        self.rate_limiter: RateLimiter = RateLimiter(calls_per_minute=60)  # OpenWeather free tier limit

    @log_performance
    def get_weather_data(self, latitude: float, longitude: float, location_name: str) -> Dict[str, Any]:
        """
        Fetches weather data from OpenWeather API for a specific latitude/longitude
        
        Args:
            latitude (float): Latitude coordinate
            longitude (float): Longitude coordinate
            location_name (str): Custom location name
            
        Returns:
            dict: Dictionary containing weather data and forecast
        """
        # Check cache first
        cache_key = create_cache_key(latitude, longitude)
        if self.cache:
            cached_data = self.cache.get(cache_key)
            if cached_data:
                logger.info(f"Using cached weather data for {location_name}")
                return cached_data
        
        try:
            # Rate limit API calls
            self.rate_limiter.wait_if_needed()
            
            # Get current weather with retry
            current_data = self._fetch_current_weather(latitude, longitude)
            
            # Get forecast with retry
            forecast_data = self._fetch_forecast(latitude, longitude)
            
            # Format the response
            weather_data = {
                'location': {
                    'name': location_name,
                    'country': current_data['sys']['country'],
                    'latitude': latitude,
                    'longitude': longitude
                },
                'current_conditions': {
                    'timestamp': datetime.fromtimestamp(current_data['dt'], tz.utc).isoformat(),
                    'temperature_c': current_data['main']['temp'],
                    'temperature_f': self._celsius_to_fahrenheit(current_data['main']['temp']),
                    'humidity': current_data['main']['humidity'],
                    'wind_speed_mph': self._ms_to_mph(current_data['wind']['speed']),
                    'wind_direction': current_data['wind']['deg'],
                    'description': current_data['weather'][0]['description']
                },
                'forecast': self._format_forecast(forecast_data['list'][:2])  # Next 6 hours of forecast
            }
            
            # Cache the successful response
            if self.cache:
                self.cache.set(cache_key, weather_data)
                logger.debug(f"Cached weather data for {location_name}")
            
            return weather_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching weather data: {e}")
            raise APIError(f"Failed to fetch weather data: {e}") from e
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.error(f"Error parsing weather data: {e}")
            raise APIError(f"Failed to parse weather data: {e}") from e
    
    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def _fetch_current_weather(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """Fetch current weather data with retry logic"""
        url = f"{self.base_url}/weather?lat={latitude}&lon={longitude}&appid={self.api_key}&units=metric"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    
    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def _fetch_forecast(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """Fetch forecast data with retry logic"""
        url = f"{self.base_url}/forecast?lat={latitude}&lon={longitude}&appid={self.api_key}&units=metric"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    
    def _celsius_to_fahrenheit(self, celsius: Optional[float]) -> Optional[float]:
        """Convert Celsius to Fahrenheit"""
        return None if celsius is None else (celsius * 9/5) + 32
    
    def _ms_to_mph(self, meters_per_second: Optional[float]) -> Optional[float]:
        """Convert meters per second to miles per hour"""
        return None if meters_per_second is None else meters_per_second * 2.237

    def _format_forecast(self, forecast_periods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format the forecast data from OpenWeather API"""
        formatted_periods: List[Dict[str, Any]] = []
        for period in forecast_periods:
            try:
                formatted_periods.append({
                    'startTime': datetime.fromtimestamp(period['dt'], tz.utc).isoformat(),
                    'temperature': period['main']['temp'],
                    'windSpeed': self._ms_to_mph(period['wind']['speed']),
                    'windDirection': period['wind']['deg'],
                    'shortForecast': period['weather'][0]['description']
                })
            except (KeyError, IndexError) as e:
                logger.warning(f"Skipping malformed forecast period: {e}")
                continue
        return formatted_periods
    
    def cleanup_cache(self) -> None:
        """Clean up expired cache entries"""
        if self.cache:
            self.cache.cleanup_expired()