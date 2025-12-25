# Weather Vibes

A natural language weather forecast generator that creates beautifully written weather reports and AI-generated images for any location. Originally built for Perth, Australia, now location-aware and mobile.

## Features

- Fetches real-time weather data from OpenWeather API
- Generates narrative weather reports using GPT
- Creates AI-generated weather scene images using Gemini
- Auto-detects timezone from coordinates
- Supports dynamic location updates (via mobile automation)
- Runs on GitHub Actions with scheduled updates

## Prerequisites

- Python 3.9+
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
