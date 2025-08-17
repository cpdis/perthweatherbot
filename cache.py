import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A cached data entry with timestamp"""
    data: Dict[str, Any]
    timestamp: float
    ttl: int  # Time to live in seconds
    
    def is_expired(self) -> bool:
        """Check if the cache entry has expired"""
        return time.time() - self.timestamp > self.ttl


class WeatherCache:
    """Simple file-based cache for weather data"""
    
    def __init__(self, cache_dir: Optional[Path] = None, default_ttl: int = 300) -> None:
        """
        Initialize weather cache
        
        Args:
            cache_dir: Directory to store cache files (defaults to current directory)
            default_ttl: Default time to live in seconds (defaults to 5 minutes)
        """
        self.cache_dir: Path = cache_dir or Path(__file__).parent / ".cache"
        self.default_ttl: int = default_ttl
        self.cache_dir.mkdir(exist_ok=True)
        self._memory_cache: Dict[str, CacheEntry] = {}
        
    def _get_cache_file_path(self, key: str) -> Path:
        """Get the file path for a cache key"""
        # Sanitize key for filename
        safe_key = "".join(c for c in key if c.isalnum() or c in ('-', '_', '.')).rstrip()
        return self.cache_dir / f"{safe_key}.json"
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get cached data by key
        
        Args:
            key: Cache key
            
        Returns:
            Cached data if valid, None if expired or not found
        """
        # Check memory cache first
        if key in self._memory_cache:
            entry = self._memory_cache[key]
            if not entry.is_expired():
                logger.debug(f"Cache hit (memory): {key}")
                return entry.data
            else:
                del self._memory_cache[key]
        
        # Check file cache
        cache_file = self._get_cache_file_path(key)
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                    
                entry = CacheEntry(
                    data=cache_data['data'],
                    timestamp=cache_data['timestamp'],
                    ttl=cache_data['ttl']
                )
                
                if not entry.is_expired():
                    # Store in memory cache for faster access
                    self._memory_cache[key] = entry
                    logger.debug(f"Cache hit (file): {key}")
                    return entry.data
                else:
                    # Remove expired cache file
                    cache_file.unlink()
                    logger.debug(f"Cache expired: {key}")
                    
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.warning(f"Failed to read cache file {cache_file}: {e}")
        
        logger.debug(f"Cache miss: {key}")
        return None
    
    def set(self, key: str, data: Dict[str, Any], ttl: Optional[int] = None) -> None:
        """
        Store data in cache
        
        Args:
            key: Cache key
            data: Data to cache
            ttl: Time to live in seconds (uses default if not specified)
        """
        ttl = ttl or self.default_ttl
        timestamp = time.time()
        
        entry = CacheEntry(
            data=data,
            timestamp=timestamp,
            ttl=ttl
        )
        
        # Store in memory cache
        self._memory_cache[key] = entry
        
        # Store in file cache
        cache_file = self._get_cache_file_path(key)
        try:
            cache_data = {
                'data': data,
                'timestamp': timestamp,
                'ttl': ttl
            }
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            logger.debug(f"Cached data: {key}")
        except OSError as e:
            logger.warning(f"Failed to write cache file {cache_file}: {e}")
    
    def clear(self) -> None:
        """Clear all cached data"""
        # Clear memory cache
        self._memory_cache.clear()
        
        # Clear file cache
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink()
            logger.info("Cache cleared")
        except OSError as e:
            logger.warning(f"Failed to clear cache files: {e}")
    
    def cleanup_expired(self) -> None:
        """Remove expired cache entries"""
        current_time = time.time()
        
        # Cleanup memory cache
        expired_keys = [
            key for key, entry in self._memory_cache.items()
            if entry.is_expired()
        ]
        for key in expired_keys:
            del self._memory_cache[key]
        
        # Cleanup file cache
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    with open(cache_file, 'r') as f:
                        cache_data = json.load(f)
                    
                    if current_time - cache_data['timestamp'] > cache_data['ttl']:
                        cache_file.unlink()
                        logger.debug(f"Removed expired cache file: {cache_file}")
                        
                except (json.JSONDecodeError, KeyError, OSError):
                    # Remove corrupted cache files
                    cache_file.unlink()
                    logger.debug(f"Removed corrupted cache file: {cache_file}")
                    
        except OSError as e:
            logger.warning(f"Failed to cleanup cache files: {e}")
        
        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")