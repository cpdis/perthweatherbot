"""Report-generation regression tests; no network calls or real API keys."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import llm
import pytest

import weatherbot
from config import LocationConfig, WeatherBotConfig, load_location_config


@pytest.fixture
def report_setup(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_USER_PATH", str(tmp_path / "llm"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setattr(weatherbot, "__file__", str(tmp_path / "weatherbot.py"))
    location = LocationConfig("Perth", -31.9544, 115.8526)
    config = WeatherBotConfig(location, [location], "test-weather-key", "test-openai-key")
    monkeypatch.setattr(weatherbot, "load_config", Mock(return_value=config))
    weather_data = {
        "forecast": [{"startTime": "2026-11-11T12:00:00+08:00", "shortForecast": "Sunny, 24 C"}],
        "current_conditions": {"description": "clear sky", "temperature_c": 24},
    }
    service = Mock()
    service.get_weather_data.return_value = weather_data
    monkeypatch.setattr(weatherbot, "WeatherService", Mock(return_value=service))
    history = Mock()
    monkeypatch.setattr(weatherbot, "WeatherHistory", Mock(return_value=history))
    image = Mock()
    monkeypatch.setattr(weatherbot, "generate_weather_image", image)
    # Resolve the real installed LLM adapter, mocking only the remote API client.
    model = llm.get_model(weatherbot.REPORT_MODEL)
    client = Mock()
    monkeypatch.setattr(model, "get_client", Mock(return_value=client))
    get_model = Mock(return_value=model)
    monkeypatch.setattr(weatherbot.llm, "get_model", get_model)
    return tmp_path, weather_data, model, client, get_model, history, image


def structured_response(**overrides):
    value = dict(headline="Soft light", summary="Soft light settles over Perth.",
                 outlook="A mild afternoon is forecast.", clothing="A light shirt will suit.",
                 activity="Take a quiet walk.", color_code="#87CEEB")
    value.update(overrides)
    return json.dumps(value)


def test_luna_report_generation(report_setup):
    output_dir, weather_data, model, client, get_model, history, image = report_setup
    client.responses.create.return_value = iter([
        SimpleNamespace(type="response.output_text.delta", delta=structured_response()),
    ])
    weatherbot.main()
    get_model.assert_called_once_with("gpt-6-luna")
    request = client.responses.create.call_args.kwargs
    assert request["model"] == "gpt-6-luna"
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["text"]["format"]["schema"]["additionalProperties"] is False
    assert "Sunny, 24 C" in json.dumps(request["input"])
    assert "under 300 words" in json.dumps(request["input"])
    result = json.loads((output_dir / "weather_report.json").read_text())
    assert result["report"]["headline"] == "Soft light"
    assert result["color_code"] == "#87CEEB"
    assert result["forecast_data"] == weather_data
    assert result["generated_at"].endswith("+00:00")
    assert result["timestamp"].endswith("+08:00")
    assert result["observed_at"] is None
    assert result["image"]["status"] == "unavailable"
    history.add_entry.assert_called_once_with(result)
    image.assert_not_called()


def test_blank_location_and_invalid_color_publish_safe_report(report_setup, monkeypatch):
    """Both cosmetic fallbacks work together without changing weather coordinates."""
    output_dir, weather_data, _, client, _, history, _ = report_setup
    monkeypatch.setattr('config.__file__', str(output_dir / 'config.py'))
    (output_dir / 'location.json').write_text(json.dumps({
        'location_name': '', 'latitude': -32.0, 'longitude': 116.0,
        'timezone': 'Australia/Perth',
    }))
    location = load_location_config()
    weatherbot.load_config.return_value.current_location = location
    weatherbot.load_config.return_value.locations = [location]
    client.responses.create.return_value = iter([
        SimpleNamespace(type='response.output_text.delta',
                        delta=structured_response(color_code='not-a-color')),
    ])
    weatherbot.main()
    result = json.loads((output_dir / 'weather_report.json').read_text())
    assert result['location'] == {
        'name': 'Current location', 'latitude': -32.0, 'longitude': 116.0,
        'timezone': 'Australia/Perth',
    }
    assert result['color_code'] == '#426350'
    assert result['forecast_data'] == weather_data
    weatherbot.WeatherService.return_value.get_weather_data.assert_called_once_with(
        -32.0, 116.0, 'Current location', forecast_hours=48)
    client.responses.create.assert_called_once()
    assert 'Current location' in json.dumps(client.responses.create.call_args.kwargs['input'])
    history.add_entry.assert_called_once_with(result)


@pytest.mark.parametrize("payload", ["not json", "{}",
    structured_response(summary="UV will be low."), structured_response(extra="unexpected"),
    structured_response(activity=" "), structured_response(summary="word " * 301)])
def test_malformed_output_preserves_report(report_setup, payload):
    output_dir, _, _, client, _, history, image = report_setup
    path = output_dir / "weather_report.json"
    path.write_text('{"weather_report":"Previous"}')
    client.responses.create.return_value = iter([
        SimpleNamespace(type="response.output_text.delta", delta=payload),
    ])
    with pytest.raises(ValueError):
        weatherbot.main()
    assert json.loads(path.read_text())["weather_report"] == "Previous"
    history.add_entry.assert_not_called()
    image.assert_not_called()


def test_image_failure_preserves_metadata(report_setup):
    output_dir, _, _, client, _, _, image = report_setup
    weatherbot.load_config.return_value.gemini_api_key = "test"
    (output_dir / "weather_image.png").write_bytes(b"previous scene")
    (output_dir / "weather_report.json").write_text(json.dumps({
        "location": vars(weatherbot.load_config.return_value.current_location),
        "image": {"generated_at": "2026-11-10T12:00:00+00:00"}}))
    image.side_effect = RuntimeError("image unavailable")
    client.responses.create.return_value = iter([
        SimpleNamespace(type="response.output_text.delta", delta=structured_response()),
    ])
    weatherbot.main()
    result = json.loads((output_dir / "weather_report.json").read_text())
    assert result["image"]["status"] == "previous"
    assert result["image"]["generated_at"] == "2026-11-10T12:00:00+00:00"


def test_luna_api_failure_preserves_previous_report(report_setup):
    output_dir, _, _, client, _, history, image = report_setup
    report = output_dir / "weather_report.json"
    report.write_text('{"weather_report": "Previous report"}')
    client.responses.create.side_effect = RuntimeError("API unavailable")

    with pytest.raises(RuntimeError, match="API unavailable"):
        weatherbot.main()

    assert json.loads(report.read_text())["weather_report"] == "Previous report"
    history.add_entry.assert_not_called()
    image.assert_not_called()


@pytest.mark.parametrize('previous', [[], None, {'image': None}, {'image': []}])
def test_malformed_previous_metadata_does_not_block(report_setup, previous):
    output_dir, _, _, client, _, _, _ = report_setup
    (output_dir / 'weather_report.json').write_text(json.dumps(previous))
    (output_dir / 'weather_image.png').write_bytes(b'old scene')
    client.responses.create.return_value = iter([
        SimpleNamespace(type='response.output_text.delta', delta=structured_response()),
    ])
    weatherbot.main()
    result = json.loads((output_dir / 'weather_report.json').read_text())
    assert result['image']['status'] == 'unavailable'


def test_changed_location_does_not_reuse_scene_on_repeated_runs(report_setup):
    output_dir, _, _, client, _, _, _ = report_setup
    previous_location = dict(vars(weatherbot.load_config.return_value.current_location), name='London')
    (output_dir / 'weather_report.json').write_text(json.dumps({
        'location': previous_location, 'image': {'status': 'ready', 'generated_at': '2026-11-10T12:00:00Z'}}))
    (output_dir / 'weather_image.png').write_bytes(b'London scene')
    for _ in range(2):
        client.responses.create.return_value = iter([
            SimpleNamespace(type='response.output_text.delta', delta=structured_response()),
        ])
        weatherbot.main()
        result = json.loads((output_dir / 'weather_report.json').read_text())
        assert result['image']['status'] == 'unavailable'
        assert result['image']['generated_at'] is None
    assert (output_dir / 'weather_image.png').read_bytes() == b'London scene'


@pytest.mark.parametrize(('color', 'expected'), [
    ('#87CEEB', '#87CEEB'),
    ('  #87ceeb  ', '#87CEEB'),
    ('87ceeb', '#87CEEB'),
    ('#abc', '#AABBCC'),
    ('blue', '#426350'),
    ('rgb(135, 206, 235)', '#426350'),
    ('#12GG34', '#426350'),
    ('#123456;background:url(https://example.com)', '#426350'),
    ('', '#426350'),
    (None, '#426350'),
    (['#87CEEB'], '#426350'),
    ('x' * 6001, '#426350'),
])
def test_decorative_color_does_not_block_weather_publication(report_setup, color, expected):
    output_dir, weather_data, _, client, _, history, image = report_setup
    weatherbot.load_config.return_value.gemini_api_key = 'test-image-key'
    (output_dir / 'weather_report.json').write_text('{"weather_report":"Previous"}')
    client.responses.create.return_value = iter([
        SimpleNamespace(type='response.output_text.delta', delta=structured_response(color_code=color)),
    ])
    weatherbot.main()
    result = json.loads((output_dir / 'weather_report.json').read_text())
    assert result['color_code'] == expected
    assert result['report']['summary'] == 'Soft light settles over Perth.'
    assert result['forecast_data'] == weather_data
    assert result['image']['status'] == 'ready'
    history.add_entry.assert_called_once_with(result)
    image.assert_called_once()
    client.responses.create.assert_called_once()  # No additional paid retry for styling.


def test_color_fallback_does_not_bypass_narrative_validation(report_setup):
    output_dir, _, _, client, _, history, image = report_setup
    path = output_dir / 'weather_report.json'
    path.write_text('{"weather_report":"Previous"}')
    client.responses.create.return_value = iter([
        SimpleNamespace(type='response.output_text.delta',
                        delta=structured_response(color_code='blue', summary='UV will be low.')),
    ])
    with pytest.raises(ValueError, match='unsupported measurement'):
        weatherbot.main()
    assert json.loads(path.read_text())['weather_report'] == 'Previous'
    history.add_entry.assert_not_called()
    image.assert_not_called()
