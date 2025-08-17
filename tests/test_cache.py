import unittest
import tempfile
import json
import time
from pathlib import Path

from cache import WeatherCache, CacheEntry


class TestCacheEntry(unittest.TestCase):
    
    def test_cache_entry_not_expired(self):
        """Test cache entry that hasn't expired"""
        entry = CacheEntry(
            data={"test": "data"},
            timestamp=time.time(),
            ttl=300
        )
        self.assertFalse(entry.is_expired())
    
    def test_cache_entry_expired(self):
        """Test cache entry that has expired"""
        entry = CacheEntry(
            data={"test": "data"},
            timestamp=time.time() - 400,  # 400 seconds ago
            ttl=300  # 5 minute TTL
        )
        self.assertTrue(entry.is_expired())


class TestWeatherCache(unittest.TestCase):
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cache = WeatherCache(cache_dir=Path(self.temp_dir), default_ttl=300)
    
    def tearDown(self):
        # Clean up temporary directory
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_cache_set_and_get(self):
        """Test basic cache set and get operations"""
        test_data = {"temperature": 20.5, "description": "sunny"}
        
        # Set data in cache
        self.cache.set("test_key", test_data)
        
        # Get data from cache
        result = self.cache.get("test_key")
        self.assertEqual(result, test_data)
    
    def test_cache_miss(self):
        """Test cache miss returns None"""
        result = self.cache.get("nonexistent_key")
        self.assertIsNone(result)
    
    def test_cache_expiry(self):
        """Test that expired cache entries return None"""
        test_data = {"temperature": 20.5}
        
        # Set data with very short TTL
        self.cache.set("test_key", test_data, ttl=1)
        
        # Should be available immediately
        result = self.cache.get("test_key")
        self.assertEqual(result, test_data)
        
        # Wait for expiry
        time.sleep(1.1)
        
        # Should now return None
        result = self.cache.get("test_key")
        self.assertIsNone(result)
    
    def test_cache_file_persistence(self):
        """Test that cache persists to file"""
        test_data = {"temperature": 20.5}
        self.cache.set("test_key", test_data)
        
        # Create new cache instance with same directory
        new_cache = WeatherCache(cache_dir=Path(self.temp_dir))
        result = new_cache.get("test_key")
        self.assertEqual(result, test_data)
    
    def test_cache_clear(self):
        """Test clearing cache"""
        test_data = {"temperature": 20.5}
        self.cache.set("test_key", test_data)
        
        # Verify data is cached
        result = self.cache.get("test_key")
        self.assertEqual(result, test_data)
        
        # Clear cache
        self.cache.clear()
        
        # Verify data is gone
        result = self.cache.get("test_key")
        self.assertIsNone(result)
    
    def test_cleanup_expired(self):
        """Test cleanup of expired entries"""
        # Set expired data
        self.cache.set("expired_key", {"temp": 20}, ttl=1)
        self.cache.set("valid_key", {"temp": 25}, ttl=300)
        
        # Wait for first entry to expire
        time.sleep(1.1)
        
        # Run cleanup
        self.cache.cleanup_expired()
        
        # Expired entry should be gone, valid entry should remain
        self.assertIsNone(self.cache.get("expired_key"))
        self.assertIsNotNone(self.cache.get("valid_key"))


if __name__ == '__main__':
    unittest.main()