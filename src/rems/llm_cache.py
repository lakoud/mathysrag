"""LLM Cache implementation with TTL and metrics tracking."""

import hashlib
import json
import sqlite3
import time
from pathlib import Path

from langchain_core.caches import BaseCache
from langchain_core.outputs import Generation

from rems.config import settings

class REMSLLMCache(BaseCache):
    """
    A custom SQLite-based cache for LangChain that tracking hits/misses 
    and handles Time-To-Live (TTL).
    """

    def __init__(self, db_path: str = ".rems_llm_cache.db", ttl_seconds: int | None = None):
        """Initialize the cache."""
        self.db_path = Path(db_path)
        self.ttl_seconds = ttl_seconds if ttl_seconds is not None else settings.llm_cache_ttl
        self.enabled = settings.llm_cache_enabled
        
        # Metrics
        self.hits = 0
        self.misses = 0

        if self.enabled:
            self._init_db()

    def _init_db(self):
        """Initialize the SQLite database schema."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS llm_cache (
                    hash_key TEXT PRIMARY KEY,
                    response TEXT,
                    expires_at REAL
                )
            """)
            conn.commit()

    def _generate_key(self, prompt: str, llm_string: str) -> str:
        """Generate a SHA-256 hash for the cache key."""
        content = f"{prompt}---{llm_string}".encode("utf-8")
        return hashlib.sha256(content).hexdigest()

    def lookup(self, prompt: str, llm_string: str) -> list[Generation] | None:
        """Look up based on prompt and llm_string."""
        if not self.enabled:
            return None

        key = self._generate_key(prompt, llm_string)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT response, expires_at FROM llm_cache WHERE hash_key = ?", 
                (key,)
            )
            row = cursor.fetchone()

            if row:
                response_str, expires_at = row
                # Check TTL
                if expires_at and time.time() > expires_at:
                    self.misses += 1
                    # Clean up expired entry
                    cursor.execute("DELETE FROM llm_cache WHERE hash_key = ?", (key,))
                    conn.commit()
                    return None
                
                self.hits += 1
                
                # Deserialize LangChain generation
                try:
                    data = json.loads(response_str)
                    return [Generation(**gen) for gen in data]
                except (json.JSONDecodeError, TypeError):
                    self.misses += 1
                    return None

        self.misses += 1
        return None

    def update(self, prompt: str, llm_string: str, return_val: list[Generation]) -> None:
        """Update cache based on prompt and llm_string."""
        if not self.enabled:
            return

        key = self._generate_key(prompt, llm_string)
        
        # Serialize list of Generations to JSON string
        try:
            data = [gen.dict() for gen in return_val]
            response_str = json.dumps(data)
        except Exception:
            # If we cannot serialize, we don't cache
            return

        expires_at = time.time() + self.ttl_seconds if self.ttl_seconds else None

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO llm_cache (hash_key, response, expires_at)
                VALUES (?, ?, ?)
            """, (key, response_str, expires_at))
            conn.commit()

    def clear(self, **kwargs) -> None:
        """Clear the cache."""
        if not self.enabled:
            return
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM llm_cache")
            conn.commit()
        self.hits = 0
        self.misses = 0

    def get_metrics(self) -> dict:
        """Return the current metrics and hit rate."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "total_calls": total,
            "hit_rate_percent": round(hit_rate, 2),
            "savings_percent": round(hit_rate, 2), # Hit rate directly correlates to savings
        }

# Global singleton instance for the session
llm_cache = REMSLLMCache()
