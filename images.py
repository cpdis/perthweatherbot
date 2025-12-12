import logging
from pathlib import Path
from typing import Optional
from google import genai
from google.genai import types
from config import WeatherBotError, WeatherBotConfig
from utils import log_performance

logger = logging.getLogger(__name__)


class ImageGenerationError(WeatherBotError):
    """Raised when image generation fails"""
    pass


@log_performance
def generate_weather_image(
    location_name: str,
    weather_description: str,
    temperature: float,
    date_str: str,
    config: Optional[WeatherBotConfig] = None
) -> Path:
    """
    Generate weather image using Gemini API

    Args:
        location_name: Name of the city/location
        weather_description: Current weather conditions description
        temperature: Current temperature in Celsius
        date_str: Formatted date string
        config: WeatherBotConfig instance

    Returns:
        Path to the generated image file

    Raises:
        ImageGenerationError: If image generation fails
    """
    try:
        # Use provided config or load from environment
        if config is None:
            from config import load_config
            config = load_config()

        if not config.gemini_api_key:
            logger.error("Gemini API key not found")
            raise ImageGenerationError("Gemini API key not found")

        # Build the prompt with dynamic values
        prompt = f"""Present a clear, 45° top-down isometric miniature 3D cartoon scene of {location_name}, featuring its most iconic landmarks and architectural elements. Use soft, refined textures with realistic PBR materials and gentle, lifelike lighting and shadows. Integrate the current weather conditions ({weather_description}) directly into the city environment to create an immersive atmospheric mood.
Use a clean, minimalistic composition with a soft, solid-colored background.

At the top-center, place the title "{location_name}" in large bold text, a prominent weather icon beneath it, then the date ({date_str}) and temperature ({temperature:.0f}°C).
All text must be centered with consistent spacing, and may subtly overlap the tops of the buildings.
Square 1080x1080 dimension."""

        logger.info(f"Generating weather image for {location_name}")
        logger.debug(f"Image prompt: {prompt[:100]}...")

        # Initialize Gemini client
        client = genai.Client(api_key=config.gemini_api_key)

        # Generate image
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(aspect_ratio="1:1")
            )
        )

        # Extract and save image
        image_path = Path(__file__).parent / "weather_image.png"

        if not response.candidates:
            raise ImageGenerationError("No candidates in response")

        for part in response.parts:
            if part.inline_data is not None and part.inline_data.data is not None:
                with open(image_path, "wb") as f:
                    f.write(part.inline_data.data)
                logger.info(f"Successfully generated weather image at {image_path}")
                return image_path

        raise ImageGenerationError("No image data in response")

    except ImageGenerationError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error generating weather image: {e}")
        raise ImageGenerationError(f"Unexpected error during image generation: {e}") from e
