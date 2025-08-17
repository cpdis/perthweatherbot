import os
import json
import logging
import websocket
import base64
from pathlib import Path
from typing import Dict, List, Union, Optional
from config import WeatherBotError

logger = logging.getLogger(__name__)


class AudioGenerationError(WeatherBotError):
    """Raised when audio generation fails"""
    pass


def generate_audio_forecast(forecast_text: str) -> bool:
    """
    Generates audio file from forecast text using Eleven Labs API via websockets
    
    Args:
        forecast_text (str): The weather forecast text
        
    Returns:
        bool: True if audio generation was successful
        
    Raises:
        AudioGenerationError: If audio generation fails
    """
    try:
        api_key: Optional[str] = os.getenv('ELEVENLABS_API_KEY')
        if not api_key:
            logger.error("Eleven Labs API key not found in environment variables")
            raise AudioGenerationError("Eleven Labs API key not found in environment variables")

        # Prepare the request data
        request_data: Dict[str, Union[str, int]] = {
            "text": forecast_text,
            "model_id": "eleven_multilingual_v2",
            "voice_id": "qNkzaJoHLLdpvgh5tISm",
            "optimize_streaming_latency": 0
        }

        # Initialize audio buffer
        audio_chunks: List[bytes] = []

        def on_message(ws: websocket.WebSocketApp, message: Union[str, bytes]) -> None:
            try:
                # Parse the BinaryMessage
                data = json.loads(message)
                if "audio" in data:
                    # Decode base64 audio data
                    audio_chunk: bytes = base64.b64decode(data["audio"])
                    audio_chunks.append(audio_chunk)
            except json.JSONDecodeError:
                # If message is binary, it's an audio chunk
                if isinstance(message, bytes):
                    audio_chunks.append(message)
                else:
                    logger.warning(f"Received non-JSON string message: {message}")

        def on_error(ws: websocket.WebSocketApp, error: Exception) -> None:
            logger.error(f"WebSocket error: {error}")

        def on_close(ws: websocket.WebSocketApp, close_status_code: Optional[int], close_msg: Optional[str]) -> None:
            logger.info(f"WebSocket connection closed: {close_status_code} - {close_msg}")

        def on_open(ws: websocket.WebSocketApp) -> None:
            logger.info("WebSocket connection opened")
            # Send the initial request
            ws.send(json.dumps(request_data))

        # Create WebSocket connection
        ws = websocket.WebSocketApp(
            f"wss://api.elevenlabs.io/v1/text-to-speech/{request_data['voice_id']}/stream-input?model_id={request_data['model_id']}",
            header={"xi-api-key": api_key},
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )

        # Run WebSocket connection
        ws.run_forever()  

        if not audio_chunks:
            logger.error("No audio data received")
            raise AudioGenerationError("No audio data received from ElevenLabs API")

        # Combine audio chunks and save to file
        audio_path: Path = Path(__file__).parent / "forecast.mp3"
        try:
            with open(audio_path, "wb") as audio_file:
                for chunk in audio_chunks:
                    audio_file.write(chunk)
            logger.info(f"Successfully generated audio forecast at {audio_path}")
            return True
        except IOError as e:
            logger.error(f"Failed to write audio file: {e}")
            raise AudioGenerationError(f"Failed to write audio file: {e}") from e

    except (ConnectionError, websocket.WebSocketException) as e:
        logger.error(f"WebSocket connection error: {e}")
        raise AudioGenerationError(f"Audio generation failed due to connection error: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error generating audio forecast: {e}")
        raise AudioGenerationError(f"Unexpected error during audio generation: {e}") from e