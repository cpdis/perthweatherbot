# Weather Vibes

A natural language weather forecast generator that creates beautifully written weather reports and AI-generated images for any location. Originally built for Perth, Australia, now location-aware and mobile.

## Features

- Fetches real-time weather data from OpenWeather API
- Generates narrative weather reports using GPT-6 Luna (`gpt-6-luna`)
- Creates AI-generated weather scene images using Gemini
- Auto-detects timezone from coordinates
- Supports dynamic location updates (via mobile automation)
- Runs on GitHub Actions with scheduled updates

## Prerequisites

- Python 3.11+ (GitHub Actions and Docker use 3.12)
- OpenWeather API key
- OpenAI API key
- Gemini API key (optional, for image generation)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/cpdis/perthweatherbot.git
cd perthweatherbot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables in a `.env` file:
```
OPENWEATHER_API_KEY=your_openweather_api_key
OPENAI_API_KEY=your_openai_api_key
GEMINI_API_KEY=your_gemini_api_key
```

## Configuration

### Location

Edit `location.json` to set your location:
```json
{
  "latitude": 29.7234,
  "longitude": -95.8334,
  "location_name": "Katy"
}
```

The timezone is automatically detected from coordinates using `timezonefinder`.

### Mobile Location Updates

The location can be updated automatically via mobile automation (e.g., iOS Shortcuts) by pushing changes to `location.json`. This enables the weather report to follow you as you travel.

## Running Locally

```bash
python weatherbot.py
```

This generates:
- `weather_report.json` - Weather data and narrative report
- `weather_image.png` - AI-generated weather scene (if Gemini configured)

## GitHub Actions

The bot runs automatically via GitHub Actions on a schedule. Configure the cron in `.github/workflows/weather-update.yml`.

## Output

The generated report includes:
- Current weather conditions
- Weather forecast
- Narrative weather report (novelist style)
- AI-generated scene image
- Color code based on conditions
- Timestamps in local time

## Live Site

View the live weather at [weather.cpd.dev](https://weather.cpd.dev)

## Weather Vibes upgrades

The generated scene appears at the top of the page, above the weather report, in its original aspect ratio without cropping or animation. The miniature-city look remains, and new images contain no baked-in dates or temperatures. The page keeps light/dark themes, a compact next-24-hours forecast, and recent reports for the displayed location.

### Forecast and report contract

- The existing OpenWeather current-weather and three-hour forecast endpoints remain in use. The default horizon is now 48 hours (`FORECAST_HOURS=48`, configurable from 3 to 48).
- The language model receives the actual measurements, local time, forecast timestamps, feels-like temperature, humidity, cloud cover, wind/gusts, precipitation probabilities/amounts, and sunrise/sunset when supplied. Missing values remain unknown. This endpoint does not provide UV, air quality, pollen, or visibility.
- GPT-6 Luna produces a JSON object with `headline`, `summary`, `outlook`, `clothing`, `activity`, and `color_code`. A local validator checks exact fields, narrative types, the configured word budget, duplicate keys, and unsupported measurement mentions. The `llm` adapter does not enforce strict schema mode, so validation happens locally. Decorative colors are normalized to six-digit hex when unambiguous; invalid color values use a safe default accent rather than blocking fresh weather. This never retries a paid model call just to repair styling. This reduces unsupported claims; it is not a guarantee that every narrative sentence is factually correct.
- Report JSON keeps the original `weather_report`, `forecast_data`, `timestamp`, and `location` fields. Version 2 adds a structured `report`, `generated_at`, `observed_at`, `data_source`, and image freshness metadata.
- The interface uses the location's timezone. It distinguishes observation time from report-generation time and warns after 18 hours without a newer weather observation. Forecast periods that have already passed are not presented as upcoming. Reports are scheduled, not live.
- Report, history, and image files are replaced atomically. Invalid narrative/JSON output or a failed report write preserves the previous report. A failed image call preserves the old image but marks it as previous; artwork from a different location is not shown. Missing/corrupt history or artwork does not prevent reading the forecast.
- Existing location inputs and historical data are not rewritten by this upgrade. This remains a public static-site data model: review location privacy separately before publishing precise location data.

### Local design preview (no API calls)

Requires Node 22+:

```sh
npm run preview
```

Open the printed localhost URL. This uses clearly labelled **illustrative sample data**, plus a generated preview artwork, without changing `weather_report.json`, `weather_history.json`, or `weather_image.png`. The preview artwork is not a production Gemini output. Stop it with Ctrl-C.

To serve the real generated files locally instead:

```sh
python -m http.server 8000 --bind 127.0.0.1
```

Keep that development server local: unlike the supplied nginx configuration, a generic file server does not restrict which repository files are served.

### Verification

```sh
python -m pytest tests --cov=. --cov-report=term-missing
mypy --ignore-missing-imports *.py
flake8 . --exclude=venv,node_modules --select=E9,F63,F7,F82
npm ci
npm test
npx playwright install chromium
npm run test:ui
```

Browser tests use an isolated profile with sample data. They cover mobile/desktop layouts, dark mode, uncropped top-image layout, history, retries, stale and missing data, unsafe model text, and unavailable artwork/history. Set `SCREENSHOT_DIR=artifacts` to save labelled preview screenshots. No live weather, model, or image-generation calls run in tests.

The Docker/Compose setup serves the new JS/CSS assets and uses directory mounts so atomic output replacement works. nginx exposes only an explicit public-file allowlist, not `.env`, `.git`, source files, location inputs, or test fixtures.
