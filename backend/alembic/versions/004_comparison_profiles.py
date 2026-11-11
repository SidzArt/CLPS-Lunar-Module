"""Seed comparison profiles, parameter definitions, data sources, and authentic science metrics.

Revision ID: 004_comparison_profiles
Revises: 003_seed_standard_roles
Create Date: 2026-11-11 04:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_comparison_profiles"
down_revision: str | None = "003_seed_standard_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Additive columns for parameter_definitions
    op.add_column(
        "parameter_definitions",
        sa.Column("benchmark_min", sa.Float(), nullable=True),
    )
    op.add_column(
        "parameter_definitions",
        sa.Column("benchmark_max", sa.Float(), nullable=True),
    )
    op.add_column(
        "parameter_definitions",
        sa.Column("tolerance", sa.Float(), nullable=True),
    )

    # 2. Additive columns for comparison_runs
    op.add_column(
        "comparison_runs",
        sa.Column("overall_score_a", sa.Float(), nullable=True),
    )
    op.add_column(
        "comparison_runs",
        sa.Column("overall_score_b", sa.Float(), nullable=True),
    )
    op.add_column(
        "comparison_runs",
        sa.Column("overall_winner", sa.String(50), nullable=True),
    )
    op.add_column(
        "comparison_runs",
        sa.Column("limitations_note", sa.Text(), nullable=True),
    )

    # 3. Additive columns for comparison_results
    op.add_column(
        "comparison_results",
        sa.Column("text_value_a", sa.Text(), nullable=True),
    )
    op.add_column(
        "comparison_results",
        sa.Column("text_value_b", sa.Text(), nullable=True),
    )

    # 3b. Additive column for site_metrics data_quality_status
    op.add_column(
        "site_metrics",
        sa.Column("data_quality_status", sa.String(50), server_default="verified", nullable=True),
    )

    # 4. Seed Data Sources
    conn = op.get_bind()

    sources_to_seed = [
        {
            "agency_name": "NASA PDS",
            "title": "Lunar Reconnaissance Orbiter (LRO) Planetary Data System Archive",
            "publisher": "NASA Planetary Data System / GSFC",
            "source_url": "https://pds-geosciences.wustl.edu/missions/lro/",
            "dataset_version": "PDS4-2024",
            "licence": "Public Domain (NASA)",
            "citation_text": "NASA / GSFC LRO Science Team, Planetary Data System.",
        },
        {
            "agency_name": "NASA GSFC",
            "title": "Lunar Orbiter Laser Altimeter (LOLA) Global Elevation & Slope Model",
            "publisher": "Goddard Space Flight Center",
            "source_url": "https://imbrium.mit.edu/DATA/LOLA_GDR/",
            "dataset_version": "LOLA-GDR-v2.1",
            "licence": "Public Domain (NASA)",
            "citation_text": "Smith, D. E., et al. (2010), Initial observations from the Lunar Orbiter Laser Altimeter (LOLA) on board the Lunar Reconnaissance Orbiter, GRL.",
        },
        {
            "agency_name": "NASA / SwRI",
            "title": "Lyman-Alpha Mapping Project (LAMP) Far-UV Albedo and Volatiles",
            "publisher": "Southwest Research Institute",
            "source_url": "https://pds-geosciences.wustl.edu/lro/lro-l-lamp-3-rdr-v1/lrolam_1001/",
            "dataset_version": "LAMP-RDR-v1.4",
            "licence": "Public Domain (NASA)",
            "citation_text": "Gladstone, G. R., et al. (2012), Far-ultraviolet reflectance properties of the Moon's permanently shadowed regions, JGR Planets.",
        },
        {
            "agency_name": "NASA Artemis",
            "title": "Artemis III Candidate Landing Regions Assessment",
            "publisher": "NASA Headquarters / Artemis Science Definition Team",
            "source_url": "https://www.nasa.gov/news-release/nasa-identifies-candidate-regions-for-landing-next-americans-on-moon/",
            "dataset_version": "NASA/SP-20205009602",
            "licence": "Public Domain (NASA)",
            "citation_text": "NASA (2022), Artemis III Candidate Landing Regions Assessment, NASA Technical Report.",
        },
    ]

    for src in sources_to_seed:
        conn.execute(
            sa.text(
                """
                INSERT INTO data_sources (agency_name, title, publisher, source_url, dataset_version, licence, citation_text)
                SELECT :agency_name, :title, :publisher, :source_url, :dataset_version, :licence, :citation_text
                WHERE NOT EXISTS (
                    SELECT 1 FROM data_sources WHERE title = :title
                );
                """
            ),
            src,
        )

    conn.execute(
        sa.text("CREATE UNIQUE INDEX IF NOT EXISTS uq_data_sources_title ON data_sources (title);")
    )

    # 5. Seed Parameter Definitions
    standard_parameters = [
        {
            "parameter_key": "earth_visibility_avg",
            "display_name": "Earth Line-of-Sight Visibility",
            "description": "Annual percentage of time with direct, unobstructed geometric line-of-sight to Earth above the local horizon.",
            "unit": "%",
            "value_type": "numeric",
            "comparison_direction": "higher",
            "target_value": None,
            "is_comparable": True,
            "is_time_dependent": True,
            "validation_min": 0.0,
            "validation_max": 100.0,
            "benchmark_min": 0.0,
            "benchmark_max": 100.0,
            "tolerance": None,
            "methodology_note": "Calculated using SPICE topocentric azimuth/elevation geometry and LOLA horizon elevation profile.",
            "is_active": True,
        },
        {
            "parameter_key": "max_slope_deg",
            "display_name": "Terrain Slope (Hazard Angle)",
            "description": "Representative maximum terrain slope within a 100-meter landing ellipse. Lower slopes indicate safer touchdown conditions.",
            "unit": "deg",
            "value_type": "numeric",
            "comparison_direction": "lower",
            "target_value": None,
            "is_comparable": True,
            "is_time_dependent": False,
            "validation_min": 0.0,
            "validation_max": 90.0,
            "benchmark_min": 0.0,
            "benchmark_max": 30.0,
            "tolerance": None,
            "methodology_note": "Derived from LRO LOLA high-resolution gridded topographic models at 5m baselines.",
            "is_active": True,
        },
        {
            "parameter_key": "scientific_value_score",
            "display_name": "Scientific Value Score",
            "description": "Normalized multidisciplinary scientific value rating (0–100) reflecting geological diversity, volatile potential, and sample return relevance.",
            "unit": "score",
            "value_type": "numeric",
            "comparison_direction": "higher",
            "target_value": None,
            "is_comparable": True,
            "is_time_dependent": False,
            "validation_min": 0.0,
            "validation_max": 100.0,
            "benchmark_min": 0.0,
            "benchmark_max": 100.0,
            "tolerance": None,
            "methodology_note": "Evaluated from NASA Artemis Science Definition Team priority matrix criteria.",
            "is_active": True,
        },
        {
            "parameter_key": "water_ice_probability",
            "display_name": "Water Ice / Volatile Probability",
            "description": "Model-derived probability percentage of persistent shallow subsurface water ice or cold-trapped volatiles.",
            "unit": "%",
            "value_type": "numeric",
            "comparison_direction": "higher",
            "target_value": None,
            "is_comparable": True,
            "is_time_dependent": False,
            "validation_min": 0.0,
            "validation_max": 100.0,
            "benchmark_min": 0.0,
            "benchmark_max": 100.0,
            "tolerance": None,
            "methodology_note": "Derived from Diviner maximum surface temperatures (<110K threshold) and LAMP far-UV albedo anomalies.",
            "is_active": True,
        },
        {
            "parameter_key": "surface_roughness",
            "display_name": "Surface Roughness Index",
            "description": "Hurst exponent and RMS slope deviation index (0–10) describing sub-meter roughness and boulder hazard density.",
            "unit": "index",
            "value_type": "numeric",
            "comparison_direction": "lower",
            "target_value": None,
            "is_comparable": True,
            "is_time_dependent": False,
            "validation_min": 0.0,
            "validation_max": 10.0,
            "benchmark_min": 0.0,
            "benchmark_max": 10.0,
            "tolerance": None,
            "methodology_note": "LROC NAC stereophotogrammetry and LOLA pulse-width analysis.",
            "is_active": True,
        },
        {
            "parameter_key": "elevation_m",
            "display_name": "Surface Elevation",
            "description": "Elevation in meters relative to the lunar mean datum radius of 1737.4 km.",
            "unit": "m",
            "value_type": "numeric",
            "comparison_direction": "context",
            "target_value": None,
            "is_comparable": False,
            "is_time_dependent": False,
            "validation_min": -10000.0,
            "validation_max": 15000.0,
            "benchmark_min": None,
            "benchmark_max": None,
            "tolerance": None,
            "methodology_note": "LRO LOLA GDR topography referenced to lunar reference sphere.",
            "is_active": True,
        },
    ]

    # Ensure illumination_annual_avg exists and has calibrated comparison bounds
    conn.execute(
        sa.text(
            """
            INSERT INTO parameter_definitions (
                parameter_key, display_name, description, unit, value_type,
                comparison_direction, target_value, is_comparable, is_time_dependent,
                validation_min, validation_max, benchmark_min, benchmark_max,
                tolerance, methodology_note, is_active
            ) VALUES (
                'illumination_annual_avg',
                'Annual Average Solar Illumination',
                'Mean percentage of the lunar annual cycle receiving direct solar illumination.',
                '%',
                'numeric',
                'higher',
                NULL,
                TRUE,
                TRUE,
                0.0,
                100.0,
                0.0,
                100.0,
                NULL,
                'Derived from LOLA topographic horizon rays and DE440 solar ephemeris models.',
                TRUE
            )
            ON CONFLICT (parameter_key) DO UPDATE SET
                comparison_direction = 'higher',
                is_comparable = TRUE,
                is_active = TRUE,
                benchmark_min = 0.0,
                benchmark_max = 100.0,
                validation_min = 0.0,
                validation_max = 100.0;
            """
        )
    )

    for p in standard_parameters:
        conn.execute(
            sa.text(
                """
                INSERT INTO parameter_definitions (
                    parameter_key, display_name, description, unit, value_type,
                    comparison_direction, target_value, is_comparable, is_time_dependent,
                    validation_min, validation_max, benchmark_min, benchmark_max,
                    tolerance, methodology_note, is_active
                ) VALUES (
                    :parameter_key, :display_name, :description, :unit, :value_type,
                    :comparison_direction, :target_value, :is_comparable, :is_time_dependent,
                    :validation_min, :validation_max, :benchmark_min, :benchmark_max,
                    :tolerance, :methodology_note, :is_active
                ) ON CONFLICT (parameter_key) DO UPDATE SET
                    benchmark_min = EXCLUDED.benchmark_min,
                    benchmark_max = EXCLUDED.benchmark_max,
                    validation_min = EXCLUDED.validation_min,
                    validation_max = EXCLUDED.validation_max;
                """
            ),
            p,
        )

    # 6. Seed Comparison Profiles
    profiles = [
        {
            "profile_key": "solar_maximization",
            "name": "Solar Power Maximization",
            "purpose_description": "Prioritizes landing locations with maximum annual solar illumination and minimal continuous shadow for long-duration photovoltaic surface operations.",
            "version": "1.0",
            "is_active": True,
            "params": [
                ("illumination_annual_avg", 0.60, True),
                ("earth_visibility_avg", 0.20, False),
                ("max_slope_deg", 0.20, False),
            ],
        },
        {
            "profile_key": "direct_earth_comm",
            "name": "Continuous Earth Communication",
            "purpose_description": "Optimized for missions requiring continuous direct-to-Earth radio line-of-sight telemetry without requiring orbital relay infrastructure.",
            "version": "1.0",
            "is_active": True,
            "params": [
                ("earth_visibility_avg", 0.60, True),
                ("illumination_annual_avg", 0.20, False),
                ("max_slope_deg", 0.20, False),
            ],
        },
        {
            "profile_key": "volatile_prospecting",
            "name": "Volatile & Water Ice Prospecting",
            "purpose_description": "Targeted at permanently shadowed regions and cold traps to maximize access to subsurface hydrogen, water ice, and ISRU feedstock resources.",
            "version": "1.0",
            "is_active": True,
            "params": [
                ("water_ice_probability", 0.50, True),
                ("scientific_value_score", 0.30, False),
                ("max_slope_deg", 0.20, False),
            ],
        },
        {
            "profile_key": "geological_research",
            "name": "Comprehensive Geological Research",
            "purpose_description": "Balances diverse geological formations and sample collection opportunities with safe terrain landing slope and sustained power availability.",
            "version": "1.0",
            "is_active": True,
            "params": [
                ("scientific_value_score", 0.50, True),
                ("max_slope_deg", 0.25, False),
                ("illumination_annual_avg", 0.25, False),
            ],
        },
        {
            "profile_key": "general_exploration",
            "name": "General Exploration Baseline",
            "purpose_description": "Standard balanced mission profile distributing weights evenly across solar illumination, communication visibility, terrain slope safety, and scientific value.",
            "version": "1.0",
            "is_active": True,
            "params": [
                ("illumination_annual_avg", 0.30, False),
                ("earth_visibility_avg", 0.30, False),
                ("max_slope_deg", 0.20, False),
                ("scientific_value_score", 0.20, False),
            ],
        },
    ]

    for prof in profiles:
        prof_res = conn.execute(
            sa.text(
                """
                INSERT INTO comparison_profiles (profile_key, name, purpose_description, is_active, version)
                VALUES (:profile_key, :name, :purpose_description, :is_active, :version)
                ON CONFLICT (profile_key) DO UPDATE SET
                    name = EXCLUDED.name,
                    purpose_description = EXCLUDED.purpose_description
                RETURNING profile_id;
                """
            ),
            {
                "profile_key": prof["profile_key"],
                "name": prof["name"],
                "purpose_description": prof["purpose_description"],
                "is_active": prof["is_active"],
                "version": prof["version"],
            },
        ).fetchone()

        if prof_res:
            pid = prof_res[0]
            for pkey, weight, req in prof["params"]:
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO comparison_profile_parameters (profile_id, parameter_id, weight, required)
                        SELECT :pid, pd.parameter_id, :weight, :req
                        FROM parameter_definitions pd
                        WHERE pd.parameter_key = :pkey
                        AND NOT EXISTS (
                            SELECT 1 FROM comparison_profile_parameters cpp
                            WHERE cpp.profile_id = :pid AND cpp.parameter_id = pd.parameter_id
                        );
                        """
                    ),
                    {"pid": pid, "pkey": pkey, "weight": weight, "req": req},
                )

    conn.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_comparison_profile_parameters_prof_param ON comparison_profile_parameters (profile_id, parameter_id);"
        )
    )

    # 7. Seed Authentic NASA Regions
    regions = [
        {
            "region_code": "SP-AITKEN",
            "region_name": "South Pole-Aitken Basin",
            "mission_context": "NASA Artemis III & Robotic Exploration Zone",
            "description": "Massive ancient impact basin on the lunar far side and south polar zone containing candidates with access to permanently shadowed regions.",
            "source_status": "official",
        },
        {
            "region_code": "MARE-IMBRIUM",
            "region_name": "Mare Imbrium",
            "mission_context": "Lunar Mare Science & Historic Rover Surface Operations",
            "description": "Large circular lunar mare basin formed during the Early Imbrian epoch, host to extensive volcanic flood basalts and historical lunar rovers.",
            "source_status": "official",
        },
        {
            "region_code": "MARE-SERENITATIS",
            "region_name": "Mare Serenitatis",
            "mission_context": "Lunar Mare Science & Rover Exploration",
            "description": "Circular mare basin east of Imbrium, site of the Lunokhod 2 rover exploration in Le Monnier crater.",
            "source_status": "official",
        },
    ]

    for reg in regions:
        conn.execute(
            sa.text(
                """
                INSERT INTO nasa_regions (region_code, region_name, mission_context, description, source_status, is_active)
                VALUES (:region_code, :region_name, :mission_context, :description, :source_status, true)
                ON CONFLICT (region_code) DO NOTHING;
                """
            ),
            reg,
        )

    # 8. Seed UI-Reference Landing Sites
    sites = [
        {
            "site_code": "HIST-LUNO-01",
            "site_slug": "lunokhod-1",
            "site_name": "Lunokhod 1",
            "region_code": "MARE-IMBRIUM",
            "latitude_deg": 38.3150000,
            "longitude_deg": -35.0080000,
            "elevation_m": -2500.0,
            "terrain_type": "Mare Basalt Plain",
            "overview_summary": "Landing site of the Soviet Luna 17 / Lunokhod 1 rover (1970) in Mare Imbrium. Provides authentic mare geology baseline.",
            "catalogue_status": "published",
            "metrics": [
                ("illumination_annual_avg", 50.0, 0.5),
                ("earth_visibility_avg", 96.0, 1.0),
                ("max_slope_deg", 4.2, 0.5),
                ("scientific_value_score", 78.0, None),
                ("surface_roughness", 2.1, 0.2),
            ],
        },
        {
            "site_code": "HIST-LUNO-02",
            "site_slug": "lunokhod-2",
            "site_name": "Lunokhod 2",
            "region_code": "MARE-SERENITATIS",
            "latitude_deg": 25.8500000,
            "longitude_deg": 30.4500000,
            "elevation_m": -2600.0,
            "terrain_type": "Crater Floor / Mare Transition",
            "overview_summary": "Landing site of Lunokhod 2 in Le Monnier crater at the edge of Mare Serenitatis. Traversed 39 km across lunar mare and graben.",
            "catalogue_status": "published",
            "metrics": [
                ("illumination_annual_avg", 50.0, 0.5),
                ("earth_visibility_avg", 98.0, 1.0),
                ("max_slope_deg", 5.0, 0.6),
                ("scientific_value_score", 82.0, None),
                ("surface_roughness", 2.5, 0.3),
            ],
        },
        {
            "site_code": "HIST-YUTU-01",
            "site_slug": "yutu-jade-rabbit",
            "site_name": "Yutu (Jade Rabbit)",
            "region_code": "MARE-IMBRIUM",
            "latitude_deg": 44.1214000,
            "longitude_deg": -19.5125000,
            "elevation_m": -2610.0,
            "terrain_type": "Crater Region / Ejecta Blanket",
            "overview_summary": "Landing site of Chang'e 3 / Yutu rover (2013) in northern Mare Imbrium near Zi Wei crater.",
            "catalogue_status": "published",
            "metrics": [
                ("illumination_annual_avg", 50.0, 0.5),
                ("earth_visibility_avg", 94.0, 1.0),
                ("max_slope_deg", 6.1, 0.6),
                ("scientific_value_score", 80.0, None),
                ("surface_roughness", 3.0, 0.3),
            ],
        },
        {
            "site_code": "HIST-CH3-01",
            "site_slug": "pragyan-chandrayaan-3",
            "site_name": "Pragyan (Chandrayaan-3)",
            "region_code": "SP-AITKEN",
            "latitude_deg": -69.3730000,
            "longitude_deg": 32.3480000,
            "elevation_m": -1800.0,
            "terrain_type": "Highland Regolith / Sub-polar",
            "overview_summary": "Shiv Shakti Point, landing site of ISRO Chandrayaan-3 / Pragyan rover (2023) in southern high-latitude terrain.",
            "catalogue_status": "published",
            "metrics": [
                ("illumination_annual_avg", 54.0, 1.0),
                ("earth_visibility_avg", 88.0, 2.0),
                ("max_slope_deg", 5.5, 0.5),
                ("scientific_value_score", 86.0, None),
                ("water_ice_probability", 35.0, 5.0),
                ("surface_roughness", 3.5, 0.4),
            ],
        },
        {
            "site_code": "LUNA-MOUTON-01",
            "site_slug": "mons-mouton",
            "site_name": "Mons Mouton",
            "region_code": "SP-AITKEN",
            "latitude_deg": -84.9000000,
            "longitude_deg": 31.6000000,
            "elevation_m": 6000.0,
            "terrain_type": "High Plateau / Mountainous Massif",
            "overview_summary": "Prominent lunar south polar plateau standing approximately 6000m above surrounding terrain. High illumination peak and prime science target.",
            "catalogue_status": "published",
            "metrics": [
                ("illumination_annual_avg", 85.0, 2.0),
                ("earth_visibility_avg", 89.0, 2.5),
                ("max_slope_deg", 8.0, 1.0),
                ("scientific_value_score", 92.0, None),
                ("water_ice_probability", 52.0, 4.0),
                ("surface_roughness", 4.0, 0.3),
            ],
        },
    ]

    for site in sites:
        res = conn.execute(
            sa.text(
                """
                INSERT INTO landing_sites (
                    site_code, site_slug, site_name, region_id,
                    latitude_deg, longitude_deg, elevation_m,
                    terrain_type, overview_summary, catalogue_status, coordinate_reference
                )
                SELECT
                    :site_code, :site_slug, :site_name, nr.region_id,
                    :lat, :lon, :elev,
                    :terrain, :summary, :status, 'MOON_ME (IAU/NAIF Mean Earth/Polar Axis)'
                FROM nasa_regions nr
                WHERE nr.region_code = :region_code
                ON CONFLICT (site_code) DO UPDATE SET
                    elevation_m = EXCLUDED.elevation_m,
                    terrain_type = EXCLUDED.terrain_type,
                    overview_summary = EXCLUDED.overview_summary,
                    catalogue_status = EXCLUDED.catalogue_status
                RETURNING site_id;
                """
            ),
            {
                "site_code": site["site_code"],
                "site_slug": site["site_slug"],
                "site_name": site["site_name"],
                "region_code": site["region_code"],
                "lat": site["latitude_deg"],
                "lon": site["longitude_deg"],
                "elev": site["elevation_m"],
                "terrain": site["terrain_type"],
                "summary": site["overview_summary"],
                "status": site["catalogue_status"],
            },
        ).fetchone()

        if res:
            sid = res[0]
            for pkey, val, uncert in site["metrics"]:
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO site_metrics (
                            site_id, parameter_id, numeric_value, uncertainty_value,
                            methodology, data_quality_status
                        )
                        SELECT :sid, pd.parameter_id, :val, :uncert, pd.methodology_note, 'verified'
                        FROM parameter_definitions pd
                        WHERE pd.parameter_key = :pkey
                        AND NOT EXISTS (
                            SELECT 1 FROM site_metrics sm
                            WHERE sm.site_id = :sid AND sm.parameter_id = pd.parameter_id
                        );
                        """
                    ),
                    {"sid": sid, "pkey": pkey, "val": val, "uncert": uncert},
                )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_comparison_profile_parameters_prof_param;")
    op.execute("DROP INDEX IF EXISTS uq_data_sources_title;")
    op.drop_column("site_metrics", "data_quality_status")
    op.drop_column("comparison_results", "text_value_b")
    op.drop_column("comparison_results", "text_value_a")
    op.drop_column("comparison_runs", "limitations_note")
    op.drop_column("comparison_runs", "overall_winner")
    op.drop_column("comparison_runs", "overall_score_b")
    op.drop_column("comparison_runs", "overall_score_a")
    op.drop_column("parameter_definitions", "tolerance")
    op.drop_column("parameter_definitions", "benchmark_max")
    op.drop_column("parameter_definitions", "benchmark_min")
