import os
import json
import logging
import requests
from typing import Dict, Any, List
from datetime import datetime, timedelta
from pathlib import Path

from config import load_config, ConfigurationError
from weather import WeatherService
from cache import WeatherCache

logger = logging.getLogger(__name__)


class HealthCheck:
    """Health check system for the weather bot"""
    
    def __init__(self) -> None:
        self.checks: List[Dict[str, Any]] = []
    
    def check_api_connectivity(self) -> Dict[str, Any]:
        """Check if weather API is accessible"""
        try:
            config = load_config()
            
            # Test OpenWeather API with a simple request
            url = f"https://api.openweathermap.org/data/2.5/weather?lat=-31.9544&lon=115.8526&appid={config.openweather_api_key}&units=metric"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            return {
                "name": "OpenWeather API",
                "status": "healthy",
                "response_time_ms": response.elapsed.total_seconds() * 1000,
                "details": f"HTTP {response.status_code}"
            }
        except requests.exceptions.RequestException as e:
            return {
                "name": "OpenWeather API", 
                "status": "unhealthy",
                "error": str(e),
                "details": "Failed to connect to OpenWeather API"
            }
        except Exception as e:
            return {
                "name": "OpenWeather API",
                "status": "error", 
                "error": str(e),
                "details": "Configuration or other error"
            }
    
    def check_configuration(self) -> Dict[str, Any]:
        """Check if configuration is valid"""
        try:
            config = load_config()
            
            checks = []
            
            # Check required API keys
            if config.openweather_api_key:
                checks.append("OpenWeather API key configured")
            else:
                checks.append("❌ OpenWeather API key missing")
                
            if config.openai_api_key:
                checks.append("OpenAI API key configured")
            else:
                checks.append("❌ OpenAI API key missing")

            # Check location configuration
            if config.current_location:
                checks.append(f"Location: {config.current_location.name}")
            else:
                checks.append("❌ No location configured")
            
            return {
                "name": "Configuration",
                "status": "healthy",
                "details": checks
            }
            
        except ConfigurationError as e:
            return {
                "name": "Configuration",
                "status": "unhealthy", 
                "error": str(e),
                "details": "Configuration validation failed"
            }
        except Exception as e:
            return {
                "name": "Configuration",
                "status": "error",
                "error": str(e),
                "details": "Unexpected configuration error"
            }
    
    def check_file_permissions(self) -> Dict[str, Any]:
        """Check if required files can be read/written"""
        try:
            issues = []
            base_path = Path(__file__).parent
            
            # Check if we can write output files
            try:
                test_file = base_path / "test_write.tmp"
                test_file.write_text("test")
                test_file.unlink()
            except Exception as e:
                issues.append(f"Cannot write to project directory: {e}")
            
            # Check if required files exist and are readable
            required_files = ["location.json"]
            for filename in required_files:
                file_path = base_path / filename
                if not file_path.exists():
                    issues.append(f"Required file missing: {filename}")
                elif not file_path.is_file():
                    issues.append(f"Path is not a file: {filename}")
                else:
                    try:
                        file_path.read_text()
                    except Exception as e:
                        issues.append(f"Cannot read {filename}: {e}")
            
            if issues:
                return {
                    "name": "File Permissions",
                    "status": "unhealthy",
                    "details": issues
                }
            else:
                return {
                    "name": "File Permissions", 
                    "status": "healthy",
                    "details": ["All required files accessible"]
                }
                
        except Exception as e:
            return {
                "name": "File Permissions",
                "status": "error",
                "error": str(e),
                "details": "Unexpected file permission error"
            }
    
    def check_cache_system(self) -> Dict[str, Any]:
        """Check if caching system is working"""
        try:
            cache = WeatherCache()
            
            # Test cache operations
            test_data = {"test": "cache_data", "timestamp": datetime.now().isoformat()}
            cache.set("health_check", test_data, ttl=60)
            
            retrieved_data = cache.get("health_check")
            if retrieved_data == test_data:
                cache.clear()  # Clean up
                return {
                    "name": "Cache System",
                    "status": "healthy",
                    "details": ["Cache read/write operations successful"]
                }
            else:
                return {
                    "name": "Cache System",
                    "status": "unhealthy", 
                    "details": ["Cache data integrity check failed"]
                }
                
        except Exception as e:
            return {
                "name": "Cache System",
                "status": "error",
                "error": str(e),
                "details": "Cache system error"
            }
    
    def check_dependencies(self) -> Dict[str, Any]:
        """Check if all required Python packages are available"""
        try:
            required_modules = [
                "requests", "llm", "pytz", "json", "pathlib"
            ]
            
            missing_modules = []
            for module in required_modules:
                try:
                    __import__(module)
                except ImportError:
                    missing_modules.append(module)
            
            if missing_modules:
                return {
                    "name": "Dependencies",
                    "status": "unhealthy",
                    "details": f"Missing modules: {', '.join(missing_modules)}"
                }
            else:
                return {
                    "name": "Dependencies",
                    "status": "healthy", 
                    "details": ["All required modules available"]
                }
                
        except Exception as e:
            return {
                "name": "Dependencies",
                "status": "error",
                "error": str(e),
                "details": "Dependency check error"
            }
    
    def run_all_checks(self) -> Dict[str, Any]:
        """Run all health checks and return summary"""
        checks = [
            self.check_configuration(),
            self.check_file_permissions(), 
            self.check_dependencies(),
            self.check_cache_system(),
            self.check_api_connectivity()
        ]
        
        healthy_count = sum(1 for check in checks if check["status"] == "healthy")
        unhealthy_count = sum(1 for check in checks if check["status"] == "unhealthy")
        error_count = sum(1 for check in checks if check["status"] == "error")
        
        overall_status = "healthy" if unhealthy_count == 0 and error_count == 0 else "unhealthy"
        
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_status": overall_status,
            "summary": {
                "total_checks": len(checks),
                "healthy": healthy_count,
                "unhealthy": unhealthy_count,
                "errors": error_count
            },
            "checks": checks
        }


def main() -> None:
    """Run health checks and print results"""
    health = HealthCheck()
    results = health.run_all_checks()
    
    print(f"Weather Bot Health Check - {results['timestamp']}")
    print(f"Overall Status: {results['overall_status'].upper()}")
    print(f"Summary: {results['summary']['healthy']}/{results['summary']['total_checks']} checks passed")
    print("\nDetailed Results:")
    
    for check in results['checks']:
        status_emoji = {"healthy": "✅", "unhealthy": "❌", "error": "⚠️"}
        emoji = status_emoji.get(check['status'], "❓")
        print(f"{emoji} {check['name']}: {check['status']}")
        
        if 'error' in check:
            print(f"   Error: {check['error']}")
        if 'details' in check:
            if isinstance(check['details'], list):
                for detail in check['details']:
                    print(f"   - {detail}")
            else:
                print(f"   Details: {check['details']}")
    
    # Save results to file
    output_file = Path(__file__).parent / "health_check.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nHealth check results saved to {output_file}")


if __name__ == "__main__":
    main()