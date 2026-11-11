import requests
import math
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
    def get_weather_data(self, latitude: float, longitude: float, location_name: str, forecast_hours: int = 48) -> Dict[str, Any]:
        """
        Fetches weather data from OpenWeather API for a specific latitude/longitude
        
        Args:
            latitude (float): Latitude coordinate
            longitude (float): Longitude coordinate
            location_name (str): Custom location name
            forecast_hours (int): 3–48 hours, rounded up to three-hour periods
            
        Returns:
            dict: Dictionary containing weather data and forecast
        """
        # Check cache first
        if not isinstance(forecast_hours, int) or isinstance(forecast_hours, bool) or not 3 <= forecast_hours <= 48:
            raise ValueError('forecast_hours must be an integer between 3 and 48')
        cache_key = f'v2_{forecast_hours}h_' + create_cache_key(latitude, longitude)
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
                    'country': self._optional_object(current_data, 'sys').get('country'),
                    'latitude': latitude,
                    'longitude': longitude
                },
                'current_conditions': self._format_current(current_data),
                # Round up to the provider's three-hour resolution.
                'forecast': self._format_forecast(forecast_data['list'][:math.ceil(forecast_hours / 3)]),
                'source': 'OpenWeather',
                'retrieved_at': datetime.now(tz.utc).isoformat()

            }
            
            # Cache the successful response
            if self.cache:
                self.cache.set(cache_key, weather_data)
                logger.debug(f"Cached weather data for {location_name}")
            
            return weather_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching weather data: {e}")
            raise APIError(f"Failed to fetch weather data: {e}") from e
        except (KeyError, IndexError, TypeError, ValueError) as e:
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

    @staticmethod
    def _optional_object(data, key):
        value = data.get(key)
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _optional_number(value, minimum=None, maximum=None):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None
        if minimum is not None and value < minimum:
            return None
        if maximum is not None and value > maximum:
            return None
        return value

    def _measurements(self, data, hours):
        main = self._optional_object(data, 'main')
        wind = self._optional_object(data, 'wind')
        speed = self._optional_number(wind.get('speed'), 0)
        gust = self._optional_number(wind.get('gust'), 0)
        pop = self._optional_number(data.get('pop'), 0, 1)
        return {
            'feels_like_c': self._optional_number(main.get('feels_like')),
            'humidity': self._optional_number(main.get('humidity'), 0, 100),
            'cloud_cover_pct': self._optional_number(self._optional_object(data, 'clouds').get('all'), 0, 100),
            'wind_speed_kmh': speed * 3.6 if speed is not None else None,
            'wind_gust_kmh': gust * 3.6 if gust is not None else None,
            'wind_gust_mph': self._ms_to_mph(gust),
            'precipitation_probability': pop,
            'precipitation_probability_pct': pop * 100 if pop is not None else None,
            'rain_mm': self._optional_number(self._optional_object(data, 'rain').get(f'{hours}h'), 0),
            'snow_mm': self._optional_number(self._optional_object(data, 'snow').get(f'{hours}h'), 0),
            f'rain_{hours}h_mm': self._optional_number(self._optional_object(data, 'rain').get(f'{hours}h'), 0),
            f'snow_{hours}h_mm': self._optional_number(self._optional_object(data, 'snow').get(f'{hours}h'), 0),
        }

    def _format_current(self, data):
        sunrise = self._optional_number(self._optional_object(data, 'sys').get('sunrise'), 0, 253402300799)
        sunset = self._optional_number(self._optional_object(data, 'sys').get('sunset'), 0, 253402300799)
        return {
            **self._measurements(data, 1),
            'timestamp': datetime.fromtimestamp(data['dt'], tz.utc).isoformat(),
            'temperature_c': data['main']['temp'],
            'temperature_f': self._celsius_to_fahrenheit(data['main']['temp']),
            'wind_speed_mph': self._ms_to_mph(self._optional_number(self._optional_object(data, 'wind').get('speed'), 0)),
            'wind_direction': self._optional_number(self._optional_object(data, 'wind').get('deg'), 0, 360),
            'description': data['weather'][0]['description'],
            'sunrise': datetime.fromtimestamp(sunrise, tz.utc).isoformat() if sunrise else None,
            'sunset': datetime.fromtimestamp(sunset, tz.utc).isoformat() if sunset else None,
            'is_day': sunrise <= data['dt'] < sunset if sunrise and sunset else None,
        }

    def _format_forecast(self, forecast_periods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Keep optional measurements unknown; do not turn absent rain into zero."""
        periods = []
        for period in forecast_periods:
            try:
                if not isinstance(period, dict):
                    raise ValueError('Forecast period is not an object')
                periods.append({
                    **self._measurements(period, 3),
                    'startTime': datetime.fromtimestamp(period['dt'], tz.utc).isoformat(),
                    'temperature': period['main']['temp'],
                    'windSpeed': self._ms_to_mph(self._optional_number(self._optional_object(period, 'wind').get('speed'), 0)),
                    'windDirection': self._optional_number(self._optional_object(period, 'wind').get('deg'), 0, 360),
                    'shortForecast': period['weather'][0]['description'],
                })
            except (KeyError, IndexError, TypeError, ValueError) as error:
                logger.warning('Skipping malformed forecast period: %s', error)
        if not periods:
            raise APIError('No usable forecast periods received')
        return periods

    def cleanup_cache(self) -> None:
        """Clean up expired cache entries"""
        if self.cache:
            self.cache.cleanup_expired()