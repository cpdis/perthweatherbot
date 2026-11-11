"""No paid image calls: verify prompt, request and last-good-image semantics."""
import io
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image
import pytest

import images


def png_bytes():
    output = io.BytesIO()
    Image.new('RGB', (32, 18), 'skyblue').save(output, format='PNG')
    return output.getvalue()


def test_scene_request_is_wide_text_free_and_grounded(tmp_path, monkeypatch):
    monkeypatch.setattr(images, '__file__', str(tmp_path / 'images.py'))
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(
        candidates=[1], parts=[SimpleNamespace(inline_data=SimpleNamespace(data=png_bytes()))])
    monkeypatch.setattr(images.genai, 'Client', Mock(return_value=client))
    result = images.generate_weather_image('Perth', 'clear sky', 24, 'Wednesday',
                                           SimpleNamespace(gemini_api_key='test'), '20:00', False)
    request = client.models.generate_content.call_args.kwargs
    assert request['model'] == 'gemini-2.5-flash-image'
    assert request['config'].image_config.aspect_ratio == '16:9'
    assert 'NO text' in request['contents']
    assert 'Nighttime' in request['contents']
    assert result.read_bytes() == png_bytes()
    assert not list(tmp_path.glob('*.tmp'))


def test_corrupt_image_keeps_previous_scene(tmp_path):
    path = tmp_path / 'weather_image.png'
    path.write_bytes(png_bytes())
    before = path.read_bytes()
    with pytest.raises(images.ImageGenerationError):
        images.save_image_atomically(b'not an image', path)
    assert path.read_bytes() == before


def test_failed_replace_keeps_previous_scene(tmp_path, monkeypatch):
    path = tmp_path / 'weather_image.png'
    path.write_bytes(b'previous')
    monkeypatch.setattr(images.os, 'replace', Mock(side_effect=OSError('disk error')))
    with pytest.raises(OSError):
        images.save_image_atomically(png_bytes(), path)
    assert path.read_bytes() == b'previous'
    assert not list(tmp_path.glob('.weather-scene-*.tmp'))


def test_unknown_daylight_does_not_force_daytime():
    prompt = images.build_scene_prompt('Perth', 'cloudy', 18, 'Wednesday')
    assert 'Match the supplied local time' in prompt
    assert 'Daylight, with natural' not in prompt


def test_public_image_is_readable_by_static_server(tmp_path):
    import stat
    path = tmp_path / 'weather_image.png'
    images.save_image_atomically(png_bytes(), path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o644
