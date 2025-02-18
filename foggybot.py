import requests
import json
from datetime import datetime
import llm
import re
from pytz import timezone
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

class WeatherService:
    def __init__(self):
        self.base_url = "https://api.openweathermap.org/data/2.5"
        self.api_key = os.getenv('OPENWEATHER_API_KEY')
        if not self.api_key:
            raise ValueError("OpenWeather API key not found in environment variables")

    def get_weather_data(self, latitude: float, longitude: float) -> dict:
        """
        Fetches weather data from OpenWeather API for a specific latitude/longitude
        
        Args:
            latitude (float): Latitude coordinate
            longitude (float): Longitude coordinate
            
        Returns:
            dict: Dictionary containing weather data and forecast
        """
        try:
            # Get current weather
            current_weather_url = f"{self.base_url}/weather?lat={latitude}&lon={longitude}&appid={self.api_key}&units=metric"
            current_response = requests.get(current_weather_url)
            current_response.raise_for_status()
            current_data = current_response.json()
            
            # Get forecast
            forecast_url = f"{self.base_url}/forecast?lat={latitude}&lon={longitude}&appid={self.api_key}&units=metric"
            forecast_response = requests.get(forecast_url)
            forecast_response.raise_for_status()
            forecast_data = forecast_response.json()
            
            # Format the response
            weather_data = {
                'location': {
                    'name': current_data['name'],
                    'country': current_data['sys']['country'],
                    'latitude': latitude,
                    'longitude': longitude
                },
                'current_conditions': {
                    'timestamp': datetime.utcfromtimestamp(current_data['dt']).isoformat(),
                    'temperature_c': current_data['main']['temp'],
                    'temperature_f': self._celsius_to_fahrenheit(current_data['main']['temp']),
                    'humidity': current_data['main']['humidity'],
                    'wind_speed_mph': self._ms_to_mph(current_data['wind']['speed']),
                    'wind_direction': current_data['wind']['deg'],
                    'description': current_data['weather'][0]['description']
                },
                'forecast': self._format_forecast(forecast_data['list'][:2])  # Next 6 hours of forecast
            }
            
            return weather_data
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching weather data: {e}")
            return None
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            print(f"Error parsing weather data: {e}")
            return None
    
    def _celsius_to_fahrenheit(self, celsius):
        """Convert Celsius to Fahrenheit"""
        return None if celsius is None else (celsius * 9/5) + 32
    
    def _ms_to_mph(self, meters_per_second):
        """Convert meters per second to miles per hour"""
        return None if meters_per_second is None else meters_per_second * 2.237

    def _format_forecast(self, forecast_periods):
        """Format the forecast data from OpenWeather API"""
        formatted_periods = []
        for period in forecast_periods:
            formatted_periods.append({
                'startTime': datetime.utcfromtimestamp(period['dt']).isoformat(),
                'temperature': period['main']['temp'],
                'windSpeed': self._ms_to_mph(period['wind']['speed']),
                'windDirection': period['wind']['deg'],
                'shortForecast': period['weather'][0]['description']
            })
        return formatted_periods

if __name__ == "__main__":
    # Perth, Australia coordinates
    PERTH_LAT = -31.9544
    PERTH_LON = 115.8526
    
    # Configure OpenAI API key for llm
    os.environ["OPENAI_API_KEY"] = os.getenv('OPENAI_API_KEY')
    if not os.getenv('OPENAI_API_KEY'):
        raise ValueError("OpenAI API key not found in environment variables")
    
    weather = WeatherService()
    weather_data = weather.get_weather_data(PERTH_LAT, PERTH_LON)
    
    if weather_data:
        forecasts = "Below is the weather forecast for Perth, Australia: \n"
        for period in weather_data['forecast']:
            forecasts = forecasts + "\n - " + period['startTime'] + ": " + period['shortForecast']

        # Convert the current time to Perth time
        perth_tz = timezone('Australia/Perth')
        perth_time = datetime.now(perth_tz).strftime("%Y-%m-%d %H:%M:%S")

        forecasts += f"\n\nCurrent local time: {perth_time}"
        
        forecasts += "\n\nReview the weather forecast and assess the weather, specifically looking for where any fog is, the clarity of the day, and more.\n\nConsidering the weather forecast, please write a weather report for Perth, Australia capturing the current conditions; the expected weather for the day; how pleasant or unpleasant it looks; how foggy it is and/or where the marine layer is; how one might best dress for the weather; and what one might do given the conditions, day, and time. Remember: you will generate this report many times a day, your recommended activities should be relatively mundane and not too cliche or stereotypical."

        forecasts += "\n\nDo not use headers or other formatting in your response. Just write one to two single paragraphs that are elegant, don't use bullet points or exclamation marks, and use emotive words more often than numbers and figures – but don't be flowery. You write like a novelist describing the scene, producing a work suitable for someone calmly reading it on a classical radio station between songs. With a style somewhere between Jack Kerouac and J. Peterman."

        forecasts += "\n\nRemember to keep the response under 500 words."

        forecasts += "\n\nAfter the weather report, please put an HTML color code that best represents the weather forecast, time of day."

        model = llm.get_model("gpt-4o")
        response = model.prompt(
            forecasts,
            attachments=[]  # No camera attachments needed for Perth
        )

        response = response.__str__()
        # Extract the HTML color code from the response
        color_code_match = re.search(r'#(?:[0-9a-fA-F]{3}){1,2}\b', response)
        color_code = color_code_match.group(0) if color_code_match else None

        # Trim any trailing whitespace from the response
        if color_code:
            response = response.replace(color_code, "")
        response = response.rstrip()

        result = {
            "forecast_data": weather_data,
            "weather_report": response,
            "color_code": color_code,
            "timestamp": perth_time
        }

        with open("weather_report.json", "w") as f:
            json.dump(result, f, indent=4)