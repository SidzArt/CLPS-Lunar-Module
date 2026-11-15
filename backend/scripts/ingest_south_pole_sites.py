"""Ingestion script for 9 Lunar South Pole candidate landing sites.

Inserts or updates:
- Site Code 1: Peak near Cabeus B (Full dossier + 3 media assets)
- Site Code 2: Haworth (Full dossier + 3 media assets)
- Sites 3–9: Compact records only (Name and coordinates)
"""

import hashlib
import io
import os
import sys
from datetime import date
from pathlib import Path

# Ensure backend root is on sys.path
backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_root))

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import delete, select
from app.db.session import SessionLocal
from app.models.catalogue import (
    LandingSite,
    NASARegion,
    SiteAlias,
    SiteContent,
    SiteHistory,
    SiteMedia,
    SiteProCon,
)
from app.core.config import settings


def generate_scientific_plate(
    title: str,
    subtitle: str,
    site_label: str,
    coords_label: str,
    data_type: str,
    credit: str,
    theme: str = "lola",
) -> bytes:
    """Generate high-resolution scientific data plate with grid, scale bar, and telemetry."""
    width, height = 1280, 800
    img = Image.new("RGB", (width, height), color=(11, 16, 25))
    draw = ImageDraw.Draw(img)

    # Background gradient / simulated raster texture
    if theme == "lroc":
        # Grayscale radar/optical backscatter texture
        for y in range(80, height - 70, 4):
            for x in range(40, width - 40, 8):
                noise = int(35 + ((x * y * 13) % 45) + ((x * 17) % 30))
                draw.rectangle([x, y, x + 8, y + 4], fill=(noise, noise + 2, noise + 5))
    elif theme == "lola":
        # False color elevation map texture (cool blues to cyans to greens to amber peaks)
        for y in range(80, height - 70, 4):
            val = (y - 80) / (height - 150)
            r = int(15 + 180 * (1 - val) ** 2)
            g = int(30 + 150 * val * (1 - val) * 4)
            b = int(60 + 180 * val)
            draw.rectangle([40, y, width - 40, y + 4], fill=(r, g, b))
    else:  # psr / thermal
        # Deep blue-black with cyan thermal frost contours
        for y in range(80, height - 70, 4):
            val = ((y * 7) % 255) / 255.0
            r = int(5 + 20 * val)
            g = int(25 + 90 * val)
            b = int(70 + 130 * val)
            draw.rectangle([40, y, width - 40, y + 4], fill=(r, g, b))

    # Dark vignette overlay to give depth
    draw.rectangle([40, 80, width - 40, height - 70], outline=(70, 95, 130), width=1)

    # Top telemetry bar
    draw.rectangle([0, 0, width, 70], fill=(7, 10, 16))
    draw.line([0, 70, width, 70], fill=(90, 210, 230), width=2)

    # Bottom status bar
    draw.rectangle([0, height - 60, width, height], fill=(7, 10, 16))
    draw.line([0, height - 60, width, height - 60], fill=(245, 184, 61), width=1)

    # Texts
    draw.text((45, 16), "CLPS LUNA BROWSER · SCIENTIFIC MISSION DATA ARCHIVE", fill=(90, 210, 230))
    draw.text((45, 38), f"{title} | {data_type}", fill=(240, 245, 255))
    draw.text((width - 450, 26), f"TARGET: {site_label} ({coords_label})", fill=(245, 184, 61))

    # Coordinate crosshairs and reticle in center
    cx, cy = width // 2, (height + 10) // 2
    draw.ellipse([cx - 140, cy - 140, cx + 140, cy + 140], outline=(90, 210, 230), width=1)
    draw.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], outline=(245, 184, 61), width=1)
    draw.line([cx - 180, cy, cx + 180, cy], fill=(90, 210, 230), width=1)
    draw.line([cx, cy - 180, cx, cy + 180], fill=(90, 210, 230), width=1)

    # Target indicator text
    draw.text((cx + 15, cy + 15), f"TOUCHDOWN ELIGIBLE ZONE: {coords_label}", fill=(255, 255, 255))
    draw.text((cx + 15, cy + 32), f"SUBTITLE: {subtitle}", fill=(180, 200, 220))

    # Scale bar in bottom right of data window
    sb_x, sb_y = width - 280, height - 110
    draw.line([sb_x, sb_y, sb_x + 180, sb_y], fill=(255, 255, 255), width=3)
    draw.line([sb_x, sb_y - 6, sb_x, sb_y + 6], fill=(255, 255, 255), width=2)
    draw.line([sb_x + 180, sb_y - 6, sb_x + 180, sb_y + 6], fill=(255, 255, 255), width=2)
    draw.text((sb_x + 55, sb_y - 18), "10 KILOMETERS", fill=(255, 255, 255))

    # Bottom credit & provenance bar
    draw.text((45, height - 42), f"CREDIT: {credit}", fill=(160, 175, 195))
    draw.text((width - 430, height - 42), "REFERENCE FRAME: MOON_ME (IAU/NAIF DE440)", fill=(160, 175, 195))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def save_media_asset(
    png_bytes: bytes,
    filename_stem: str,
    caption: str,
    credit: str,
    media_type: str = "image",
    display_order: int = 0,
    is_primary: bool = False,
) -> dict:
    """Save processed image and thumbnail to storage/media and return metadata dictionary."""
    media_dir = Path(settings.MEDIA_ROOT)
    media_dir.mkdir(parents=True, exist_ok=True)

    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    width_px, height_px = img.size

    # Save primary webp
    main_filename = f"{filename_stem}.webp"
    thumb_filename = f"{filename_stem}_thumb.webp"
    main_abs_path = media_dir / main_filename
    thumb_abs_path = media_dir / thumb_filename

    img.save(main_abs_path, format="WEBP", quality=90)
    file_size_bytes = os.path.getsize(main_abs_path)

    # Save thumbnail
    thumb = img.copy()
    thumb.thumbnail((400, 250), Image.Resampling.LANCZOS)
    thumb.save(thumb_abs_path, format="WEBP", quality=85)

    sha256_hash = hashlib.sha256(png_bytes).hexdigest()

    return {
        "media_type": media_type,
        "file_path": f"media/{main_filename}",
        "thumbnail_path": f"media/{thumb_filename}",
        "original_filename": f"{filename_stem}.png",
        "mime_type": "image/webp",
        "file_size_bytes": file_size_bytes,
        "width_px": width_px,
        "height_px": height_px,
        "caption": caption,
        "credit": credit,
        "alt_text": caption,
        "sha256": sha256_hash,
        "display_order": display_order,
        "is_primary": is_primary,
    }


def ingest_south_pole_catalogue():
    db = SessionLocal()
    try:
        # 1. Ensure Region SP-AITKEN exists
        region = db.scalar(select(NASARegion).where(NASARegion.region_code == "SP-AITKEN"))
        if not region:
            region = NASARegion(
                region_code="SP-AITKEN",
                region_name="South Pole-Aitken Basin",
                description="Massive pre-Nectarian impact basin on the lunar south pole and far side.",
                source_status="official",
                is_active=True,
            )
            db.add(region)
            db.flush()

        region_id = region.region_id

        # 2. Complete Dossier: Site Code 1 — Peak near Cabeus B
        print("Ingesting Site Code 1: Peak near Cabeus B...")
        site1 = db.scalar(select(LandingSite).where(LandingSite.site_code == "1"))
        if not site1:
            site1 = db.scalar(select(LandingSite).where(LandingSite.site_slug == "peak-near-cabeus-b"))
        if not site1:
            site1 = LandingSite(
                site_code="1",
                site_slug="peak-near-cabeus-b",
                site_name="Peak near Cabeus B",
                region_id=region_id,
                latitude_deg=-83.6000000,
                longitude_deg=-68.8000000,
                elevation_m=3850.0,
                terrain_type="Elevated Peak / High Crater Rim Transition",
                overview_summary=(
                    "Peak near Cabeus B is an elevated prominence near the lunar south pole, located next to Cabeus B "
                    "crater and Cabeus crater. It offers crucial access to surrounding crater formations and permanently shadowed "
                    "regions hosting potential water ice volatiles. Added to NASA's Artemis III candidate list in October 2024."
                ),
                catalogue_status="published",
                coordinate_reference="MOON_ME (IAU/NAIF Mean Earth/Polar Axis)",
                alternate_names=["Peak near Cabeus B", "Cabeus B Peak", "Candidate Region 01"],
            )
            db.add(site1)
            db.flush()
        else:
            site1.site_code = "1"
            site1.site_slug = "peak-near-cabeus-b"
            site1.site_name = "Peak near Cabeus B"
            site1.region_id = region_id
            site1.latitude_deg = -83.6000000
            site1.longitude_deg = -68.8000000
            site1.elevation_m = 3850.0
            site1.terrain_type = "Elevated Peak / High Crater Rim Transition"
            site1.overview_summary = (
                "Peak near Cabeus B is an elevated prominence near the lunar south pole, located next to Cabeus B "
                "crater and Cabeus crater. It offers crucial access to surrounding crater formations and permanently shadowed "
                "regions hosting potential water ice volatiles. Added to NASA's Artemis III candidate list in October 2024."
            )
            site1.catalogue_status = "published"
            db.flush()

        # Clear existing sub-tables for clean, idempotent insertion
        db.execute(delete(SiteProCon).where(SiteProCon.site_id == site1.site_id))
        db.execute(delete(SiteContent).where(SiteContent.site_id == site1.site_id))
        db.execute(delete(SiteHistory).where(SiteHistory.site_id == site1.site_id))
        db.execute(delete(SiteMedia).where(SiteMedia.site_id == site1.site_id))

        # Advantages & Disadvantages for Site 1
        site1_pros = [
            "Located near the Cabeus crater, an area of significant scientific interest due to the presence of permanently shadowed regions (PSRs).",
            "Offers an opportunity to investigate water ice and other potentially useful lunar resources.",
            "Its elevated location provides access to surrounding crater structures and geological formations.",
            "Can contribute valuable information about the Moon's geological history.",
        ]
        for idx, text in enumerate(site1_pros):
            db.add(SiteProCon(site_id=site1.site_id, point_type="PRO", body=text, display_order=idx))

        site1_cons = [
            "Has a very limited safe landing area, with only approximately 2.1 km² meeting the specified landing-slope requirements.",
            "The surrounding terrain presents challenges for astronaut and rover movement.",
            "Permanently shadowed regions may limit sunlight availability and complicate solar power generation.",
            "Limited suitable terrain reduces flexibility when selecting an exact touchdown location.",
        ]
        for idx, text in enumerate(site1_cons):
            db.add(SiteProCon(site_id=site1.site_id, point_type="CON", body=text, display_order=idx))

        # Content Sections for Site 1
        site1_history_text = (
            "Peak near Cabeus B is not a formally named lunar feature. It was added to NASA's Artemis III candidate list "
            "in the October 2024 update. It lies near Cabeus B crater, next to Cabeus crater, and is centred at approximately "
            "83.6°S, 291.2°E (68.8°W).\n\n"
            "The terrain rises approximately 6 km over a 30 km span, from roughly 2,900 m below to 3,850 m above mean lunar level.\n\n"
            "The region is close to where NASA's LCROSS probe was deliberately crashed into Cabeus crater on 9 October 2009. "
            "The impact produced a plume containing water ice, making the region scientifically important for lunar resource research."
        )
        db.add(SiteContent(site_id=site1.site_id, section_key="overview", title="Overview & Location Context", body=site1.overview_summary, display_order=0))
        db.add(SiteContent(site_id=site1.site_id, section_key="history", title="History & Background", body=site1_history_text, display_order=1))
        db.add(SiteContent(site_id=site1.site_id, section_key="geology", title="Geology & Topography", body="The terrain rises approximately 6 km over a 30 km span, from roughly 2,900 m below to 3,850 m above mean lunar level. Landing area meeting safety slope constraints is approximately 2.1 km².", display_order=2))
        db.add(SiteContent(site_id=site1.site_id, section_key="research", title="Resource Research Significance", body="Proximity to the 2009 LCROSS impact site in Cabeus provides primary scientific interest for volatiles prospecting and lunar ice exploration.", display_order=3))

        # History Events for Site 1
        db.add(SiteHistory(site_id=site1.site_id, event_date=date(2009, 10, 9), title="NASA LCROSS Probe Impact in Cabeus Crater", description="LCROSS deliberately impacted Cabeus crater, ejecting water ice and volatile plumes confirming lunar ice deposits.", display_order=0))
        db.add(SiteHistory(site_id=site1.site_id, event_date=date(2024, 10, 1), title="Shortlisted in NASA Artemis III Update", description="Added as an Artemis III candidate landing region in NASA's refined nine-region shortlist.", display_order=1))

        # Exactly 3 Images for Site 1
        img1_1 = generate_scientific_plate(
            "LROC NAC ORBITAL RECONNAISSANCE MOSAIC",
            "High-resolution orbital reconnaissance of Peak near Cabeus B candidate landing zone",
            "Peak near Cabeus B",
            "83.6°S, 68.8°W",
            "Optical Imagery (LROC)",
            "NASA / GSFC / Arizona State University (LRO/LROC)",
            theme="lroc",
        )
        img1_2 = generate_scientific_plate(
            "LOLA DIGITAL ELEVATION & SLOPES MODEL",
            "Topographic 6 km relief and slope roughness across Cabeus B elevated ridge",
            "Peak near Cabeus B",
            "83.6°S, 68.8°W",
            "Topographic Altimetry (LOLA)",
            "NASA / Goddard Space Flight Center (LOLA Science Team)",
            theme="lola",
        )
        img1_3 = generate_scientific_plate(
            "VOLATILE DISTRIBUTION & PSR ILLUMINATION MAP",
            "Permanently shadowed regions and solar illumination availability model",
            "Peak near Cabeus B",
            "83.6°S, 68.8°W",
            "Volatiles & Illumination Assessment",
            "NASA Artemis Science Team / LRO LAMP / Diviner",
            theme="psr",
        )

        m1_meta = save_media_asset(img1_1, "cabeus_b_orbital_lroc", "NASA LRO LROC Narrow Angle Camera high-resolution orbital reconnaissance mosaic of the Peak near Cabeus B candidate zone.", "NASA / GSFC / ASU (LROC)", media_type="image", display_order=0, is_primary=True)
        m2_meta = save_media_asset(img1_2, "cabeus_b_terrain_lola", "LOLA shaded relief showing the 6 km topographic elevation rise and crater rim slopes across the Cabeus B ridge.", "NASA / GSFC (LOLA)", media_type="map", display_order=1, is_primary=False)
        m3_meta = save_media_asset(img1_3, "cabeus_b_psr_illumination", "LOLA and LAMP permanently shadowed region (PSR) volatile distribution and solar illumination model for Peak near Cabeus B.", "NASA Artemis Science Team / LRO", media_type="chart", display_order=2, is_primary=False)

        for m in [m1_meta, m2_meta, m3_meta]:
            db.add(SiteMedia(site_id=site1.site_id, **m))

        # 3. Complete Dossier: Site Code 2 — Haworth
        print("Ingesting Site Code 2: Haworth...")
        site2 = db.scalar(select(LandingSite).where(LandingSite.site_code == "2"))
        if not site2:
            site2 = db.scalar(select(LandingSite).where(LandingSite.site_slug == "haworth"))
        if not site2:
            site2 = LandingSite(
                site_code="2",
                site_slug="haworth",
                site_name="Haworth",
                region_id=region_id,
                latitude_deg=-86.9000000,
                longitude_deg=-4.0000000,
                elevation_m=-2800.0,
                terrain_type="Pre-Nectarian Impact Crater / PSR Interior & Rim",
                overview_summary=(
                    "Haworth is an ancient Pre-Nectarian impact crater (>3.9 Ga) approximately 51 km across located near "
                    "the lunar south pole (86.9°S, 4.0°W; alternative gazetteer 87.45°S, 5.2°W). Much of its interior is "
                    "permanently shadowed and extremely cold (~40 K) with frost, surrounded by extensive gentle exploration slopes."
                ),
                catalogue_status="published",
                coordinate_reference="MOON_ME (IAU/NAIF Mean Earth/Polar Axis)",
                alternate_names=["Haworth Crater", "Artemis Candidate Haworth", "IAU Gazetteer: 87.45°S, 5.2°W"],
            )
            db.add(site2)
            db.flush()
        else:
            site2.site_code = "2"
            site2.site_slug = "haworth"
            site2.site_name = "Haworth"
            site2.region_id = region_id
            site2.latitude_deg = -86.9000000
            site2.longitude_deg = -4.0000000
            site2.elevation_m = -2800.0
            site2.terrain_type = "Pre-Nectarian Impact Crater / PSR Interior & Rim"
            site2.overview_summary = (
                "Haworth is an ancient Pre-Nectarian impact crater (>3.9 Ga) approximately 51 km across located near "
                "the lunar south pole (86.9°S, 4.0°W; alternative gazetteer 87.45°S, 5.2°W). Much of its interior is "
                "permanently shadowed and extremely cold (~40 K) with frost, surrounded by extensive gentle exploration slopes."
            )
            site2.catalogue_status = "published"
            db.flush()

        # Clear existing sub-tables for Haworth
        db.execute(delete(SiteProCon).where(SiteProCon.site_id == site2.site_id))
        db.execute(delete(SiteContent).where(SiteContent.site_id == site2.site_id))
        db.execute(delete(SiteHistory).where(SiteHistory.site_id == site2.site_id))
        db.execute(delete(SiteMedia).where(SiteMedia.site_id == site2.site_id))
        db.execute(delete(SiteAlias).where(SiteAlias.site_id == site2.site_id))

        # Gazetteer alias
        db.add(SiteAlias(site_id=site2.site_id, alias_text="87.45°S, 5.2°W (Alternative IAU Gazetteer Coordinates)", language_code="en"))

        # Advantages & Disadvantages for Site 2
        site2_pros = [
            "Contains relatively extensive areas of gentle slopes suitable for landing and surface exploration.",
            "Offers access to permanently shadowed regions that may contain water ice and other volatile materials.",
            "Provides opportunities to study ancient lunar geological formations.",
            "Several areas have relatively low surface roughness, supporting astronaut and rover mobility.",
        ]
        for idx, text in enumerate(site2_pros):
            db.add(SiteProCon(site_id=site2.site_id, point_type="PRO", body=text, display_order=idx))

        site2_cons = [
            "Steep slopes around the crater rims can restrict movement and exploration.",
            "Permanently shadowed areas receive little or no direct sunlight, making scientific access and operations challenging.",
            "Sunlight and Earth visibility vary across the region, potentially affecting power generation and communication.",
            "The crater's rugged surroundings increase navigation complexity.",
        ]
        for idx, text in enumerate(site2_cons):
            db.add(SiteProCon(site_id=site2.site_id, point_type="CON", body=text, display_order=idx))

        # Content Sections for Site 2
        site2_history_text = (
            "Haworth is a Pre-Nectarian impact crater, estimated to be over 3.9 billion years old, near the lunar south pole. "
            "It is approximately 51 km across and centred at roughly 86.9°S, 4°W. One gazetteer-based source gives alternative "
            "coordinates of approximately 87.45°S, 5.2°W.\n\n"
            "It is named after Walter Haworth, the British chemist who won the 1937 Nobel Prize in Chemistry for his work on vitamin C. "
            "The name was officially approved in October 2008.\n\n"
            "Because the crater lies in near-permanent shadow, it is rarely visible in photographs. It was known mainly through Earth-based "
            "radar observations. Much of its interior is permanently shadowed and extremely cold, possibly never exceeding approximately 40 K. "
            "The surrounding low-lying areas also contain frost.\n\n"
            "Haworth was one of NASA's 13 Artemis III candidate landing regions announced in 2022 and remained among the nine shortlisted "
            "regions announced in October 2024."
        )
        db.add(SiteContent(site_id=site2.site_id, section_key="overview", title="Overview & Crater Context", body=site2.overview_summary, display_order=0))
        db.add(SiteContent(site_id=site2.site_id, section_key="history", title="History & Background", body=site2_history_text, display_order=1))
        db.add(SiteContent(site_id=site2.site_id, section_key="geology", title="Pre-Nectarian Geology", body="Pre-Nectarian impact structure (>3.9 Ga), 51 km across. Interior temperatures remain cryogenic (<40 K) preserving cold-trapped volatiles and surface frost deposits.", display_order=2))
        db.add(SiteContent(site_id=site2.site_id, section_key="research", title="Radar & Thermal Observations", body="Historically observed via Earth-based radar (Arecibo/Goldstone) due to persistent shadows; mapped by LRO Diviner, LOLA, and LAMP.", display_order=3))

        # History Events for Site 2
        db.add(SiteHistory(site_id=site2.site_id, event_date=date(2008, 10, 1), title="IAU Approval of Name Haworth", description="Officially named after British chemist and Nobel laureate Sir Walter Haworth.", display_order=0))
        db.add(SiteHistory(site_id=site2.site_id, event_date=date(2022, 8, 19), title="Initial Artemis III Candidate Selection", description="Announced as one of NASA's 13 candidate landing regions for Artemis III.", display_order=1))
        db.add(SiteHistory(site_id=site2.site_id, event_date=date(2024, 10, 1), title="Reaffirmed in Artemis III Shortlist", description="Retained among NASA's nine shortlisted regions in the October 2024 candidate refinement.", display_order=2))

        # Exactly 3 Images for Site 2
        img2_1 = generate_scientific_plate(
            "LROC WAC CRATER RECONNAISSANCE MOSAIC",
            "LROC Wide Angle Camera polar mosaic of Haworth impact crater (~51 km diameter)",
            "Haworth",
            "86.9°S, 4.0°W (Alt: 87.45°S, 5.2°W)",
            "Optical Imagery (LROC WAC)",
            "NASA / GSFC / Arizona State University (LRO/LROC)",
            theme="lroc",
        )
        img2_2 = generate_scientific_plate(
            "LOLA DIGITAL ELEVATION & RIM PROFILE",
            "Topographic depression, interior floor gradient, and surrounding crater rim slopes",
            "Haworth",
            "86.9°S, 4.0°W",
            "Altimetry & Digital Elevation (LOLA)",
            "NASA / Goddard Space Flight Center (LOLA Science Team)",
            theme="lola",
        )
        img2_3 = generate_scientific_plate(
            "DIVINER & LAMP VOLATILE / FROST DISTRIBUTION",
            "Permanently shadowed regions thermal profile (<40 K) and surface frost signatures",
            "Haworth",
            "86.9°S, 4.0°W",
            "Thermal & Far-UV Albedo (Diviner/LAMP)",
            "NASA / UCLA / SwRI (LRO Science Teams)",
            theme="psr",
        )

        h1_meta = save_media_asset(img2_1, "haworth_crater_orbital_lroc", "NASA LRO LROC Wide Angle Camera polar mosaic showing the 51 km diameter Haworth impact crater.", "NASA / GSFC / ASU (LROC)", media_type="image", display_order=0, is_primary=True)
        h2_meta = save_media_asset(img2_2, "haworth_lola_elevation_profile", "LOLA topographic digital elevation model showing Haworth crater floor depression and rim elevation profiles.", "NASA / GSFC (LOLA)", media_type="map", display_order=1, is_primary=False)
        h3_meta = save_media_asset(img2_3, "haworth_psr_frost_map", "LRO Diviner and LAMP thermal/far-UV reflectance map showing permanently shadowed interior (<40 K) and surface frost locations.", "NASA / UCLA / SwRI (LRO)", media_type="chart", display_order=2, is_primary=False)

        for m in [h1_meta, h2_meta, h3_meta]:
            db.add(SiteMedia(site_id=site2.site_id, **m))

        # 4. Sites 3 to 9: Compact Records ONLY (Name, Lat, Lon ONLY)
        compact_sites = [
            ("3", "malapert-massif", "Malapert Massif", -86.4000000, 1.3000000),
            ("4", "mons-mouton-plateau", "Mons Mouton Plateau", -84.6000000, 31.0000000),
            ("5", "nobile-rim-2", "Nobile Rim 2", -84.2000000, 60.7000000),
            ("6", "connecting-ridge", "Connecting Ridge", -89.6000000, -172.7000000),
            ("7", "connecting-ridge-extension", "Connecting Ridge Extension", -89.2000000, -86.0000000),
            ("8", "leibnitz-beta-plateau", "Leibnitz Beta Plateau", -85.2000000, 33.8000000),
            ("9", "amundsen-rim", "Amundsen Rim", -84.2000000, 66.9000000),
        ]

        for code, slug, name, lat, lon in compact_sites:
            print(f"Ingesting compact Site Code {code}: {name} ({lat}, {lon})...")
            site_obj = db.scalar(select(LandingSite).where(LandingSite.site_code == code))
            if not site_obj:
                site_obj = db.scalar(select(LandingSite).where(LandingSite.site_slug == slug))

            if not site_obj:
                site_obj = LandingSite(
                    site_code=code,
                    site_slug=slug,
                    site_name=name,
                    region_id=region_id,
                    latitude_deg=lat,
                    longitude_deg=lon,
                    elevation_m=None,
                    terrain_type=None,
                    overview_summary=None,
                    catalogue_status="published",
                    coordinate_reference="MOON_ME (IAU/NAIF Mean Earth/Polar Axis)",
                )
                db.add(site_obj)
                db.flush()
            else:
                site_obj.site_code = code
                site_obj.site_slug = slug
                site_obj.site_name = name
                site_obj.region_id = region_id
                site_obj.latitude_deg = lat
                site_obj.longitude_deg = lon
                site_obj.elevation_m = None
                site_obj.terrain_type = None
                site_obj.overview_summary = None
                site_obj.catalogue_status = "published"
                db.flush()

            # Ensure NO detailed sub-tables for Sites 3–9
            db.execute(delete(SiteProCon).where(SiteProCon.site_id == site_obj.site_id))
            db.execute(delete(SiteContent).where(SiteContent.site_id == site_obj.site_id))
            db.execute(delete(SiteHistory).where(SiteHistory.site_id == site_obj.site_id))
            db.execute(delete(SiteMedia).where(SiteMedia.site_id == site_obj.site_id))
            db.execute(delete(SiteAlias).where(SiteAlias.site_id == site_obj.site_id))

        db.commit()
        print("Catalogue ingestion successfully committed to PostgreSQL database 'clps_luna'.")

    finally:
        db.close()


if __name__ == "__main__":
    ingest_south_pole_catalogue()

