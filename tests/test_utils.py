import unittest
import time
from unittest.mock import patch, MagicMock

from utils import RateLimiter, retry_with_backoff, create_cache_key, log_performance


class TestRateLimiter(unittest.TestCase):
    
    def test_rate_limiter_basic(self):
        """Test basic rate limiting functionality"""
        limiter = RateLimiter(calls_per_minute=60)  # 1 call per second
        
        # First call should not wait
        start_time = time.time()
        limiter.wait_if_needed()
        self.assertLess(time.time() - start_time, 0.1)
        
        # Second call should wait briefly
        start_time = time.time()
        limiter.wait_if_needed()
        elapsed = time.time() - start_time
        self.assertGreater(elapsed, 0.8)  # Should wait close to 1 second
    
    def test_rate_limiter_high_frequency(self):
        """Test rate limiter with high frequency calls"""
        limiter = RateLimiter(calls_per_minute=120)  # 2 calls per second
        
        start_time = time.time()
        limiter.wait_if_needed()
        limiter.wait_if_needed()
        elapsed = time.time() - start_time
        
        # Should wait approximately 0.5 seconds
        self.assertGreater(elapsed, 0.4)
        self.assertLess(elapsed, 0.7)


class TestRetryDecorator(unittest.TestCase):
    
    def test_retry_success_first_attempt(self):
        """Test successful function on first attempt"""
        @retry_with_backoff(max_retries=3)
        def always_succeeds():
            return "success"
        
        result = always_succeeds()
        self.assertEqual(result, "success")
    
    def test_retry_success_after_failures(self):
        """Test successful function after some failures"""
        call_count = 0
        
        @retry_with_backoff(max_retries=3, base_delay=0.1)
        def fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception(f"Attempt {call_count}")
            return "success"
        
        result = fails_twice()
        self.assertEqual(result, "success")
        self.assertEqual(call_count, 3)
    
    def test_retry_exhausted(self):
        """Test function that fails all retry attempts"""
        @retry_with_backoff(max_retries=2, base_delay=0.1)
        def always_fails():
            raise Exception("Always fails")
        
        with self.assertRaises(Exception):
            always_fails()


class TestUtilityFunctions(unittest.TestCase):
    
    def test_create_cache_key(self):
        """Test cache key creation"""
        key = create_cache_key(-31.9544, 115.8526)
        self.assertEqual(key, "weather_-31.9544_115.8526")
        
        key_rounded = create_cache_key(-31.95443333, 115.85267777)
        self.assertEqual(key_rounded, "weather_-31.9544_115.8527")
    
    def test_create_cache_key_with_type(self):
        """Test cache key creation with custom data type"""
        key = create_cache_key(-31.9544, 115.8526, "forecast")
        self.assertEqual(key, "forecast_-31.9544_115.8526")
    
    @patch('utils.logger')
    def test_log_performance_decorator(self, mock_logger):
        """Test performance logging decorator"""
        @log_performance
        def test_function():
            time.sleep(0.1)
            return "result"
        
        result = test_function()
        self.assertEqual(result, "result")
        
        # Verify logging was called
        self.assertTrue(mock_logger.info.called)
        log_message = mock_logger.info.call_args[0][0]
        self.assertIn("test_function completed in", log_message)
    
    @patch('utils.logger')
    def test_log_performance_with_exception(self, mock_logger):
        """Test performance logging decorator with exception"""
        @log_performance
        def failing_function():
            time.sleep(0.1)
            raise ValueError("Test error")
        
        with self.assertRaises(ValueError):
            failing_function()
        
        # Verify error logging was called
        self.assertTrue(mock_logger.error.called)
        log_message = mock_logger.error.call_args[0][0]
        self.assertIn("failing_function failed after", log_message)


if __name__ == '__main__':
    unittest.main()