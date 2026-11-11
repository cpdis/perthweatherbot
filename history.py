import json
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from report import atomic_write_json
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class WeatherHistory:
    """Manage historical weather data and trends"""
    
    def __init__(self, history_file: Optional[Path] = None) -> None:
        self.history_file: Path = history_file or Path(__file__).parent / "weather_history.json"
        self.max_entries: int = 168  # Keep 1 week of hourly data
    
    def add_entry(self, weather_report: Dict[str, Any]) -> None:
        """Add a weather report to history"""
        try:
            # Load existing history
            history = self._load_history()
            
            # Create history entry
            entry = {
                "timestamp": weather_report.get("generated_at", weather_report.get("timestamp")),
                "generated_at": weather_report.get("generated_at"),
                "observed_at": weather_report.get("observed_at"),
                "headline": weather_report.get("report", {}).get("headline"),
                "location": weather_report.get("location", {}),
                "current_conditions": weather_report.get("forecast_data", {}).get("current_conditions", {}),
                "report_summary": weather_report.get("report", {}).get("summary") or weather_report.get("weather_report", "")[:240],
                "color_code": weather_report.get("color_code")
            }
            
            # Add to history
            history.append(entry)
            
            # Keep only recent entries
            if len(history) > self.max_entries:
                history = history[-self.max_entries:]
            
            # Save updated history
            self._save_history(history)
            logger.info(f"Added weather entry to history. Total entries: {len(history)}")
            
        except Exception as e:
            logger.error(f"Failed to add entry to weather history: {e}")
    
    @staticmethod
    def _entry_time(entry):
        value = entry.get('generated_at') or entry['timestamp']
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            # Old reports stored local wall time; never use the server timezone.
            name = entry.get('location', {}).get('timezone') or 'Australia/Perth'
            parsed = parsed.replace(tzinfo=ZoneInfo(name))
        return parsed.astimezone(timezone.utc)

    def get_recent_entries(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get weather entries from the last N hours"""
        try:
            history = self._load_history()
            
            # Filter entries from last N hours
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            recent_entries = []
            
            for entry in history:
                if entry.get("timestamp"):
                    try:
                        entry_time = self._entry_time(entry)
                        if entry_time >= cutoff_time:
                            recent_entries.append(entry)
                    except (ValueError, TypeError, KeyError):
                        continue
            
            return sorted(recent_entries, key=self._entry_time)[-50:]  # Return max 50 entries
            
        except Exception as e:
            logger.error(f"Failed to get recent weather history: {e}")
            return []
    
    def get_temperature_trend(self, hours: int = 12) -> Dict[str, Any]:
        """Get temperature trend analysis"""
        try:
            recent_entries = self.get_recent_entries(hours)
            
            if len(recent_entries) < 2:
                return {"trend": "insufficient_data", "message": "Not enough data for trend analysis"}
            
            temperatures = []
            for entry in recent_entries:
                temp = entry.get("current_conditions", {}).get("temperature_c")
                if temp is not None:
                    temperatures.append(temp)
            
            if len(temperatures) < 2:
                return {"trend": "insufficient_data", "message": "Not enough temperature data"}
            
            # Simple trend analysis
            first_temp = temperatures[0]
            last_temp = temperatures[-1]
            temp_change = last_temp - first_temp
            
            if abs(temp_change) < 1:
                trend = "stable"
                message = f"Temperature has been stable around {last_temp:.1f}°C"
            elif temp_change > 0:
                trend = "rising"
                message = f"Temperature rising by {temp_change:.1f}°C (from {first_temp:.1f}°C to {last_temp:.1f}°C)"
            else:
                trend = "falling"
                message = f"Temperature falling by {abs(temp_change):.1f}°C (from {first_temp:.1f}°C to {last_temp:.1f}°C)"
            
            return {
                "trend": trend,
                "change_celsius": temp_change,
                "current_temp": last_temp,
                "message": message,
                "data_points": len(temperatures)
            }
            
        except Exception as e:
            logger.error(f"Failed to analyze temperature trend: {e}")
            return {"trend": "error", "message": f"Analysis failed: {e}"}
    
    def _load_history(self) -> List[Dict[str, Any]]:
        """Load weather history from file"""
        if not self.history_file.exists():
            return []
        
        try:
            with open(self.history_file, 'r') as f:
                data = json.load(f)
                if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
                    raise ValueError('History must be a list of objects')
                return data
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load weather history: {e}")
            raise
    
    def _save_history(self, history: List[Dict[str, Any]]) -> None:
        """Save weather history to file"""
        try:
            atomic_write_json(self.history_file, history)
        except IOError as e:
            logger.error(f"Failed to save weather history: {e}")
            raise
    
    def cleanup_old_entries(self, days: int = 7) -> None:
        """Remove entries older than specified days"""
        try:
            history = self._load_history()
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
            
            filtered_history = []
            for entry in history:
                if entry.get("timestamp"):
                    try:
                        entry_time = self._entry_time(entry)
                        if entry_time >= cutoff_time:
                            filtered_history.append(entry)
                    except (ValueError, TypeError, KeyError):
                        continue
            
            if len(filtered_history) != len(history):
                self._save_history(filtered_history)
                removed_count = len(history) - len(filtered_history)
                logger.info(f"Cleaned up {removed_count} old weather history entries")
            
        except Exception as e:
            logger.error(f"Failed to cleanup weather history: {e}")


def main() -> None:
    """Demonstrate weather history functionality"""
    history = WeatherHistory()
    
    # Show recent entries
    recent = history.get_recent_entries(24)
    print(f"Recent entries (last 24h): {len(recent)}")
    
    # Show temperature trend
    trend = history.get_temperature_trend(12)
    print(f"Temperature trend: {trend}")
    
    # Cleanup old entries
    history.cleanup_old_entries(7)


if __name__ == "__main__":
    main()