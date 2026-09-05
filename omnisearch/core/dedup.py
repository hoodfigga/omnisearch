"""
Canonical identity resolution, URL normalization, and metadata deduplication engine.
"""

from __future__ import annotations
import re
from urllib.parse import urlparse, urlunparse
from typing import Dict, List, Optional, Tuple
from omnisearch.models.video import ItemRecord, MatchProvenance, ItemType


# Tracking parameters to strip from URLs
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "ref",
    "source",
    "feature",
    "si",
    "embed",
    "from",
}

YOUTUBE_ID_RE = re.compile(r"(?:v=|\/embed\/|\/shorts\/|\/v\/|^https?:\/\/youtu\.be\/)([a-zA-Z0-9_-]{11})")
VIMEO_ID_RE = re.compile(r"(?:vimeo\.com\/(?:video\/)?|player\.vimeo\.com\/video\/)([0-9]{5,15})")
DAILYMOTION_ID_RE = re.compile(r"(?:dailymotion\.com\/(?:video|embed\/video)\/|dai\.ly\/)([a-zA-Z0-9]+)")
ARCHIVE_ID_RE = re.compile(r"archive\.org\/(?:details|embed|download)\/([a-zA-Z0-9_.-]+)")

MEDIAFIRE_RE = re.compile(r"(?:^|\.)mediafire\.com\/(?:file\/|view\/|\?)?([a-zA-Z0-9]+)", re.I)
MEGA_RE = re.compile(r"(?:^|\.)mega\.(?:nz|io)\/#?(?:file|folder)\/([a-zA-Z0-9_-]+)", re.I)
RAPIDGATOR_RE = re.compile(r"(?:^|\.)rapidgator\.net\/file\/([a-zA-Z0-9]+)", re.I)
ONEFICHIER_RE = re.compile(r"(?:^|\.)1fichier\.com\/?\??([a-zA-Z0-9]+)", re.I)
TURBOBIT_RE = re.compile(r"(?:^|\.)turbobit\.net\/([a-zA-Z0-9]+)", re.I)
NITROFLARE_RE = re.compile(r"(?:^|\.)nitroflare\.com\/view\/([a-zA-Z0-9]+)", re.I)
DDOWNLOAD_RE = re.compile(r"(?:^|\.)ddownload\.com\/([a-zA-Z0-9]+)", re.I)
KATFILE_RE = re.compile(r"(?:^|\.)katfile\.com\/([a-zA-Z0-9]+)", re.I)
PIXELDRAIN_RE = re.compile(r"(?:^|\.)pixeldrain\.com\/(?:u|api\/file)\/([a-zA-Z0-9_-]+)", re.I)
GOFILE_RE = re.compile(r"(?:^|\.)gofile\.io\/d\/([a-zA-Z0-9_-]+)", re.I)
KRAKENFILES_RE = re.compile(r"(?:^|\.)krakenfiles\.com\/view\/([a-zA-Z0-9_-]+)", re.I)
CATBOX_RE = re.compile(r"(?:^|\.)(?:files\.)?catbox\.moe\/([a-zA-Z0-9_.-]+)", re.I)
TMPFILES_RE = re.compile(r"(?:^|\.)tmpfiles\.org\/(?:dl\/)?([0-9]+)", re.I)
CYBERFILE_RE = re.compile(r"(?:^|\.)(?:cyberfile|cyberdrop|saint2)\.[a-z]+\/(?:f|d|file)\/([a-zA-Z0-9_-]+)", re.I)
GDRIVE_RE = re.compile(r"(?:^|\.)drive\.google\.com\/(?:file\/d\/|open\?id=)([a-zA-Z0-9_-]+)", re.I)
DROPBOX_RE = re.compile(r"(?:^|\.)(?:www\.)?dropbox\.com\/(?:s|scl\/fi)\/([a-zA-Z0-9_-]+)", re.I)
GITHUB_RE = re.compile(r"(?:^|\.)(?:www\.)?github\.com\/([^/]+\/[^/]+)\/(?:releases|archive)", re.I)
WORKUPLOAD_RE = re.compile(r"(?:^|\.)workupload\.com\/file\/([a-zA-Z0-9_-]+)", re.I)

BUNKR_RE = re.compile(r"(?:^|\.)(?:bunkr|bunkrr|bunker)\.[a-z0-9.]+", re.I)
BUNKR_FILE_ID_RE = re.compile(r"/(?:f|v|d|file)/([a-zA-Z0-9_-]+)", re.I)
BUNKR_ALBUM_ID_RE = re.compile(r"/a/([a-zA-Z0-9_-]+)", re.I)


def normalize_url(raw_url: str) -> str:
    """Cleans and standardizes URL by removing tracking query parameters and trailing slashes."""
    if not raw_url:
        return ""
    try:
        parsed = urlparse(raw_url.strip())
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        if netloc.startswith("m."):
            netloc = netloc[2:]

        # Filter query params while preserving their raw formatting:
        # valueless params (1fichier.com/?abc123 — the bare param IS the file
        # id) and original encoding must survive canonicalization.
        raw_params = [p for p in parsed.query.split("&") if p]
        kept = [p for p in raw_params if p.split("=")[0].lower() not in TRACKING_PARAMS]
        clean_query = "&".join(kept)

        # Standardize path
        path = parsed.path.rstrip("/") if parsed.path != "/" else "/"

        clean_url = urlunparse((
            parsed.scheme.lower() or "https",
            netloc,
            path,
            "",
            clean_query,
            "",  # Strip fragment
        ))
        return clean_url
    except Exception:
        return raw_url.strip()


def resolve_platform_and_id(url: str) -> Tuple[str, Optional[str], str]:
    """
    Analyzes a URL to resolve the canonical platform, platform-native ID, and canonical page URL.
    Returns: (platform_name, platform_id, canonical_url)
    """
    norm_url = normalize_url(url)
    parsed = urlparse(norm_url)
    netloc = parsed.netloc.lower()

    # Domain-scoped subject: leading dot guarantees host-boundary anchoring,
    # so 'debunkr.com' can never match the Bunkr patterns while
    # 'www.mediafire.com' and 'sub.bunkr.is' still do.
    host_subject = f".{netloc}{parsed.path}"
    if parsed.query:
        host_subject += f"?{parsed.query}"

    # MediaFire
    mf_match = MEDIAFIRE_RE.search(host_subject)
    if mf_match:
        return "MediaFire", mf_match.group(1), norm_url

    # MEGA
    mega_match = MEGA_RE.search(host_subject)
    if mega_match:
        return "MEGA", mega_match.group(1), norm_url

    # Rapidgator
    rg_match = RAPIDGATOR_RE.search(host_subject)
    if rg_match:
        return "Rapidgator", rg_match.group(1), norm_url

    # 1Fichier
    fich_match = ONEFICHIER_RE.search(host_subject)
    if fich_match:
        return "1Fichier", fich_match.group(1), norm_url

    # Turbobit
    tb_match = TURBOBIT_RE.search(host_subject)
    if tb_match:
        return "Turbobit", tb_match.group(1), norm_url

    # Nitroflare
    nf_match = NITROFLARE_RE.search(host_subject)
    if nf_match:
        return "Nitroflare", nf_match.group(1), norm_url

    # DDownload
    dd_match = DDOWNLOAD_RE.search(host_subject)
    if dd_match:
        return "DDownload", dd_match.group(1), norm_url

    # Katfile
    kf_match = KATFILE_RE.search(host_subject)
    if kf_match:
        return "Katfile", kf_match.group(1), norm_url

    # Pixeldrain
    pd_match = PIXELDRAIN_RE.search(host_subject)
    if pd_match:
        return "Pixeldrain", pd_match.group(1), f"https://pixeldrain.com/u/{pd_match.group(1)}"

    # Gofile
    gf_match = GOFILE_RE.search(host_subject)
    if gf_match:
        return "Gofile", gf_match.group(1), norm_url

    # Krakenfiles
    kraken_match = KRAKENFILES_RE.search(host_subject)
    if kraken_match:
        return "Krakenfiles", kraken_match.group(1), norm_url

    # Catbox / Litterbox
    cat_match = CATBOX_RE.search(host_subject)
    if cat_match:
        return "Catbox", cat_match.group(1), norm_url

    # Tmpfiles
    tmp_match = TMPFILES_RE.search(host_subject)
    if tmp_match:
        return "Tmpfiles", tmp_match.group(1), norm_url

    # Cyberfile / Cyberdrop / Saint2
    cf_match = CYBERFILE_RE.search(host_subject)
    if cf_match:
        return "Cyberfile", cf_match.group(1), norm_url

    # Google Drive
    gdrive_match = GDRIVE_RE.search(host_subject)
    if gdrive_match:
        return "Google Drive", gdrive_match.group(1), f"https://drive.google.com/file/d/{gdrive_match.group(1)}/view"

    # Dropbox
    db_match = DROPBOX_RE.search(host_subject)
    if db_match:
        return "Dropbox", db_match.group(1), norm_url

    # GitHub
    gh_match = GITHUB_RE.search(host_subject)
    if gh_match:
        return "GitHub", gh_match.group(1), norm_url

    # Workupload
    wu_match = WORKUPLOAD_RE.search(host_subject)
    if wu_match:
        return "Workupload", wu_match.group(1), norm_url

    # YouTube
    yt_match = YOUTUBE_ID_RE.search(norm_url) or YOUTUBE_ID_RE.search(url)
    if yt_match:
        vid_id = yt_match.group(1)
        return "YouTube", vid_id, f"https://www.youtube.com/watch?v={vid_id}"

    # Vimeo
    vimeo_match = VIMEO_ID_RE.search(norm_url) or VIMEO_ID_RE.search(url)
    if vimeo_match:
        vid_id = vimeo_match.group(1)
        return "Vimeo", vid_id, f"https://vimeo.com/{vid_id}"

    # Dailymotion
    dm_match = DAILYMOTION_ID_RE.search(norm_url) or DAILYMOTION_ID_RE.search(url)
    if dm_match:
        vid_id = dm_match.group(1)
        return "Dailymotion", vid_id, f"https://www.dailymotion.com/video/{vid_id}"

    # Internet Archive
    ia_match = ARCHIVE_ID_RE.search(norm_url) or ARCHIVE_ID_RE.search(url)
    if ia_match:
        vid_id = ia_match.group(1)
        return "Internet Archive", vid_id, f"https://archive.org/details/{vid_id}"

    # Bunkr (all bunkr.* and bunkrr.* domains)
    if BUNKR_RE.search(netloc):
        f_match = BUNKR_FILE_ID_RE.search(parsed.path)
        if f_match:
            vid_id = f_match.group(1)
            return "Bunkr", vid_id, norm_url
        a_match = BUNKR_ALBUM_ID_RE.search(parsed.path)
        if a_match:
            album_id = a_match.group(1)
            return "Bunkr", album_id, norm_url
        return "Bunkr", None, norm_url

    # Generic Web
    domain = netloc.capitalize() if netloc else "Web"
    return domain, None, norm_url


class DeduplicationEngine:
    """Merges duplicate candidate records from different sources into single rich records."""

    @classmethod
    def get_identity_key(cls, record: ItemRecord) -> str:
        """Determines unique identity key for a record."""
        if record.platform and record.platform_id:
            return f"{record.platform.lower()}:{record.platform_id}"
        # Fall back to canonical URL
        norm_url = normalize_url(record.canonical_url)
        return f"url:{norm_url}"

    @classmethod
    def merge_records(cls, existing: ItemRecord, incoming: ItemRecord) -> ItemRecord:
        """Merges incoming record into existing record preserving maximum metadata and provenance."""
        # Prefer richer title and description
        title = existing.title if len(existing.title) >= len(incoming.title) else incoming.title
        description = existing.description if len(existing.description) >= len(incoming.description) else incoming.description
        download_url = existing.download_url or incoming.download_url
        file_name = existing.file_name or incoming.file_name
        file_extension = existing.file_extension or incoming.file_extension
        file_size_bytes = existing.file_size_bytes or incoming.file_size_bytes
        file_size_human = existing.file_size_human or incoming.file_size_human

        # Prefer specific item type over generic FILE
        item_type = existing.item_type
        if item_type == ItemType.FILE and incoming.item_type != ItemType.FILE:
            item_type = incoming.item_type

        uploader_name = existing.uploader_name or incoming.uploader_name
        uploader_url = existing.uploader_url or incoming.uploader_url
        publication_date = existing.publication_date or incoming.publication_date
        duration_seconds = existing.duration_seconds or incoming.duration_seconds
        thumbnail_url = existing.thumbnail_url or incoming.thumbnail_url
        embed_url = existing.embed_url or incoming.embed_url
        view_count = max(filter(None, [existing.view_count, incoming.view_count]), default=None)
        like_count = max(filter(None, [existing.like_count, incoming.like_count]), default=None)
        language = existing.language or incoming.language

        # Merge tags and categories
        combined_tags = list(dict.fromkeys(existing.tags + incoming.tags))
        combined_categories = list(dict.fromkeys(existing.categories + incoming.categories))

        # Merge metadata sources
        combined_sources = list(dict.fromkeys(existing.metadata_sources + incoming.metadata_sources))

        # Merge raw metadata dictionaries
        merged_raw = {**existing.raw_metadata, **incoming.raw_metadata}

        # Merge provenance
        provenance = existing.provenance
        if incoming.provenance:
            if not provenance:
                provenance = incoming.provenance
            else:
                combined_terms = list(dict.fromkeys(provenance.matched_terms + incoming.provenance.matched_terms))
                combined_fields = list(dict.fromkeys(provenance.matched_fields + incoming.provenance.matched_fields))
                all_sources = list(dict.fromkeys(provenance.all_discovery_sources + incoming.provenance.all_discovery_sources))
                provenance = MatchProvenance(
                    discovery_source=provenance.discovery_source,
                    matched_terms=combined_terms,
                    matched_fields=combined_fields,
                    match_type=provenance.match_type,
                    match_spans=provenance.match_spans + incoming.provenance.match_spans,
                    all_discovery_sources=all_sources,
                )

        return ItemRecord(
            id=existing.id,
            canonical_url=existing.canonical_url,
            download_url=download_url,
            platform=existing.platform,
            platform_id=existing.platform_id,
            title=title,
            description=description,
            item_type=item_type,
            file_name=file_name,
            file_extension=file_extension,
            file_size_bytes=file_size_bytes,
            file_size_human=file_size_human,
            duration_seconds=duration_seconds,
            publication_date=publication_date,
            thumbnail_url=thumbnail_url,
            embed_url=embed_url,
            uploader_name=uploader_name,
            uploader_url=uploader_url,
            view_count=view_count,
            like_count=like_count,
            tags=combined_tags,
            categories=combined_categories,
            language=language,
            metadata_sources=combined_sources,
            raw_metadata=merged_raw,
            provenance=provenance,
        )

    @classmethod
    def deduplicate(cls, records: List[ItemRecord]) -> Tuple[List[ItemRecord], int]:
        """Deduplicates a list of records, returning (deduped_records, duplicates_removed_count)."""
        merged: Dict[str, ItemRecord] = {}
        duplicates_count = 0

        for rec in records:
            key = cls.get_identity_key(rec)
            if key in merged:
                merged[key] = cls.merge_records(merged[key], rec)
                duplicates_count += 1
            else:
                merged[key] = rec

        return list(merged.values()), duplicates_count
