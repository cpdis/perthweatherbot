import time
import logging
import functools
from typing import Callable, Any, Dict, Optional, TypeVar, Union
import random

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RateLimiter:
    """Simple rate limiter to avoid hitting API limits"""
    
    def __init__(self, calls_per_minute: int = 60) -> None:
        self.calls_per_minute = calls_per_minute
        self.min_interval = 60.0 / calls_per_minute
        self.last_call = 0.0
    
    def wait_if_needed(self) -> None:
        """Wait if necessary to respect rate limits"""
        current_time = time.time()
        time_since_last = current_time - self.last_call
        
        if time_since_last < self.min_interval:
            sleep_time = self.min_interval - time_since_last
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        
        self.last_call = time.time()


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_multiplier: float = 2.0,
    jitter: bool = True
) -> Callable:
    """
    Decorator for retrying functions with exponential backoff
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        backoff_multiplier: Multiplier for exponential backoff
        jitter: Add random jitter to delay to avoid thundering herd
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(f"Function {func.__name__} failed after {max_retries} retries: {e}")
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (backoff_multiplier ** attempt), max_delay)
                    
                    # Add jitter to prevent thundering herd
                    if jitter:
                        delay *= (0.5 + random.random() * 0.5)
                    
                    logger.warning(f"Function {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying in {delay:.2f}s")
                    time.sleep(delay)
            
            # This should never be reached, but just in case
            raise last_exception or Exception("All retry attempts failed")
        
        return wrapper
    return decorator


def timeout_after(seconds: float) -> Callable:
    """
    Decorator to add timeout to functions
    
    Args:
        seconds: Timeout in seconds
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            import signal
            
            def timeout_handler(signum: int, frame: Any) -> None:
                raise TimeoutError(f"Function {func.__name__} timed out after {seconds} seconds")
            
            # Set the timeout
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(int(seconds))
            
            try:
                result = func(*args, **kwargs)
                signal.alarm(0)  # Cancel the alarm
                return result
            finally:
                signal.signal(signal.SIGALRM, old_handler)
        
        return wrapper
    return decorator


def create_cache_key(latitude: float, longitude: float, data_type: str = "weather") -> str:
    """
    Create a standardized cache key for weather data
    
    Args:
        latitude: Location latitude
        longitude: Location longitude  
        data_type: Type of data being cached
        
    Returns:
        Standardized cache key
    """
    # Round coordinates to reduce cache fragmentation
    lat_rounded = round(latitude, 4)
    lon_rounded = round(longitude, 4)
    return f"{data_type}_{lat_rounded}_{lon_rounded}"


def log_performance(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to log function execution time"""
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.info(f"{func.__name__} completed in {execution_time:.2f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"{func.__name__} failed after {execution_time:.2f}s: {e}")
            raise
    return wrapper