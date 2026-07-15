"""Cache manager for TechLead agent system.

Provides multi-level caching to improve performance:
1. File cache: Caches rule file contents
2. HTTP response cache: Caches external API responses
3. LLM response cache: Caches common LLM responses
4. Result cache: Caches agent processing results
"""

import hashlib
import json
import pickle
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional, Dict, List
from functools import wraps
import threading

from config import settings
from utils.logger import get_logger


class CacheManager:
    """Centralized cache manager with multi-level caching."""

    def __init__(self):
        """Initialize cache manager."""
        self.logger = get_logger("cache_manager")
        self.cache_enabled = getattr(settings, "cache_enabled", True)

        # Cache directories
        cache_dir_setting = getattr(settings, "cache_dir", "./storage/cache")
        self.cache_dir = Path(cache_dir_setting)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Cache files
        self.file_cache_file = self.cache_dir / "file_cache.pkl"
        self.http_cache_file = self.cache_dir / "http_cache.pkl"
        self.llm_cache_file = self.cache_dir / "llm_cache.pkl"
        self.result_cache_file = self.cache_dir / "result_cache.pkl"

        # In-memory caches
        self._file_cache: Dict[str, Any] = {}
        self._http_cache: Dict[str, Any] = {}
        self._llm_cache: Dict[str, Any] = {}
        self._result_cache: Dict[str, Any] = {}

        # Lock for thread safety
        self._lock = threading.RLock()

        # Load caches from disk on init
        self._load_caches()

        # Statistics
        self.stats = {
            "file_hits": 0,
            "file_misses": 0,
            "http_hits": 0,
            "http_misses": 0,
            "llm_hits": 0,
            "llm_misses": 0,
            "result_hits": 0,
            "result_misses": 0,
        }

    def _get_cache_key(self, *args, **kwargs) -> str:
        """Generate cache key from args and kwargs.

        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            str: Cache key
        """
        key_data = {
            "args": [str(a) for a in args],
            "kwargs": {k: str(v) for k, v in kwargs.items()},
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()

    def _get_cache_path(self, cache_type: str, key: str) -> Path:
        """Get cache file path.

        Args:
            cache_type: Cache type (file, http, llm, result)
            key: Cache key

        Returns:
            Path: Cache file path
        """
        subdir = cache_type
        subdir_path = self.cache_dir / subdir
        subdir_path.mkdir(parents=True, exist_ok=True)
        return subdir_path / f"{key}.json"

    def _load_caches(self):
        """Load all caches from disk."""
        if not self.cache_enabled:
            return

        try:
            # Load file cache
            if self.file_cache_file.exists():
                with open(self.file_cache_file, "rb") as f:
                    self._file_cache = pickle.load(f)
                self.logger.info(f"Loaded file cache: {len(self._file_cache)} entries")

            # Load HTTP cache
            if self.http_cache_file.exists():
                with open(self.http_cache_file, "rb") as f:
                    self._http_cache = pickle.load(f)
                self.logger.info(f"Loaded HTTP cache: {len(self._http_cache)} entries")

            # Load LLM cache
            if self.llm_cache_file.exists():
                with open(self.llm_cache_file, "rb") as f:
                    self._llm_cache = pickle.load(f)
                self.logger.info(f"Loaded LLM cache: {len(self._llm_cache)} entries")

            # Load result cache
            if self.result_cache_file.exists():
                with open(self.result_cache_file, "rb") as f:
                    self._result_cache = pickle.load(f)
                self.logger.info(f"Loaded result cache: {len(self._result_cache)} entries")

        except Exception as e:
            self.logger.warning(f"Failed to load caches: {e}")
            self._file_cache = {}
            self._http_cache = {}
            self._llm_cache = {}
            self._result_cache = {}

    def _save_caches(self):
        """Save all caches to disk."""
        if not self.cache_enabled:
            return

        try:
            with self._lock:
                with open(self.file_cache_file, "wb") as f:
                    pickle.dump(self._file_cache, f)
                with open(self.http_cache_file, "wb") as f:
                    pickle.dump(self._http_cache, f)
                with open(self.llm_cache_file, "wb") as f:
                    pickle.dump(self._llm_cache, f)
                with open(self.result_cache_file, "wb") as f:
                    pickle.dump(self._result_cache, f)
        except Exception as e:
            self.logger.error(f"Failed to save caches: {e}")

    # ==================== File Cache ====================

    def get_file(self, path: str) -> Optional[Any]:
        """Get cached file content.

        Args:
            path: File path

        Returns:
            Cached content or None
        """
        if not self.cache_enabled:
            return None

        key = f"file:{path}"
        with self._lock:
            if key in self._file_cache:
                entry = self._file_cache[key]
                # Check if expired
                if entry["expires_at"] and datetime.now() > entry["expires_at"]:
                    del self._file_cache[key]
                    self.stats["file_misses"] += 1
                    return None

                self.stats["file_hits"] += 1
                return entry["data"]

            self.stats["file_misses"] += 1
            return None

    def set_file(self, path: str, data: Any, ttl_hours: int = 24):
        """Cache file content.

        Args:
            path: File path
            data: Data to cache
            ttl_hours: Time to live in hours
        """
        if not self.cache_enabled:
            return

        key = f"file:{path}"
        with self._lock:
            self._file_cache[key] = {
                "data": data,
                "expires_at": datetime.now() + timedelta(hours=ttl_hours),
            }
            # Save to disk in background
            self._save_caches()

    def invalidate_file(self, path: str):
        """Invalidate cached file.

        Args:
            path: File path
        """
        if not self.cache_enabled:
            return

        key = f"file:{path}"
        with self._lock:
            if key in self._file_cache:
                del self._file_cache[key]
                self._save_caches()

    # ==================== HTTP Cache ====================

    def get_http(
        self,
        url: str,
        method: str = "GET",
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get cached HTTP response.

        Args:
            url: Request URL
            method: HTTP method
            params: Query parameters
            headers: Request headers

        Returns:
            Cached response or None
        """
        if not self.cache_enabled:
            return None

        key = self._get_cache_key(method, url, sorted(params.items()) if params else None, sorted(headers.items()) if headers else None)
        with self._lock:
            if key in self._http_cache:
                entry = self._http_cache[key]
                if entry["expires_at"] and datetime.now() > entry["expires_at"]:
                    del self._http_cache[key]
                    self.stats["http_misses"] += 1
                    return None

                self.stats["http_hits"] += 1
                return entry["data"]

            self.stats["http_misses"] += 1
            return None

    def set_http(
        self,
        url: str,
        data: Any,
        method: str = "GET",
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        ttl_minutes: int = 30,
    ):
        """Cache HTTP response.

        Args:
            url: Request URL
            data: Response data
            method: HTTP method
            params: Query parameters
            headers: Request headers
            ttl_minutes: Time to live in minutes
        """
        if not self.cache_enabled:
            return

        key = self._get_cache_key(method, url, sorted(params.items()) if params else None, sorted(headers.items()) if headers else None)
        with self._lock:
            self._http_cache[key] = {
                "data": data,
                "expires_at": datetime.now() + timedelta(minutes=ttl_minutes),
            }
            self._save_caches()

    # ==================== LLM Cache ====================

    def get_llm(self, prompt: str, model: str = "gpt-4o") -> Optional[str]:
        """Get cached LLM response.

        Args:
            prompt: Prompt text
            model: Model name

        Returns:
            Cached response or None
        """
        if not self.cache_enabled:
            return None

        key = self._get_cache_key("llm", prompt, model)
        with self._lock:
            if key in self._llm_cache:
                entry = self._llm_cache[key]
                if entry["expires_at"] and datetime.now() > entry["expires_at"]:
                    del self._llm_cache[key]
                    self.stats["llm_misses"] += 1
                    return None

                self.stats["llm_hits"] += 1
                return entry["response"]

            self.stats["llm_misses"] += 1
            return None

    def set_llm(self, prompt: str, response: str, model: str = "gpt-4o", ttl_hours: int = 2):
        """Cache LLM response.

        Args:
            prompt: Prompt text
            response: LLM response
            model: Model name
            ttl_hours: Time to live in hours
        """
        if not self.cache_enabled:
            return

        key = self._get_cache_key("llm", prompt, model)
        with self._lock:
            self._llm_cache[key] = {
                "response": response,
                "expires_at": datetime.now() + timedelta(hours=ttl_hours),
            }
            self._save_caches()

    # ==================== Result Cache ====================

    def get_result(self, cache_type: str, cache_key: str) -> Optional[Any]:
        """Get cached result.

        Args:
            cache_type: Type of result (design_review, code_review, etc.)
            cache_key: Unique key for this result

        Returns:
            Cached result or None
        """
        if not self.cache_enabled:
            return None

        key = f"{cache_type}:{cache_key}"
        with self._lock:
            if key in self._result_cache:
                entry = self._result_cache[key]
                if entry["expires_at"] and datetime.now() > entry["expires_at"]:
                    del self._result_cache[key]
                    self.stats["result_misses"] += 1
                    return None

                self.stats["result_hits"] += 1
                return entry["result"]

            self.stats["result_misses"] += 1
            return None

    def set_result(
        self,
        cache_type: str,
        cache_key: str,
        result: Any,
        ttl_minutes: int = 60,
    ):
        """Cache result.

        Args:
            cache_type: Type of result
            cache_key: Unique key
            result: Result data
            ttl_minutes: Time to live in minutes
        """
        if not self.cache_enabled:
            return

        key = f"{cache_type}:{cache_key}"
        with self._lock:
            self._result_cache[key] = {
                "result": result,
                "expires_at": datetime.now() + timedelta(minutes=ttl_minutes),
            }
            self._save_caches()

    # ==================== Statistics ====================

    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics.

        Returns:
            dict: Statistics dictionary
        """
        return self.stats.copy()

    def get_hit_rate(self, cache_type: Optional[str] = None) -> Dict[str, float]:
        """Get cache hit rates.

        Args:
            cache_type: Optional cache type filter

        Returns:
            dict: Hit rate statistics
        """
        if cache_type:
            cache_type_lower = cache_type.lower()
            key = f"{cache_type_lower}_hits"
            miss_key = f"{cache_type_lower}_misses"
            hits = self.stats.get(key, 0)
            misses = self.stats.get(miss_key, 0)
            total = hits + misses
            return {
                "hits": hits,
                "misses": misses,
                "hit_rate": hits / total if total > 0 else 0.0,
            }

        # All caches
        all_caches = ["file", "http", "llm", "result"]
        result = {}
        for cache in all_caches:
            result[cache] = self.get_hit_rate(cache)
        return result

    def clear_all(self):
        """Clear all caches."""
        with self._lock:
            self._file_cache.clear()
            self._http_cache.clear()
            self._llm_cache.clear()
            self._result_cache.clear()
            self.stats = {k: 0 for k in self.stats}
            self._save_caches()

    def clear_type(self, cache_type: str):
        """Clear cache of specific type and reset its statistics.

        Args:
            cache_type: Cache type (file, http, llm, result)
        """
        with self._lock:
            if cache_type == "file":
                self._file_cache.clear()
                self.stats["file_hits"] = 0
                self.stats["file_misses"] = 0
            elif cache_type == "http":
                self._http_cache.clear()
                self.stats["http_hits"] = 0
                self.stats["http_misses"] = 0
            elif cache_type == "llm":
                self._llm_cache.clear()
                self.stats["llm_hits"] = 0
                self.stats["llm_misses"] = 0
            elif cache_type == "result":
                self._result_cache.clear()
                self.stats["result_hits"] = 0
                self.stats["result_misses"] = 0
            self._save_caches()


# Global cache manager instance
_cache_manager: Optional[CacheManager] = None
_cache_lock = threading.Lock()


def get_cache_manager() -> CacheManager:
    """Get or create global cache manager instance.

    Returns:
        CacheManager: Cache manager instance
    """
    global _cache_manager
    with _cache_lock:
        if _cache_manager is None:
            _cache_manager = CacheManager()
    return _cache_manager


def cache_result(cache_type: str, ttl_minutes: int = 60):
    """Decorator to cache function results.

    Args:
        cache_type: Type of result (e.g., "design_review")
        ttl_minutes: Time to live in minutes

    Returns:
        Decorator function
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_manager = get_cache_manager()
            cache_key = cache_manager._get_cache_key(func.__name__, *args, **kwargs)

            # Try to get cached result
            cached = cache_manager.get_result(cache_type, cache_key)
            if cached is not None:
                return cached

            # Execute function
            result = await func(*args, **kwargs)

            # Cache result
            cache_manager.set_result(cache_type, cache_key, result, ttl_minutes)

            return result
        return wrapper
    return decorator
