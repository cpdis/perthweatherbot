# Perth Weather Bot

A natural language weather forecast generator for Perth, Australia. This application fetches real-time weather data from the OpenWeather API and generates a beautifully written weather report.

## Prerequisites

- Python 3.6 or higher
- OpenWeather API key
- OpenAI API key

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/perth-weather-bot.git
cd perth-weather-bot
```

2. Install the required Python packages:
```bash
pip install requests pytz python-dotenv llm
```

3. Set up environment variables:
Create a `.env` file in the root directory with the following content:
```
OPENWEATHER_API_KEY=your_openweather_api_key
OPENAI_API_KEY=your_openai_api_key
```

## Configuration

The application is pre-configured with:
- Location: Perth, Australia (latitude: -31.9523, longitude: 115.8613)
- Environment variables for API keys (stored in `.env` file)

## Running Locally

1. Make sure your `.env` file is properly configured with valid API keys.

2. Run the Python script:
```bash
python foggybot.py
```

3. The script will generate a `weather_report.json` file containing:
- Current weather conditions
- Weather forecast
- Natural language weather report
- Color code based on weather conditions
- Current timestamp in Perth time

## API Reference

This application uses:
- OpenWeather API to fetch weather data:
  - Current weather endpoint: `api.openweathermap.org/data/2.5/weather`
  - Forecast endpoint: `api.openweathermap.org/data/2.5/forecast`
- OpenAI API for natural language processing

## Output Format

The generated `weather_report.json` file includes:
- Detailed weather data
- A beautifully written weather report in a narrative style
- Color coding for weather conditions
- Timestamps in Perth local time