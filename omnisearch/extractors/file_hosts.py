"""
Dedicated universal metadata and direct-download extractor for file hosting,
cyberlockers, cloud storage, open directories, and direct downloadable files.

Supports:
- Tier A: MediaFire, MEGA, Rapidgator, 1Fichier, Turbobit, Nitroflare, DDownload, Katfile, Fikper, Workupload
- Tier B: Pixeldrain, Gofile, Krakenfiles, Catbox, Tmpfiles, Cyberfile/Cyberdrop/Saint2, Bunkr (all mirrors)
- Tier C: Google Drive, Dropbox, OneDrive, GitHub Releases, Internet Archive
- Tier D: Open HTTP Directories (Apache, Nginx, Caddy Index of /), Direct file links across the web
"""

from __future__ import annotations
import re
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

from omnisearch.models.video import ItemRecord, ItemType, MetadataSource
from omnisearch.core.dedup import resolve_platform_and_id, normalize_url


KNOWN_EXTENSIONS = {
    # Archives
    "zip": ItemType.ARCHIVE, "rar": ItemType.ARCHIVE, "7z": ItemType.ARCHIVE,
    "tar": ItemType.ARCHIVE, "gz": ItemType.ARCHIVE, "bz2": ItemType.ARCHIVE,
    "xz": ItemType.ARCHIVE, "tgz": ItemType.ARCHIVE, "zst": ItemType.ARCHIVE,
    "tar.gz": ItemType.ARCHIVE, "tar.bz2": ItemType.ARCHIVE, "tar.xz": ItemType.ARCHIVE,
    # Documents
    "pdf": ItemType.DOCUMENT, "epub": ItemType.DOCUMENT, "mobi": ItemType.DOCUMENT,
    "doc": ItemType.DOCUMENT, "docx": ItemType.DOCUMENT, "txt": ItemType.DOCUMENT,
    "rtf": ItemType.DOCUMENT, "odt": ItemType.DOCUMENT, "ppt": ItemType.DOCUMENT,
    "pptx": ItemType.DOCUMENT, "xls": ItemType.DOCUMENT, "xlsx": ItemType.DOCUMENT,
    "csv": ItemType.DATASET,
    # Software & Binaries
    "exe": ItemType.SOFTWARE, "msi": ItemType.SOFTWARE, "dmg": ItemType.SOFTWARE,
    "pkg": ItemType.SOFTWARE, "deb": ItemType.SOFTWARE, "rpm": ItemType.SOFTWARE,
    "apk": ItemType.SOFTWARE, "iso": ItemType.SOFTWARE, "bin": ItemType.SOFTWARE,
    "appimage": ItemType.SOFTWARE, "sh": ItemType.SOFTWARE, "img": ItemType.SOFTWARE,
    # Audio
    "mp3": ItemType.AUDIO, "flac": ItemType.AUDIO, "wav": ItemType.AUDIO,
    "aac": ItemType.AUDIO, "ogg": ItemType.AUDIO, "m4a": ItemType.AUDIO,
    "wma": ItemType.AUDIO, "opus": ItemType.AUDIO,
    # Video
    "mp4": ItemType.VIDEO, "mkv": ItemType.VIDEO, "webm": ItemType.VIDEO,
    "avi": ItemType.VIDEO, "mov": ItemType.VIDEO, "flv": ItemType.VIDEO,
    "wmv": ItemType.VIDEO, "m4v": ItemType.VIDEO, "ts": ItemType.VIDEO,
    # Image
    "jpg": ItemType.IMAGE, "jpeg": ItemType.IMAGE, "png": ItemType.IMAGE,
    "gif": ItemType.IMAGE, "webp": ItemType.IMAGE, "svg": ItemType.IMAGE,
    "bmp": ItemType.IMAGE, "tiff": ItemType.IMAGE,
    # Datasets / Databases
    "json": ItemType.DATASET, "jsonl": ItemType.DATASET, "parquet": ItemType.DATASET,
    "sqlite": ItemType.DATASET, "db": ItemType.DATASET, "sql": ItemType.DATASET,
    "torrent": ItemType.FILE,
}

FILE_HOST_DOMAINS = {
    "mediafire": re.compile(r"mediafire\.com", re.I),
    "mega": re.compile(r"mega\.(?:nz|io)", re.I),
    "rapidgator": re.compile(r"rapidgator\.net", re.I),
    "1fichier": re.compile(r"1fichier\.com", re.I),
    "turbobit": re.compile(r"turbobit\.net", re.I),
    "nitroflare": re.compile(r"nitroflare\.com", re.I),
    "ddownload": re.compile(r"ddownload\.com", re.I),
    "katfile": re.compile(r"katfile\.com", re.I),
    "pixeldrain": re.compile(r"pixeldrain\.com", re.I),
    "gofile": re.compile(r"gofile\.io", re.I),
    "krakenfiles": re.compile(r"krakenfiles\.com", re.I),
    "catbox": re.compile(r"(?:files\.)?catbox\.moe|litterbox\.catbox\.moe", re.I),
    "tmpfiles": re.compile(r"tmpfiles\.org", re.I),
    "cyberfile": re.compile(r"cyberfile\.[a-z]+|cyberdrop\.[a-z]+|saint2\.[a-z]+", re.I),
    "bunkr": re.compile(r"bunkr\.[a-z]+|bunkrr\.[a-z]+|bunker\.[a-z]+", re.I),
    "gdrive": re.compile(r"drive\.google\.com", re.I),
    "dropbox": re.compile(r"dropbox\.com", re.I),
    "workupload": re.compile(r"workupload\.com", re.I),
}


def detect_file_extension(filename_or_url: str) -> Optional[str]:
    """Extracts lowercase file extension without leading dot."""
    if not filename_or_url:
        return None
    # If it's a URL, extract path component
    if filename_or_url.startswith("http://") or filename_or_url.startswith("https://"):
        try:
            parsed = urlparse(filename_or_url)
            path = parsed.path.rstrip("/")
            if not path or path == "/":
                return None
            clean = path.split("/")[-1]
        except Exception:
            clean = filename_or_url.split("?")[0].split("#")[0].rstrip("/")
    else:
        clean = filename_or_url.split("?")[0].split("#")[0].rstrip("/")
    # Check compound extensions first like tar.gz
    if clean.lower().endswith(".tar.gz") or clean.lower().endswith(".tar.xz"):
        return "tar.gz"
    parts = clean.split(".")
    if len(parts) > 1 and parts[0]:
        ext = parts[-1].lower()
        if ext in ("html", "htm", "php", "asp", "aspx", "jsp"):
            return None
        if ext in KNOWN_EXTENSIONS:
            return ext
        if 1 <= len(ext) <= 5 and ext.isalnum():
            # Exclude common domain TLDs
            if ext not in ("org", "com", "net", "edu", "gov", "mil", "io", "co", "ai", "app", "dev", "me", "info", "biz"):
                return ext
    return None


def infer_item_type(extension: Optional[str]) -> ItemType:
    """Infers ItemType from extension."""
    if not extension:
        return ItemType.FILE
    ext_clean = extension.lower().lstrip(".")
    if ext_clean in KNOWN_EXTENSIONS:
        return KNOWN_EXTENSIONS[ext_clean]
    return ItemType.FILE


def format_bytes(size_bytes: int) -> str:
    """Formats bytes to human readable string (e.g. 1.45 GB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    val = float(size_bytes)
    for unit in ["KB", "MB", "GB", "TB", "PB"]:
        val /= 1024.0
        if val < 1024.0 or unit == "PB":
            formatted = f"{val:.2f}".rstrip("0").rstrip(".")
            return f"{formatted} {unit}"
    return f"{val:.2f} EB"


def parse_size_str(text: str) -> Optional[int]:
    """Parses size strings like '1.45 GB', '25 MB', '(145.2 MB)', '350M', '45M' into byte count."""
    if not text:
        return None
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMGTPE]B?|bytes|b)\b", text, re.I)
    if not match:
        return None
    num = float(match.group(1))
    unit = match.group(2).upper()
    multipliers = {
        "BYTES": 1, "B": 1,
        "KB": 1024, "KIB": 1024, "K": 1024,
        "MB": 1024**2, "MIB": 1024**2, "M": 1024**2,
        "GB": 1024**3, "GIB": 1024**3, "G": 1024**3,
        "TB": 1024**4, "TIB": 1024**4, "T": 1024**4,
        "PB": 1024**5, "PIB": 1024**5, "P": 1024**5,
    }
    if unit in multipliers:
        return int(num * multipliers[unit])
    for k, mult in multipliers.items():
        if unit.startswith(k):
            return int(num * mult)
    return int(num)


class FileHostExtractor:
    """Universal extractor for file hosts, cyberlockers, cloud storage, open directories, and downloads."""

    @classmethod
    def is_file_host_url(cls, url: str) -> bool:
        domain = urlparse(url).netloc.lower()
        return any(pattern.search(domain) for pattern in FILE_HOST_DOMAINS.values())

    @classmethod
    def extract(cls, html_content: str, page_url: str) -> Optional[ItemRecord]:
        """Dispatches specialized extractors based on URL domain or page structure."""
        if not html_content:
            return None

        domain = urlparse(page_url).netloc.lower()
        soup = BeautifulSoup(html_content, "html.parser")

        # 1. MediaFire
        if FILE_HOST_DOMAINS["mediafire"].search(domain):
            return cls._extract_mediafire(soup, page_url)

        # 2. MEGA
        if FILE_HOST_DOMAINS["mega"].search(domain):
            return cls._extract_mega(soup, page_url)

        # 3. Rapidgator
        if FILE_HOST_DOMAINS["rapidgator"].search(domain):
            return cls._extract_rapidgator(soup, page_url)

        # 4. 1Fichier
        if FILE_HOST_DOMAINS["1fichier"].search(domain):
            return cls._extract_1fichier(soup, page_url)

        # 5. Turbobit & Nitroflare & DDownload & Katfile
        if (
            FILE_HOST_DOMAINS["turbobit"].search(domain)
            or FILE_HOST_DOMAINS["nitroflare"].search(domain)
            or FILE_HOST_DOMAINS["ddownload"].search(domain)
            or FILE_HOST_DOMAINS["katfile"].search(domain)
        ):
            return cls._extract_generic_cyberlocker(soup, page_url)

        # 6. Pixeldrain
        if FILE_HOST_DOMAINS["pixeldrain"].search(domain):
            return cls._extract_pixeldrain(soup, page_url)

        # 7. Gofile
        if FILE_HOST_DOMAINS["gofile"].search(domain):
            return cls._extract_gofile(soup, page_url)

        # 8. Krakenfiles
        if FILE_HOST_DOMAINS["krakenfiles"].search(domain):
            return cls._extract_krakenfiles(soup, page_url)

        # 9. Catbox & Litterbox
        if FILE_HOST_DOMAINS["catbox"].search(domain):
            return cls._extract_catbox(soup, page_url)

        # 10. Tmpfiles
        if FILE_HOST_DOMAINS["tmpfiles"].search(domain):
            return cls._extract_tmpfiles(soup, page_url)

        # 11. Cyberfile & Cyberdrop & Saint2
        if FILE_HOST_DOMAINS["cyberfile"].search(domain):
            return cls._extract_cyberfile(soup, page_url)

        # 12. Bunkr (all domains)
        if FILE_HOST_DOMAINS["bunkr"].search(domain):
            return cls._extract_bunkr(soup, page_url)

        # 13. Google Drive
        if FILE_HOST_DOMAINS["gdrive"].search(domain):
            return cls._extract_google_drive(soup, page_url)

        # 14. Dropbox
        if FILE_HOST_DOMAINS["dropbox"].search(domain):
            return cls._extract_dropbox(soup, page_url)

        # 15. Workupload
        if FILE_HOST_DOMAINS["workupload"].search(domain):
            return cls._extract_workupload(soup, page_url)

        # 16. Check if page is an Open HTTP Directory (`Index of /`)
        if cls.is_open_directory(soup, page_url):
            return cls._extract_open_directory_root(soup, page_url)

        # 17. Generic Web Page with direct downloadable links
        return cls._extract_generic_download_page(soup, page_url)

    @classmethod
    def _extract_mediafire(cls, soup: BeautifulSoup, page_url: str) -> Optional[ItemRecord]:
        """Extracts filename, size, and direct download link from MediaFire."""
        title_tag = soup.find("div", class_="filename") or soup.find("div", class_="dl-btn-label") or soup.find("h1")
        title = title_tag.get_text().strip() if title_tag else ""
        if not title:
            title_tag = soup.find("title")
            title = title_tag.get_text().replace("MediaFire", "").strip(" -|") if title_tag else "MediaFire File"

        # Direct download button
        dl_button = (
            soup.find("a", id="downloadButton")
            or soup.find("a", attrs={"aria-label": re.compile("Download file", re.I)})
            or soup.find("a", class_=re.compile("input popsok|download_link", re.I))
        )
        direct_url = dl_button.get("href") if dl_button else None
        if direct_url and not direct_url.startswith("http"):
            direct_url = urljoin(page_url, direct_url)

        # File size
        size_bytes = None
        size_elem = soup.find("ul", class_="details") or soup.find("div", class_="dl-btn-label")
        if size_elem:
            size_bytes = parse_size_str(size_elem.get_text())

        ext = detect_file_extension(title) or detect_file_extension(direct_url or "")
        item_type = infer_item_type(ext)
        platform, platform_id, canonical = resolve_platform_and_id(page_url)

        return ItemRecord(
            id=f"mediafire:{platform_id or canonical}",
            canonical_url=canonical,
            download_url=direct_url,
            platform="MediaFire",
            platform_id=platform_id,
            title=title,
            description=f"MediaFire hosted file: {title} ({format_bytes(size_bytes) if size_bytes else 'Download'})",
            item_type=item_type,
            file_name=title,
            file_extension=ext,
            file_size_bytes=size_bytes,
            file_size_human=format_bytes(size_bytes) if size_bytes else None,
            tags=["mediafire", "file-host", ext] if ext else ["mediafire", "file-host"],
            metadata_sources=[MetadataSource.FILE_HOST_PAGE],
            raw_metadata={"file_host": "mediafire", "direct_link": direct_url},
        )

    @classmethod
    def _extract_mega(cls, soup: BeautifulSoup, page_url: str) -> Optional[ItemRecord]:
        """Extracts MEGA file/folder information."""
        title_tag = soup.find("title")
        title = title_tag.get_text().replace("MEGA", "").strip(" -|") if title_tag else "MEGA File"
        platform, platform_id, canonical = resolve_platform_and_id(page_url)
        ext = detect_file_extension(title)
        item_type = infer_item_type(ext)

        return ItemRecord(
            id=f"mega:{platform_id or canonical}",
            canonical_url=canonical,
            download_url=canonical,
            platform="MEGA",
            platform_id=platform_id,
            title=title or "MEGA Shared File",
            description=f"MEGA cloud storage shared file/folder: {title}",
            item_type=item_type,
            file_name=title if ext else None,
            file_extension=ext,
            tags=["mega", "cloud-storage", ext] if ext else ["mega", "cloud-storage"],
            metadata_sources=[MetadataSource.FILE_HOST_PAGE],
            raw_metadata={"file_host": "mega"},
        )

    @classmethod
    def _extract_rapidgator(cls, soup: BeautifulSoup, page_url: str) -> Optional[ItemRecord]:
        """Extracts Rapidgator file title, size, and download link."""
        title_tag = soup.find("h1") or soup.find("div", class_="file-info") or soup.find("title")
        title = title_tag.get_text().replace("Download file", "").strip() if title_tag else "Rapidgator File"
        title = re.sub(r"\s*Rapidgator\s*", "", title, flags=re.I).strip(" -|")

        size_bytes = parse_size_str(soup.get_text())
        ext = detect_file_extension(title)
        item_type = infer_item_type(ext)
        platform, platform_id, canonical = resolve_platform_and_id(page_url)

        return ItemRecord(
            id=f"rapidgator:{platform_id or canonical}",
            canonical_url=canonical,
            download_url=canonical,
            platform="Rapidgator",
            platform_id=platform_id,
            title=title,
            description=f"Rapidgator file: {title} ({format_bytes(size_bytes) if size_bytes else 'Download'})",
            item_type=item_type,
            file_name=title,
            file_extension=ext,
            file_size_bytes=size_bytes,
            file_size_human=format_bytes(size_bytes) if size_bytes else None,
            tags=["rapidgator", "file-host"],
            metadata_sources=[MetadataSource.FILE_HOST_PAGE],
            raw_metadata={"file_host": "rapidgator"},
        )

    @classmethod
    def _extract_1fichier(cls, soup: BeautifulSoup, page_url: str) -> Optional[ItemRecord]:
        """Extracts 1Fichier file title, size, and download link."""
        table = soup.find("table")
        title = ""
        size_bytes = None
        if table:
            for tr in table.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) >= 2:
                    header = tds[0].get_text().strip()
                    val = tds[1].get_text().strip()
                    if "filename" in header.lower() or "file name" in header.lower():
                        title = val
                    elif "size" in header.lower():
                        size_bytes = parse_size_str(val)

        if not title:
            title_tag = soup.find("h1") or soup.find("title")
            title = title_tag.get_text().replace("1fichier", "").strip(" -|") if title_tag else "1Fichier File"

        ext = detect_file_extension(title)
        item_type = infer_item_type(ext)
        platform, platform_id, canonical = resolve_platform_and_id(page_url)

        return ItemRecord(
            id=f"1fichier:{platform_id or canonical}",
            canonical_url=canonical,
            download_url=canonical,
            platform="1Fichier",
            platform_id=platform_id,
            title=title,
            description=f"1Fichier hosted file: {title}",
            item_type=item_type,
            file_name=title,
            file_extension=ext,
            file_size_bytes=size_bytes,
            file_size_human=format_bytes(size_bytes) if size_bytes else None,
            tags=["1fichier", "file-host"],
            metadata_sources=[MetadataSource.FILE_HOST_PAGE],
            raw_metadata={"file_host": "1fichier"},
        )

    @classmethod
    def _extract_pixeldrain(cls, soup: BeautifulSoup, page_url: str) -> Optional[ItemRecord]:
        """Extracts Pixeldrain file title, size, and direct download endpoint."""
        parts = page_url.rstrip("/").split("/")
        file_id = parts[-1] if parts else "file"

        title_tag = soup.find("title")
        title = title_tag.get_text().replace("pixeldrain", "").strip(" -|") if title_tag else f"Pixeldrain File {file_id}"

        thumb_url = f"https://pixeldrain.com/api/file/{file_id}/thumbnail"
        direct_download = f"https://pixeldrain.com/api/file/{file_id}"
        ext = detect_file_extension(title)
        item_type = infer_item_type(ext)

        return ItemRecord(
            id=f"pixeldrain:{file_id}",
            canonical_url=f"https://pixeldrain.com/u/{file_id}",
            download_url=direct_download,
            platform="Pixeldrain",
            platform_id=file_id,
            title=title,
            description=f"Pixeldrain upload: {title}",
            item_type=item_type,
            file_name=title,
            file_extension=ext,
            thumbnail_url=thumb_url,
            embed_url=f"https://pixeldrain.com/u/{file_id}",
            tags=["pixeldrain", "file-host"],
            metadata_sources=[MetadataSource.FILE_HOST_PAGE],
            raw_metadata={"file_host": "pixeldrain", "file_id": file_id, "direct_download": direct_download},
        )

    @classmethod
    def _extract_gofile(cls, soup: BeautifulSoup, page_url: str) -> Optional[ItemRecord]:
        """Extracts Gofile folder / file page."""
        title_tag = soup.find("title")
        title = title_tag.get_text().replace("Gofile", "").strip(" -|") if title_tag else "Gofile Upload"
        platform, platform_id, canonical = resolve_platform_and_id(page_url)
        ext = detect_file_extension(title)

        return ItemRecord(
            id=f"gofile:{platform_id or canonical}",
            canonical_url=canonical,
            download_url=canonical,
            platform="Gofile",
            platform_id=platform_id,
            title=title,
            description=f"Gofile upload: {title}",
            item_type=infer_item_type(ext),
            file_name=title if ext else None,
            file_extension=ext,
            tags=["gofile", "file-host"],
            metadata_sources=[MetadataSource.FILE_HOST_PAGE],
            raw_metadata={"file_host": "gofile"},
        )

    @classmethod
    def _extract_krakenfiles(cls, soup: BeautifulSoup, page_url: str) -> Optional[ItemRecord]:
        """Extracts Krakenfiles title, size, and direct download."""
        title_tag = soup.find("div", class_="coin-name") or soup.find("h5") or soup.find("title")
        title = title_tag.get_text().strip() if title_tag else "Krakenfiles File"

        dl_btn = soup.find("a", class_=re.compile("btn-download|download-now", re.I)) or soup.find("a", href=re.compile(r"/download/", re.I))
        direct_url = urljoin(page_url, dl_btn.get("href")) if dl_btn and dl_btn.get("href") else None

        size_bytes = parse_size_str(soup.get_text())
        ext = detect_file_extension(title)
        platform, platform_id, canonical = resolve_platform_and_id(page_url)

        return ItemRecord(
            id=f"krakenfiles:{platform_id or canonical}",
            canonical_url=canonical,
            download_url=direct_url or canonical,
            platform="Krakenfiles",
            platform_id=platform_id,
            title=title,
            description=f"Krakenfiles file: {title} ({format_bytes(size_bytes) if size_bytes else 'Download'})",
            item_type=infer_item_type(ext),
            file_name=title,
            file_extension=ext,
            file_size_bytes=size_bytes,
            file_size_human=format_bytes(size_bytes) if size_bytes else None,
            tags=["krakenfiles", "file-host"],
            metadata_sources=[MetadataSource.FILE_HOST_PAGE],
            raw_metadata={"file_host": "krakenfiles", "direct_link": direct_url},
        )

    @classmethod
    def _extract_catbox(cls, soup: BeautifulSoup, page_url: str) -> Optional[ItemRecord]:
        """Extracts direct file download from Catbox / Litterbox."""
        parsed = urlparse(page_url)
        filename = parsed.path.strip("/")
        ext = detect_file_extension(filename)
        platform, platform_id, canonical = resolve_platform_and_id(page_url)

        return ItemRecord(
            id=f"catbox:{canonical}",
            canonical_url=canonical,
            download_url=canonical,
            platform="Catbox",
            platform_id=platform_id or filename,
            title=filename or "Catbox Upload",
            description=f"Direct Catbox file: {filename}",
            item_type=infer_item_type(ext),
            file_name=filename,
            file_extension=ext,
            tags=["catbox", "direct-download"],
            metadata_sources=[MetadataSource.DIRECT_LINK],
            raw_metadata={"file_host": "catbox"},
        )

    @classmethod
    def _extract_tmpfiles(cls, soup: BeautifulSoup, page_url: str) -> Optional[ItemRecord]:
        """Extracts Tmpfiles direct download."""
        title_tag = soup.find("title")
        title = title_tag.get_text().replace("tmpfiles", "").strip(" -|") if title_tag else "Tmpfiles Upload"

        download_link = soup.find("a", href=re.compile(r"/dl/", re.I))
        direct_url = urljoin(page_url, download_link.get("href")) if download_link else None

        # Automatically construct direct /dl/ URL if missing
        if not direct_url and "tmpfiles.org/" in page_url and "/dl/" not in page_url:
            direct_url = page_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")

        ext = detect_file_extension(title) or detect_file_extension(direct_url or "")
        platform, platform_id, canonical = resolve_platform_and_id(page_url)

        return ItemRecord(
            id=f"tmpfiles:{canonical}",
            canonical_url=canonical,
            download_url=direct_url or canonical,
            embed_url=direct_url,
            platform="Tmpfiles",
            platform_id=platform_id,
            title=title,
            description=f"Temporary file host upload on tmpfiles.org: {title}",
            item_type=infer_item_type(ext),
            file_name=title,
            file_extension=ext,
            tags=["tmpfiles", "file-host"],
            metadata_sources=[MetadataSource.FILE_HOST_PAGE],
            raw_metadata={"file_host": "tmpfiles", "direct_link": direct_url},
        )

    @classmethod
    def _extract_cyberfile(cls, soup: BeautifulSoup, page_url: str) -> Optional[ItemRecord]:
        """Extracts Cyberfile, Cyberdrop, and Saint2 uploads."""
        title_tag = soup.find("h1") or soup.find("title")
        title = title_tag.get_text().strip() if title_tag else "Cyberfile Media"
        title = re.sub(r"\s*(Cyberfile|Cyberdrop|Saint2)\s*", "", title, flags=re.I).strip(" -|")

        download_link = soup.find("a", href=re.compile(r"\.(mp4|m4v|mkv|mov|webm|zip|rar|7z|pdf)$|/download/|/get/", re.I))
        direct_link = urljoin(page_url, download_link.get("href")) if download_link else None

        ext = detect_file_extension(title) or detect_file_extension(direct_link or "")
        platform, platform_id, canonical = resolve_platform_and_id(page_url)

        return ItemRecord(
            id=f"cyberfile:{canonical}",
            canonical_url=canonical,
            download_url=direct_link,
            platform="Cyberfile",
            platform_id=platform_id,
            title=title or "Cyberfile Upload",
            description=f"Cyberfile hosted file: {title}",
            item_type=infer_item_type(ext),
            file_name=title,
            file_extension=ext,
            tags=["cyberfile", "file-host"],
            metadata_sources=[MetadataSource.FILE_HOST_PAGE],
            raw_metadata={"file_host": "cyberfile", "direct_link": direct_link},
        )

    @classmethod
    def _extract_bunkr(cls, soup: BeautifulSoup, page_url: str) -> Optional[ItemRecord]:
        """Extracts Bunkr files across all Bunkr domains with direct download links."""
        h1 = soup.find("h1")
        title = h1.get_text().strip() if h1 else ""
        if not title:
            title_tag = soup.find("title")
            title = title_tag.get_text().replace("Bunkr", "").strip(" -|") if title_tag else ""

        video_tag = soup.find("video")
        video_src = video_tag.get("src") if video_tag else None
        if not video_src and video_tag:
            source = video_tag.find("source")
            if source:
                video_src = source.get("src")

        download_link = soup.find("a", href=re.compile(r"/file/|/download/|dl\.", re.I))
        direct_link = download_link.get("href") if download_link else video_src
        if direct_link and not direct_link.startswith("http"):
            direct_link = urljoin(page_url, direct_link)

        thumb_url = video_tag.get("poster") if video_tag else None
        if not thumb_url:
            img = soup.find("img", class_=re.compile(r"thumb|preview|poster", re.I))
            if img:
                thumb_url = img.get("src")

        ext = detect_file_extension(title) or detect_file_extension(direct_link or "") or "mp4"
        platform, platform_id, canonical = resolve_platform_and_id(page_url)

        return ItemRecord(
            id=f"bunkr:{canonical}",
            canonical_url=canonical,
            download_url=direct_link or canonical,
            platform="Bunkr",
            platform_id=platform_id,
            title=title or "Bunkr File",
            description=f"Bunkr file: {title}",
            item_type=infer_item_type(ext),
            file_name=title,
            file_extension=ext,
            thumbnail_url=thumb_url,
            embed_url=direct_link or canonical,
            tags=["bunkr", "file-host"],
            metadata_sources=[MetadataSource.FILE_HOST_PAGE],
            raw_metadata={"file_host": "bunkr", "direct_link": direct_link},
        )

    @classmethod
    def _extract_google_drive(cls, soup: BeautifulSoup, page_url: str) -> Optional[ItemRecord]:
        """Converts Google Drive share URL into direct download URL and extracts metadata."""
        platform, platform_id, canonical = resolve_platform_and_id(page_url)
        direct_download = f"https://drive.google.com/uc?export=download&id={platform_id}" if platform_id else canonical

        title_tag = soup.find("meta", property="og:title") or soup.find("title")
        title = title_tag.get("content") if title_tag and title_tag.get("content") else (title_tag.get_text().replace("Google Drive", "").strip(" -|") if title_tag else f"Google Drive File {platform_id}")

        ext = detect_file_extension(title)

        return ItemRecord(
            id=f"gdrive:{platform_id or canonical}",
            canonical_url=canonical,
            download_url=direct_download,
            platform="Google Drive",
            platform_id=platform_id,
            title=title,
            description=f"Google Drive cloud storage file: {title}",
            item_type=infer_item_type(ext),
            file_name=title if ext else None,
            file_extension=ext,
            tags=["google-drive", "cloud-storage"],
            metadata_sources=[MetadataSource.FILE_HOST_PAGE],
            raw_metadata={"file_host": "gdrive", "direct_download": direct_download},
        )

    @classmethod
    def _extract_dropbox(cls, soup: BeautifulSoup, page_url: str) -> Optional[ItemRecord]:
        """Converts Dropbox share link to direct download link (?dl=1)."""
        platform, platform_id, canonical = resolve_platform_and_id(page_url)
        clean_url = canonical.split("?")[0]
        direct_download = f"{clean_url}?dl=1"

        title_tag = soup.find("title")
        title = title_tag.get_text().replace("Dropbox", "").strip(" -|") if title_tag else "Dropbox File"
        ext = detect_file_extension(title)

        return ItemRecord(
            id=f"dropbox:{platform_id or canonical}",
            canonical_url=canonical,
            download_url=direct_download,
            platform="Dropbox",
            platform_id=platform_id,
            title=title,
            description=f"Dropbox shared file: {title}",
            item_type=infer_item_type(ext),
            file_name=title if ext else None,
            file_extension=ext,
            tags=["dropbox", "cloud-storage"],
            metadata_sources=[MetadataSource.FILE_HOST_PAGE],
            raw_metadata={"file_host": "dropbox", "direct_download": direct_download},
        )

    @classmethod
    def _extract_workupload(cls, soup: BeautifulSoup, page_url: str) -> Optional[ItemRecord]:
        """Extracts Workupload file title, size, and download link."""
        title_tag = soup.find("h1") or soup.find("title")
        title = title_tag.get_text().replace("workupload", "").strip(" -|") if title_tag else "Workupload File"

        dl_btn = soup.find("a", href=re.compile(r"/start/", re.I)) or soup.find("a", id=re.compile("download", re.I))
        direct_url = urljoin(page_url, dl_btn.get("href")) if dl_btn else None

        size_bytes = parse_size_str(soup.get_text())
        ext = detect_file_extension(title)
        platform, platform_id, canonical = resolve_platform_and_id(page_url)

        return ItemRecord(
            id=f"workupload:{platform_id or canonical}",
            canonical_url=canonical,
            download_url=direct_url or canonical,
            platform="Workupload",
            platform_id=platform_id,
            title=title,
            description=f"Workupload file: {title}",
            item_type=infer_item_type(ext),
            file_name=title,
            file_extension=ext,
            file_size_bytes=size_bytes,
            file_size_human=format_bytes(size_bytes) if size_bytes else None,
            tags=["workupload", "file-host"],
            metadata_sources=[MetadataSource.FILE_HOST_PAGE],
            raw_metadata={"file_host": "workupload"},
        )

    @classmethod
    def _extract_generic_cyberlocker(cls, soup: BeautifulSoup, page_url: str) -> Optional[ItemRecord]:
        """Extracts title, size, and download link from generic cyberlockers (Turbobit, Nitroflare, DDownload, Katfile, etc.)."""
        title_tag = soup.find("h1") or soup.find("h2") or soup.find("title")
        title = title_tag.get_text().strip() if title_tag else ""

        platform, platform_id, canonical = resolve_platform_and_id(page_url)
        title = re.sub(rf"\s*{re.escape(platform)}\s*", "", title, flags=re.I).strip(" -|")

        size_bytes = parse_size_str(soup.get_text())
        ext = detect_file_extension(title)
        dl_btn = soup.find("a", href=re.compile(r"/download/|/dl/|\.(?:zip|rar|7z|tar\.gz|iso|exe|pdf)", re.I))
        direct_url = urljoin(page_url, dl_btn.get("href")) if dl_btn else None

        return ItemRecord(
            id=f"locker:{canonical}",
            canonical_url=canonical,
            download_url=direct_url or canonical,
            platform=platform,
            platform_id=platform_id,
            title=title or f"{platform} Hosted File",
            description=f"Hosted file on {platform}: {title} ({format_bytes(size_bytes) if size_bytes else 'Download'})",
            item_type=infer_item_type(ext),
            file_name=title if ext else None,
            file_extension=ext,
            file_size_bytes=size_bytes,
            file_size_human=format_bytes(size_bytes) if size_bytes else None,
            tags=["file-host", platform.lower()],
            metadata_sources=[MetadataSource.FILE_HOST_PAGE],
            raw_metadata={"file_host": platform, "direct_link": direct_url},
        )

    @classmethod
    def is_open_directory(cls, soup: BeautifulSoup, page_url: str) -> bool:
        """Determines if a webpage is an Apache, Nginx, or Caddy open directory index."""
        title_tag = soup.find("title")
        h1 = soup.find("h1")
        check_text = (title_tag.get_text() if title_tag else "") + " " + (h1.get_text() if h1 else "")
        return bool(re.search(r"index of\s*/", check_text, re.I))

    @classmethod
    def _extract_open_directory_root(cls, soup: BeautifulSoup, page_url: str) -> Optional[ItemRecord]:
        """Summarizes an Open Directory root into an ItemRecord with links to its contents."""
        title_tag = soup.find("title")
        title = title_tag.get_text().strip() if title_tag else "Open Directory Index"
        links = soup.find_all("a", href=True)
        files_count = len([l for l in links if not l["href"].startswith("?") and l["href"] != "../"])

        return ItemRecord(
            id=f"opendir:{normalize_url(page_url)}",
            canonical_url=normalize_url(page_url),
            download_url=normalize_url(page_url),
            platform="Open Directory",
            title=title,
            description=f"Open HTTP server directory listing with {files_count} indexed items.",
            item_type=ItemType.FILE,
            tags=["open-directory", "index-of"],
            metadata_sources=[MetadataSource.OPEN_DIRECTORY],
            raw_metadata={"open_directory": True, "items_count": files_count},
        )

    @classmethod
    def extract_open_directory_files(cls, html_content: str, page_url: str) -> List[ItemRecord]:
        """Parses individual file rows inside an open directory listing."""
        soup = BeautifulSoup(html_content, "html.parser")
        records: List[ItemRecord] = []

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            name = a.get_text().strip()
            if href.startswith("?") or href in ("../", "./", "/") or href.endswith("/") or name.endswith("/"):
                continue
            if "parent directory" in name.lower() or "parent directory" in href.lower():
                continue

            file_url = urljoin(page_url, href)
            ext = detect_file_extension(name) or detect_file_extension(file_url)
            item_type = infer_item_type(ext)

            # Try to find file size in table row or sibling text
            parent = a.find_parent(["tr", "pre", "p"])
            size_bytes = parse_size_str(parent.get_text()) if parent else None

            rec = ItemRecord(
                id=f"opendir_file:{normalize_url(file_url)}",
                canonical_url=file_url,
                download_url=file_url,
                platform="Open Directory",
                title=name,
                description=f"Direct file from open directory ({format_bytes(size_bytes) if size_bytes else 'Download'})",
                item_type=item_type,
                file_name=name,
                file_extension=ext,
                file_size_bytes=size_bytes,
                file_size_human=format_bytes(size_bytes) if size_bytes else None,
                tags=["open-directory", "direct-download", ext] if ext else ["open-directory", "direct-download"],
                metadata_sources=[MetadataSource.OPEN_DIRECTORY, MetadataSource.DIRECT_LINK],
                raw_metadata={"file_url": file_url},
            )
            records.append(rec)

        return records

    @classmethod
    def _extract_generic_download_page(cls, soup: BeautifulSoup, page_url: str) -> Optional[ItemRecord]:
        """Inspects any web page for prominent downloadable files or download buttons."""
        title_tag = soup.find("title") or soup.find("h1")
        title = title_tag.get_text().strip() if title_tag else "Web Page"

        # Check for downloadable file anchor
        dl_links = soup.find_all(
            "a",
            href=re.compile(r"\.(?:zip|rar|7z|tar\.gz|tar\.xz|iso|exe|msi|dmg|pkg|deb|rpm|apk|pdf|epub|mp4|mkv)$|/download/|/releases/download/", re.I)
        )
        direct_url = None
        ext = None
        if dl_links:
            first_dl = dl_links[0]
            href = first_dl.get("href", "")
            direct_url = urljoin(page_url, href)
            ext = detect_file_extension(direct_url) or detect_file_extension(first_dl.get_text())

        if not ext:
            ext = detect_file_extension(page_url)

        item_type = infer_item_type(ext) if ext else ItemType.WEB_PAGE
        platform, platform_id, canonical = resolve_platform_and_id(page_url)
        desc_meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
        desc = desc_meta.get("content", "").strip() if desc_meta else ""

        return ItemRecord(
            id=f"web:{canonical}",
            canonical_url=canonical,
            download_url=direct_url,
            platform=platform,
            platform_id=platform_id,
            title=title,
            description=desc or f"Page on {platform}",
            item_type=item_type,
            file_name=title if ext else None,
            file_extension=ext,
            tags=[ext] if ext else [],
            metadata_sources=[MetadataSource.HTML_META],
            raw_metadata={"source": "generic_web", "direct_link": direct_url},
        )
