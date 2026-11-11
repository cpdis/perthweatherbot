"""Report-generation regression tests; no network calls or real API keys."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import llm
import pytest

import weatherbot
from config import LocationConfig, WeatherBotConfig


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


@pytest.mark.parametrize("color", ["#87CEEB", "#abc", None])
def test_luna_report_generation(report_setup, color):
    output_dir, weather_data, model, client, get_model, history, image = report_setup
    narrative = "Soft light settles over Perth. A light shirt will suit a quiet walk."
    response = narrative + (f"\n\n{color}" if color else "")
    client.responses.create.return_value = iter([
        SimpleNamespace(type="response.output_text.delta", delta=response),
    ])

    weatherbot.main()

    get_model.assert_called_once_with("gpt-6-luna")
    assert model.model_id == "gpt-6-luna"
    request = client.responses.create.call_args.kwargs
    assert request["model"] == "gpt-6-luna"
    assert request["stream"] is True
    assert "Sunny, 24 C" in json.dumps(request["input"])
    assert "under 300 words" in json.dumps(request["input"])
    result = json.loads((output_dir / "weather_report.json").read_text())
    assert result["weather_report"] == narrative
    assert result["color_code"] == color
    assert result["forecast_data"] == weather_data
    assert result["location"]["name"] == "Perth"
    history.add_entry.assert_called_once_with(result)
    image.assert_not_called()


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
