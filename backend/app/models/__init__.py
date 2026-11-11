"""Central export of all SQLAlchemy 2.0 models for Alembic and application queries."""

from app.db.base import Base

# Admin & system
from app.models.admin import (
    Admin,
    AdminRoleLink,
    AdminSession,
    AuditLog,
    HealthCheck,
    Role,
    SystemComponent,
)

# Catalogue & narrative
from app.models.catalogue import (
    LandingSite,
    NASARegion,
    SiteAlias,
    SiteContent,
    SiteHistory,
    SiteMedia,
    SiteProCon,
)

# CODEX hardware & calibration
from app.models.codex import (
    CodePlaceholder,
    CodexCommandNonce,
    HardwareCodeVersion,
    HardwareCommandAcknowledgement,
    HardwareConfiguration,
    HardwareDevice,
    HardwareEvent,
    HardwareRun,
    MoonLedRegion,
    MoonLedRegionPixel,
    MotorCalibrationProfile,
)

# Comparison
from app.models.comparison import (
    ComparisonProfile,
    ComparisonProfileParameter,
    ComparisonResult,
    ComparisonRun,
)

# Metrics & observations
from app.models.metrics import (
    MetricObservation,
    ParameterDefinition,
    SiteMetric,
)

# Operations, queue & builds
from app.models.operations import (
    BackgroundJob,
    ContactMessage,
    FirmwareBuild,
)

# Provenance & import staging
from app.models.provenance import (
    DatasetImport,
    DataSource,
    ImportRow,
    SiteSourceLink,
)

# Simulation
from app.models.simulation import (
    SimulationEventWindow,
    SimulationMetric,
    SimulationRun,
    SimulationSample,
    TerrainHorizonProfile,
)

__all__ = [
    "Admin",
    "AdminRoleLink",
    "AdminSession",
    "AuditLog",
    "BackgroundJob",
    "Base",
    "CodePlaceholder",
    "CodexCommandNonce",
    "ComparisonProfile",
    "ComparisonProfileParameter",
    "ComparisonResult",
    "ComparisonRun",
    "ContactMessage",
    "DataSource",
    "DatasetImport",
    "FirmwareBuild",
    "HardwareCodeVersion",
    "HardwareCommandAcknowledgement",
    "HardwareConfiguration",
    "HardwareDevice",
    "HardwareEvent",
    "HardwareRun",
    "HealthCheck",
    "ImportRow",
    "LandingSite",
    "MetricObservation",
    "MoonLedRegion",
    "MoonLedRegionPixel",
    "MotorCalibrationProfile",
    "NASARegion",
    "ParameterDefinition",
    "Role",
    "SimulationEventWindow",
    "SimulationMetric",
    "SimulationRun",
    "SimulationSample",
    "SiteAlias",
    "SiteContent",
    "SiteHistory",
    "SiteMedia",
    "SiteMetric",
    "SiteProCon",
    "SiteSourceLink",
    "SystemComponent",
    "TerrainHorizonProfile",
]
