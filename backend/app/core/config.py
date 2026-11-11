"""Application configuration using Pydantic Settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings loaded from environment or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PROJECT_NAME: str = "CLPS Luna Browser API"
    API_V1_STR: str = "/api/v1"
    APP_ENV: str = Field(default="development", description="development, staging, production")
    DEBUG: bool = Field(default=False)

    # Database connection string (PostgreSQL 18 + psycopg 3)
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://clps_app:clps_dev_pass_2026@localhost:5432/clps_luna"
    )

    # Storage
    MEDIA_ROOT: str = "./storage/media"
    IMPORT_STAGING_ROOT: str = "./storage/imports"

    # Security
    SECRET_KEY: str = Field(default="dev_secret_key_change_in_production_min_32_characters_long")
    SESSION_SECRET: str = Field(default="dev_session_secret_change_in_production_seed")
    SESSION_EXPIRE_HOURS: int = 24
    COOKIE_SECURE: bool | None = Field(
        default=None,
        description="Explicit override for cookie Secure attribute; defaults to HTTPS/production auto-detection.",
    )
    AUTH_LOCKOUT_THRESHOLD: int = 5
    AUTH_LOCKOUT_MINUTES: int = 15
    AUTH_RATE_LIMIT_MAX_ATTEMPTS: int = 15
    ENABLE_HSTS: bool = False

    def is_cookie_secure(
        self, request_scheme: str = "http", forwarded_proto: str | None = None
    ) -> bool:
        """Resolve cookie Secure flag cleanly for HTTP localhost dev vs HTTPS/production."""
        if self.COOKIE_SECURE is not None:
            return self.COOKIE_SECURE
        effective_proto = (
            (forwarded_proto or request_scheme or "http").split(",")[0].strip().lower()
        )
        return effective_proto == "https" or self.APP_ENV.lower() == "production"

    # CORS origins
    CORS_ORIGINS: str = (
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a typed list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # Public Base URL for canonical SEO URLs
    PUBLIC_BASE_URL: str = "http://localhost:3000"

    # Ollama Local AI
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "gemma4:e4b"
    OLLAMA_TIMEOUT_SECONDS: float = Field(
        default=15.0, description="HTTP timeout for Ollama inference"
    )
    OLLAMA_CIRCUIT_BREAKER_FAILURES: int = Field(
        default=3, description="Consecutive failures before tripping breaker"
    )
    OLLAMA_CIRCUIT_BREAKER_RESET_SECONDS: float = Field(
        default=60.0, description="Seconds before half-open retry"
    )

    # SPICE & DEM storage
    SPICE_KERNEL_DIR: str = "../data/spice-kernels"
    DEM_ROOT: str = "../data/lunar-dem"

    # Scientific Simulation Engine (Phase 4)
    SIM_LUNAR_REFERENCE_FRAME: str = "MOON_ME"
    SIM_ABERRATION_CORRECTION: str = "LT+S"
    SIM_DEFAULT_COARSE_INTERVAL_SECONDS: int = 900
    SIM_TRANSITION_TOLERANCE_SECONDS: float = 1.0
    SIM_MAX_COARSE_SAMPLES: int = 20000
    SIM_MAX_DURATION_SECONDS: int = 10 * 365 * 86400
    SIM_HORIZON_AZIMUTH_BINS: int = 360
    SIM_HORIZON_MAX_RADIUS_M: float = 100000.0
    SIM_HORIZON_MIN_RADIUS_M: float = 100.0
    SIM_OBSERVER_HEIGHT_M: float = 1.5
    SIM_WORKER_POLL_INTERVAL_SECONDS: float = 1.0
    SIM_WORKER_LEASE_SECONDS: int = 300
    SIM_WORKER_MAX_CONCURRENT: int = 2

    # CODEX Hardware network & safety settings
    WIFI_BRIDGE_IP: str = "192.168.1.101"
    WIFI_BRIDGE_PORT: int = 80
    MOON_S3_IP: str = "192.168.1.102"
    MOON_S3_PORT: int = 80
    CODEX_SHARED_SECRET: str = "dev_codex_shared_secret_hardware_key_2026"
    CODEX_TRANSPORT_MODE: str = Field(
        default="mock",
        description="Hardware transport backend: 'mock' (simulated bench devices) or 'http' (real lab controllers)",
    )
    CODEX_REQUEST_TIMEOUT_SECONDS: float = 5.0
    CODEX_COMMAND_TTL_SECONDS: int = 300
    CODEX_HEARTBEAT_STALE_SECONDS: int = 30
    CODEX_REQUIRE_VERIFIED_BENCH: bool = True

    @staticmethod
    def _resolve_repo_relative_dir(raw_path: str) -> str:
        """Resolve data directory robustly whether executed from repo root or backend/."""
        from pathlib import Path

        candidate = Path(raw_path).expanduser()
        if candidate.is_absolute():
            return str(candidate.resolve())
        if candidate.exists():
            return str(candidate.resolve())
        # Fallback: resolve relative to CLPS Lunar Module project root (2 levels above app/core)
        project_root = Path(__file__).resolve().parents[3]
        if raw_path.startswith("./"):
            alt = (project_root / raw_path[2:]).resolve()
            if alt.exists():
                return str(alt)
        backend_root = Path(__file__).resolve().parents[2]
        return str((backend_root / candidate).resolve())

    @property
    def resolved_spice_kernel_dir(self) -> str:
        """Return canonical existing directory path for controlled SPICE kernels."""
        return self._resolve_repo_relative_dir(self.SPICE_KERNEL_DIR)

    @property
    def resolved_dem_root(self) -> str:
        """Return canonical existing directory path for controlled LOLA DEM assets."""
        return self._resolve_repo_relative_dir(self.DEM_ROOT)


settings = Settings()
