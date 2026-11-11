"""Service for landing site name, alias, and research text search."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.catalogue import LandingSite, SiteContent
from app.schemas.search import SearchResultOut


def search_sites(db: Session, query_str: str, limit: int = 20) -> list[SearchResultOut]:
    """Search landing sites by name, alternate names, and long-form research text."""
    clean_query = query_str.strip()
    if not clean_query:
        return []

    results: list[SearchResultOut] = []
    seen_site_ids = set()

    # 1. Direct and prefix name matching on published landing_sites only
    name_stmt = (
        select(LandingSite)
        .options(joinedload(LandingSite.region))
        .where(
            LandingSite.catalogue_status == "published",
            (
                LandingSite.site_name.ilike(f"%{clean_query}%")
                | LandingSite.site_code.ilike(f"%{clean_query}%")
                | LandingSite.site_slug.ilike(f"%{clean_query}%")
            ),
        )
        .limit(limit)
    )
    name_matches = db.scalars(name_stmt).all()
    for s in name_matches:
        seen_site_ids.add(s.site_id)
        results.append(
            SearchResultOut(
                site_id=s.site_id,
                site_slug=s.site_slug,
                site_code=s.site_code,
                site_name=s.site_name,
                match_field="name",
                match_snippet=s.overview_summary[:160] if s.overview_summary else None,
                region_name=s.region.region_name if s.region else None,
                latitude_deg=float(s.latitude_deg),
                longitude_deg=float(s.longitude_deg),
            )
        )

    # 2. Full-text search on long-form research content using tsvector (published sites only)
    if len(results) < limit:
        remaining = limit - len(results)
        fts_stmt = (
            select(
                SiteContent.site_id,
                func.ts_headline(
                    "english",
                    SiteContent.body,
                    func.plainto_tsquery("english", clean_query),
                    "StartSel=<mark>, StopSel=</mark>, MaxWords=30, MinWords=15",
                ).label("snippet"),
            )
            .join(LandingSite, SiteContent.site_id == LandingSite.site_id)
            .where(
                LandingSite.catalogue_status == "published",
                func.to_tsvector("english", SiteContent.body).op("@@")(
                    func.plainto_tsquery("english", clean_query)
                ),
            )
            .limit(remaining * 2)
        )
        content_matches = db.execute(fts_stmt).all()

        candidate_matches: list[tuple[int, str]] = []
        for site_id, snippet in content_matches:
            if site_id in seen_site_ids:
                continue
            seen_site_ids.add(site_id)
            candidate_matches.append((site_id, snippet))
            if len(results) + len(candidate_matches) >= limit:
                break

        if candidate_matches:
            candidate_ids = [sid for sid, _ in candidate_matches]
            sites_stmt = (
                select(LandingSite)
                .options(joinedload(LandingSite.region))
                .where(LandingSite.site_id.in_(candidate_ids))
            )
            sites_by_id = {s.site_id: s for s in db.scalars(sites_stmt).all()}
            for site_id, snippet in candidate_matches:
                site = sites_by_id.get(site_id)
                if site:
                    results.append(
                        SearchResultOut(
                            site_id=site.site_id,
                            site_slug=site.site_slug,
                            site_code=site.site_code,
                            site_name=site.site_name,
                            match_field="content",
                            match_snippet=snippet,
                            region_name=site.region.region_name if site.region else None,
                            latitude_deg=float(site.latitude_deg),
                            longitude_deg=float(site.longitude_deg),
                        )
                    )

    return results
