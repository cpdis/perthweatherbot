import json
import llm
import re
from datetime import datetime
from pytz import timezone
import os
from pathlib import Path
import logging
from typing import Dict, Union, Optional, Any

from config import load_config, WeatherBotConfig, LocationConfig, ConfigurationError
from weather import WeatherService, APIError
from images import generate_weather_image, ImageGenerationError
from history import WeatherHistory

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Main function to generate weather report"""
    try:
        # Load configuration
        config: WeatherBotConfig = load_config()
        
        # Set logging level from config
        logging.getLogger().setLevel(getattr(logging, config.log_level))
        
        # Extract location details
        location: LocationConfig = config.current_location
        logger.info(f"Using location: {location.name} ({location.latitude}, {location.longitude})")
    
        # Initialize weather service and get data
        weather: WeatherService = WeatherService(config.openweather_api_key)
        logger.info(f"Fetching weather data for {location.name}")
        weather_data: Dict[str, Any] = weather.get_weather_data(location.latitude, location.longitude, location.name)
        
        # Generate weather report using AI
        logger.info("Generating AI weather report")
        model = llm.get_model("gpt-5")
        
        # Build comprehensive forecast prompt
        forecasts: str = f"Below is the weather forecast for {location.name}: \n"
        for period in weather_data['forecast']:
            forecasts += f"\n - {period['startTime']}: {period['shortForecast']}"

        # Convert the current time to location's timezone
        local_tz = timezone(location.timezone)
        local_time: str = datetime.now(local_tz).strftime("%Y-%m-%d %H:%M:%S")

        forecasts += f"\n\nCurrent local time: {local_time}"
        forecasts += f"\n\nReview the weather forecast and assess the weather, specifically looking for how sunny it will be and the UV index, the clarity of the day, and more.\n\nConsidering the weather forecast, please write a weather report for {location.name} capturing the current conditions; the expected weather for the day; how pleasant or unpleasant it looks; how one might best dress for the weather; and what one might do given the conditions, day, and time. Remember: you will generate this report many times a day, your recommended activities should be relatively mundane and not too cliche or stereotypical."
        forecasts += "\n\nDo not use headers or other formatting in your response. Just write one to two single paragraphs that are elegant, don't use bullet points or exclamation marks, and use emotive words more often than numbers and figures – but don't be flowery. You write like a novelist describing the scene, producing a work suitable for someone calmly reading it on a classical radio station between songs. With a style somewhere between Jack Kerouac and J. Peterman."
        forecasts += f"\n\nRemember to keep the response under {config.max_report_words} words."
        forecasts += "\n\nAfter the weather report, please put an HTML color code that best represents the weather forecast, time of day. Do not actually put the words HTML color code anywhere in the text."

        try:
            response = model.prompt(
                forecasts,
                attachments=[]  # No camera attachments needed for Perth
            )
            
            response_text: str = str(response)
            logger.info("Successfully generated weather report text")
            
            # Extract the HTML color code from the response
            color_code_match = re.search(r'#(?:[0-9a-fA-F]{3}){1,2}\b', response_text)
            color_code: Optional[str] = color_code_match.group(0) if color_code_match else None
            
            # Trim any trailing whitespace from the response
            if color_code:
                response_text = response_text.replace(color_code, "")
            response_text = response_text.rstrip()
            
            result: Dict[str, Any] = {
                "forecast_data": weather_data,
                "weather_report": response_text,
                "color_code": color_code,
                "timestamp": local_time,
                "location": {
                    "name": location.name,
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "timezone": location.timezone
                }
            }
            
            # Save weather report
            output_file: Path = Path(__file__).parent / "weather_report.json"
            with open(output_file, "w") as f:
                json.dump(result, f, indent=4)
            logger.info(f"Weather report saved to {output_file}")
            
            # Add to history
            try:
                history = WeatherHistory()
                history.add_entry(result)
                history.cleanup_old_entries(7)  # Keep 1 week of data
            except Exception as e:
                logger.warning(f"Failed to save to history: {e}")
            
            # Generate weather image
            if config.gemini_api_key:
                try:
                    current = weather_data['current_conditions']
                    image_path = generate_weather_image(
                        location_name=location.name,
                        weather_description=current['description'],
                        temperature=current['temperature_c'],
                        date_str=datetime.now(local_tz).strftime("%A, %B %d"),
                        config=config
                    )
                    logger.info(f"Weather image generated: {image_path}")
                except ImageGenerationError as e:
                    logger.warning(f"Image generation failed: {e}")
            else:
                logger.info("Skipping image generation - no Gemini API key configured")

            # Log completion
            logger.info(f"Weather report generation completed for {location.name}")
                
        except Exception as e:
            logger.error(f"Failed to generate weather report: {e}")
            # Try to show trend analysis for debugging
            try:
                history = WeatherHistory()
                trend = history.get_temperature_trend(6)
                logger.info(f"Recent temperature trend: {trend.get('message', 'No trend data')}")
            except:
                pass
            raise
            
    except (ConfigurationError, APIError) as e:
        logger.error(f"Weather bot execution failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in weather bot: {e}")
        raise


if __name__ == "__main__":
    main()