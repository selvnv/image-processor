"""In-memory caches for the image processor.

The service keeps no persistent state, but caching decoded images in memory
avoids re-uploading and re-decoding on every parameter change while the
frontend polls for size estimates.
"""

import threading
import time
import uuid
from collections import OrderedDict

from .schemas import ProcessOptions


class TTLCache:
    """A small thread-safe LRU cache with a per-entry time-to-live."""

    def __init__(self, max_entries: int = 100, ttl_seconds: int = 600):
        self._lock = threading.Lock()
        self._entries = OrderedDict()
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds

    def get(self, key):
        with self._lock:
            self._evict_expired()
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return entry[0]

    def put(self, key, value):
        with self._lock:
            self._evict_expired()
            self._entries[key] = (value, time.time())
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def _evict_expired(self):
        now = time.time()
        expired = [
            key for key, (_, created) in self._entries.items()
            if now - created > self._ttl_seconds
        ]
        for key in expired:
            self._entries.pop(key, None)


# Decoded images: file_id -> (PIL.Image, input_format)
image_cache = TTLCache(max_entries=50, ttl_seconds=600)

# Computed sizes: (file_id, params) -> int (bytes)
result_cache = TTLCache(max_entries=500, ttl_seconds=300)


def store_image(image, input_format: str) -> str:
    """Store a decoded image and return its id."""
    file_id = uuid.uuid4().hex
    image_cache.put(file_id, (image, input_format))
    return file_id


def result_key(file_id: str, options: ProcessOptions) -> tuple:
    """Deterministic cache key for a (file, options) combination."""
    return (
        file_id,
        options.width,
        options.height,
        options.mode,
        options.format,
        options.quality,
    )
