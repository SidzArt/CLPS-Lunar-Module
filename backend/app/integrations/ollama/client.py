"""HTTP client and circuit breaker for local Ollama AI model."""

import json
import logging
import time
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("app.integrations.ollama")


class OllamaError(Exception):
    """Base exception for Ollama API communication failures."""


class OllamaCircuitBreakerOpenError(OllamaError):
    """Raised when circuit breaker is active and blocking calls."""


class OllamaClient:
    """Client for local Ollama instance with health check and circuit breaker."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_failures: int | None = None,
        reset_timeout: float | None = None,
    ) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.timeout = timeout or settings.OLLAMA_TIMEOUT_SECONDS
        self.max_failures = max_failures or settings.OLLAMA_CIRCUIT_BREAKER_FAILURES
        self.reset_timeout = reset_timeout or settings.OLLAMA_CIRCUIT_BREAKER_RESET_SECONDS

        # Circuit breaker state
        self._consecutive_failures: int = 0
        self._circuit_open_since: float | None = None

    @property
    def is_circuit_open(self) -> bool:
        """Check if circuit breaker is currently open."""
        if self._circuit_open_since is None:
            return False
        elapsed = time.time() - self._circuit_open_since
        if elapsed > self.reset_timeout:
            # Half-open: allow a trial request
            logger.info(
                "Ollama circuit breaker entering half-open trial state after %.1fs", elapsed
            )
            self._circuit_open_since = None
            return False
        return True

    def _record_success(self) -> None:
        """Reset circuit breaker counters on a successful call."""
        if self._consecutive_failures > 0 or self._circuit_open_since is not None:
            logger.info("Ollama client recovered. Circuit breaker reset.")
        self._consecutive_failures = 0
        self._circuit_open_since = None

    def _record_failure(self, reason: str) -> None:
        """Increment failure counter and trip circuit breaker if threshold reached."""
        self._consecutive_failures += 1
        logger.warning(
            "Ollama call failed (%d/%d): %s",
            self._consecutive_failures,
            self.max_failures,
            reason,
        )
        if self._consecutive_failures >= self.max_failures:
            self._circuit_open_since = time.time()
            logger.error(
                "Ollama circuit breaker TRIPPED. Blocking calls for %.1f seconds.",
                self.reset_timeout,
            )

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send prompt to Ollama with format='json' and return parsed JSON dictionary."""
        if self.is_circuit_open:
            raise OllamaCircuitBreakerOpenError(
                f"Ollama circuit breaker is OPEN (consecutive failures: {self._consecutive_failures})."
            )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": schema if schema is not None else "json",
            "think": False,
            "keep_alive": "15m",
            "options": {
                "temperature": 0.1,  # Low temperature for strict determinism
                "num_predict": 350,
            },
        }

        url = f"{self.base_url}/api/chat"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                t0 = time.perf_counter()
                resp = await client.post(url, json=payload)
                t1 = time.perf_counter()

                if resp.status_code != 200:
                    self._record_failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
                    raise OllamaError(f"Ollama returned HTTP {resp.status_code}")

                data = resp.json()
                content = data.get("message", {}).get("content", "")
                parsed = json.loads(content)
                self._record_success()
                logger.info(
                    "Ollama structured extraction succeeded in %.2fs using model %s",
                    t1 - t0,
                    self.model,
                )
                return parsed

        except httpx.TimeoutException as exc:
            self._record_failure(f"Timeout after {self.timeout}s")
            raise OllamaError(f"Ollama request timed out after {self.timeout}s") from exc
        except httpx.ConnectError as exc:
            self._record_failure("Connection refused / daemon offline")
            raise OllamaError("Failed to connect to local Ollama daemon") from exc
        except json.JSONDecodeError as exc:
            self._record_failure(f"Malformed JSON response: {exc}")
            raise OllamaError("Ollama returned invalid JSON payload") from exc
        except Exception as exc:
            self._record_failure(str(exc))
            raise OllamaError(f"Unexpected error communicating with Ollama: {exc}") from exc


# Global singleton instance
ollama_client = OllamaClient()
