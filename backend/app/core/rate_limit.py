"""In-memory sliding-window rate limiter and concurrency guard for API endpoints."""

import asyncio
import time
from collections import deque
from collections.abc import AsyncGenerator

from fastapi import HTTPException, Request, status

from app.core.config import settings


class InMemoryRateLimiter:
    """Sliding-window rate limiter with bounded concurrency using FastAPI yield dependency."""

    def __init__(
        self,
        requests_per_minute: int = 60,
        max_concurrent: int = 10,
        name: str = "default",
    ) -> None:
        self.requests_per_minute = requests_per_minute
        self.max_concurrent = max_concurrent
        self.name = name
        self.window_seconds = 60.0

        self._lock = asyncio.Lock()
        self._history: dict[str, deque[float]] = {}
        self._current_active: int = 0
        self._enabled: bool = True

    def disable(self) -> None:
        """Temporarily disable limiter."""
        self._enabled = False

    def enable(self) -> None:
        """Re-enable limiter."""
        self._enabled = True

    def reset(self) -> None:
        """Reset all tracked request history and concurrency counters."""
        self._history.clear()
        self._current_active = 0

    async def __call__(self, request: Request) -> AsyncGenerator[None, None]:
        """FastAPI yield dependency enforcing rate and concurrency bounds."""
        if not self._enabled:
            yield
            return

        client_host = request.client.host if request.client else "127.0.0.1"
        now = time.time()
        acquired = False

        try:
            async with self._lock:
                # 1. Check active concurrency ceiling
                if self._current_active >= self.max_concurrent:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=(
                            f"Concurrent request limit exceeded for {self.name}. "
                            f"Maximum concurrent requests: {self.max_concurrent}."
                        ),
                        headers={"Retry-After": "2"},
                    )

                # 2. Check sliding-window request rate
                timestamps = self._history.setdefault(client_host, deque())
                while timestamps and (now - timestamps[0]) > self.window_seconds:
                    timestamps.popleft()

                if len(timestamps) >= self.requests_per_minute:
                    retry_after = int(self.window_seconds - (now - timestamps[0])) + 1
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=(
                            f"Rate limit exceeded for {self.name}. "
                            f"Limit is {self.requests_per_minute} requests per minute."
                        ),
                        headers={"Retry-After": str(max(1, retry_after))},
                    )

                timestamps.append(now)
                self._current_active += 1
                acquired = True

            yield
        finally:
            if acquired:
                async with self._lock:
                    if self._current_active > 0:
                        self._current_active -= 1


# Pre-configured instances aligned with Phase 3 specification
compare_rate_limiter = InMemoryRateLimiter(
    requests_per_minute=60,
    max_concurrent=20,
    name="Compare Engine",
)

ai_assist_rate_limiter = InMemoryRateLimiter(
    requests_per_minute=15,
    max_concurrent=2,
    name="Ollama AI Assist",
)

simulation_rate_limiter = InMemoryRateLimiter(
    requests_per_minute=20,
    max_concurrent=5,
    name="Scientific Simulation Engine",
)

codex_rate_limiter = InMemoryRateLimiter(
    requests_per_minute=30,
    max_concurrent=4,
    name="CODEX Hardware Orchestration",
)

contact_rate_limiter = InMemoryRateLimiter(
    requests_per_minute=10,
    max_concurrent=5,
    name="Public Contact Form",
)

auth_login_rate_limiter = InMemoryRateLimiter(
    requests_per_minute=settings.AUTH_RATE_LIMIT_MAX_ATTEMPTS,
    max_concurrent=10,
    name="Admin Authentication",
)
