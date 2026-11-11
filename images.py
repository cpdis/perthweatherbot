"""Generate a full-bleed weather scene with the existing Gemini provider."""
import io
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types
from PIL import Image

from config import WeatherBotError, WeatherBotConfig
from utils import log_performance

logger = logging.getLogger(__name__)


class ImageGenerationError(WeatherBotError):
    """Raised when image generation fails."""


def build_scene_prompt(location_name: str, weather_description: str, temperature: float,
                       date_str: str, time_of_day: Optional[str] = None,
                       daylight: Optional[bool] = None) -> str:
    light = ('Daylight, with natural outdoor lighting.' if daylight is True else
             'Nighttime, with a dark sky and restrained warm window and street lighting.' if daylight is False else
             'Match the supplied local time; do not add unsupported weather events.')
    return f'''Create an immersive, edge-to-edge atmospheric illustration of {location_name}.
Keep the established Weather Vibes style: a refined miniature 3D city viewed at a
45-degree isometric angle, tactile materials, soft detailed textures, familiar local
architecture and gentle lifelike lighting. Expand the city into a continuous world:
streets, gardens and architecture continue beyond every edge. No floating island,
no pedestal, no isolated diorama and no solid-color border around the scene.
Actual weather description: {weather_description}. Temperature: {temperature:.0f} degrees Celsius.
Local date: {date_str}. Local time: {time_of_day or 'not supplied'}. {light}
Reflect only the supplied conditions. The image is an artistic impression, not a
live camera, a forecast chart, or evidence of exact street-level weather.
Compose a wide 16:9 landscape. Place the most interesting architecture around the
center-right, keeping the left third calmer for a readable interface overlay.
Make the central region work when cropped to a tall phone screen. Fill the frame
with this world, with visual depth and subtle atmosphere.
NO text, lettering, numerals, dates, temperatures, weather symbols, labels, logos,
UI elements or watermarks added by you. Those are rendered separately by the website.'''


def save_image_atomically(data: bytes, image_path: Path) -> None:
    """Reject malformed output and keep the last good scene on any write failure."""
    if not data or len(data) > 20 * 1024 * 1024:
        raise ImageGenerationError('Generated image is empty or too large')
    try:
        with Image.open(io.BytesIO(data)) as candidate:
            if candidate.format != 'PNG':
                raise ImageGenerationError('Expected a PNG image')
            candidate.verify()
    except ImageGenerationError:
        raise
    except Exception as error:
        raise ImageGenerationError('Generated image could not be decoded') from error
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=image_path.parent, prefix='.weather-scene-',
                                         suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            # Generated artifacts are public static-site files, also read by nginx.
            os.fchmod(handle.fileno(), 0o644)
            os.fsync(handle.fileno())
        os.replace(temporary, image_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@log_performance
def generate_weather_image(
    location_name: str,
    weather_description: str,
    temperature: float,
    date_str: str,
    config: Optional[WeatherBotConfig] = None,
    time_of_day: Optional[str] = None,
    daylight: Optional[bool] = None,
) -> Path:
    """Create text-free, panoramic artwork; failed generations preserve the old file."""
    try:
        if config is None:
            from config import load_config
            config = load_config()
        if not config.gemini_api_key:
            raise ImageGenerationError('Gemini API key not found')
        prompt = build_scene_prompt(location_name, weather_description, temperature,
                                    date_str, time_of_day, daylight)
        client = genai.Client(api_key=config.gemini_api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash-image',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=['IMAGE'],
                image_config=types.ImageConfig(aspect_ratio='16:9'),
            ),
        )
        if not response.candidates or not response.parts:
            raise ImageGenerationError('No image candidates in response')
        image_path = Path(__file__).parent / 'weather_image.png'
        for part in response.parts:
            if part.inline_data is not None and part.inline_data.data:
                save_image_atomically(part.inline_data.data, image_path)
                logger.info('Generated panoramic weather scene for %s', location_name)
                return image_path
        raise ImageGenerationError('No image data in response')
    except ImageGenerationError:
        raise
    except Exception as error:
        # Avoid logging API request details or credentials.
        logger.warning('Weather scene generation failed (%s)', type(error).__name__)
        raise ImageGenerationError('Weather scene generation failed') from error
