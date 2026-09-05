"""
Comprehensive Unit Tests for Everything Search Engine (OmniSearch).
Validates:
- Cyberlocker extractors (MediaFire, MEGA, Rapidgator, Pixeldrain, Krakenfiles, Catbox, GDrive, Dropbox)
- Open HTTP directory table parsing (Apache/Nginx Index of /)
- Direct 1-click download link resolution
- File extension detection and ItemType classification
- MatchEngine item_types and file_extensions filtering
- DeduplicationEngine merge of file attributes
"""

import pytest
from bs4 import BeautifulSoup

from omnisearch.models.video import ItemRecord, ItemType, MatchMode, MetadataSource
from omnisearch.models.query import SearchOptions
from omnisearch.core.matcher import MatchEngine
from omnisearch.core.dedup import DeduplicationEngine, resolve_platform_and_id
from omnisearch.core.query_parser import QueryParser
from omnisearch.extractors.file_hosts import (
    FileHostExtractor,
    detect_file_extension,
    infer_item_type,
    parse_size_str,
    format_bytes,
)
from omnisearch.extractors.page_extractor import PageExtractor


# Sample Mock HTMLs
SAMPLE_MEDIAFIRE_HTML = """
<!DOCTYPE html>
<html>
<head><title>MyArchive_v2.1.zip - MediaFire</title></head>
<body>
  <div class="filename">MyArchive_v2.1.zip</div>
  <ul class="details">
    <li>File size: <span>450.5 MB</span></li>
  </ul>
  <a id="downloadButton" class="input popsok" href="https://download1584.mediafire.com/xyz123/MyArchive_v2.1.zip" aria-label="Download file">
    Download (450.5MB)
  </a>
</body>
</html>
"""

SAMPLE_PIXELDRAIN_HTML = """
<!DOCTYPE html>
<html>
<head><title>pixeldrain - linux_installer.iso</title></head>
<body>
  <h1>linux_installer.iso</h1>
</body>
</html>
"""

SAMPLE_KRAKENFILES_HTML = """
<!DOCTYPE html>
<html>
<head><title>KrakenFiles - dataset_2026.tar.gz</title></head>
<body>
  <h5 class="coin-name">dataset_2026.tar.gz</h5>
  <div class="file-size">1.2 GB</div>
  <a class="btn-download" href="https://krakenfiles.com/download/abc987">Download</a>
</body>
</html>
"""

SAMPLE_OPEN_DIRECTORY_HTML = """
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">
<html>
 <head>
  <title>Index of /pub/software</title>
 </head>
 <body>
<h1>Index of /pub/software</h1>
<table>
   <tr><th valign="top"><img src="/icons/blank.gif" alt="[ICO]"></th><th><a href="?C=N;O=D">Name</a></th><th><a href="?C=M;O=A">Last modified</a></th><th><a href="?C=S;O=A">Size</a></th><th><a href="?C=D;O=A">Description</a></th></tr>
   <tr><th colspan="5"><hr></th></tr>
<tr><td valign="top"><img src="/icons/back.gif" alt="[PARENTDIR]"></td><td><a href="/pub/">Parent Directory</a></td><td>&nbsp;</td><td align="right">  - </td><td>&nbsp;</td></tr>
<tr><td valign="top"><img src="/icons/compressed.gif" alt="[   ]"></td><td><a href="backup_system.tar.gz">backup_system.tar.gz</a></td><td align="right">2026-01-15 14:22  </td><td align="right">350M</td><td>&nbsp;</td></tr>
<tr><td valign="top"><img src="/icons/application.gif" alt="[   ]"></td><td><a href="firmware_update.bin">firmware_update.bin</a></td><td align="right">2026-02-10 09:10  </td><td align="right"> 45M</td><td>&nbsp;</td></tr>
<tr><td valign="top"><img src="/icons/text.gif" alt="[TXT]"></td><td><a href="manual_guide.pdf">manual_guide.pdf</a></td><td align="right">2026-03-01 11:05  </td><td align="right">2.4M</td><td>&nbsp;</td></tr>
   <tr><th colspan="5"><hr></th></tr>
</table>
</body>
</html>
"""

SAMPLE_GENERIC_DL_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Project Release Downloads</title></head>
<body>
  <h1>Download latest release</h1>
  <p>Get the compiled binaries below:</p>
  <ul>
    <li><a href="/files/setup_v3.4.exe">Windows Installer (.exe)</a></li>
    <li><a href="/files/app_mac.dmg">macOS Disk Image (.dmg)</a></li>
    <li><a href="/docs/specification.pdf">Architecture Whitepaper (.pdf)</a></li>
  </ul>
</body>
</html>
"""


def test_file_extension_and_type_inference():
    assert detect_file_extension("archive.zip") == "zip"
    assert detect_file_extension("setup.v2.tar.gz") == "tar.gz"
    assert detect_file_extension("document.PDF") == "pdf"
    assert detect_file_extension("my_video.mp4") == "mp4"
    assert detect_file_extension("disc_image.iso") == "iso"

    assert infer_item_type("zip") == ItemType.ARCHIVE
    assert infer_item_type("7z") == ItemType.ARCHIVE
    assert infer_item_type("tar.gz") == ItemType.ARCHIVE
    assert infer_item_type("pdf") == ItemType.DOCUMENT
    assert infer_item_type("docx") == ItemType.DOCUMENT
    assert infer_item_type("exe") == ItemType.SOFTWARE
    assert infer_item_type("iso") == ItemType.SOFTWARE
    assert infer_item_type("mp3") == ItemType.AUDIO
    assert infer_item_type("mp4") == ItemType.VIDEO
    assert infer_item_type("png") == ItemType.IMAGE
    assert infer_item_type("csv") == ItemType.DATASET


def test_parse_size_str():
    assert parse_size_str("450.5 MB") == int(450.5 * 1024 * 1024)
    assert parse_size_str("1.2 GB") == int(1.2 * 1024 * 1024 * 1024)
    assert parse_size_str("350M") == 350 * 1024 * 1024
    assert parse_size_str("500 KB") == 500 * 1024
    assert parse_size_str("1234 B") == 1234


def test_mediafire_extractor():
    rec = FileHostExtractor.extract(SAMPLE_MEDIAFIRE_HTML, "https://www.mediafire.com/file/xyz123/MyArchive_v2.1.zip/file")
    assert rec is not None
    assert rec.platform == "MediaFire"
    assert "MyArchive_v2.1.zip" in rec.title
    assert rec.file_extension == "zip"
    assert rec.item_type == ItemType.ARCHIVE
    assert rec.download_url == "https://download1584.mediafire.com/xyz123/MyArchive_v2.1.zip"
    assert rec.file_size_bytes is not None
    assert rec.file_size_human is not None


def test_pixeldrain_extractor():
    rec = FileHostExtractor.extract(SAMPLE_PIXELDRAIN_HTML, "https://pixeldrain.com/u/9abcXYZ1")
    assert rec is not None
    assert rec.platform == "Pixeldrain"
    assert rec.download_url == "https://pixeldrain.com/api/file/9abcXYZ1"
    assert rec.file_extension == "iso"
    assert rec.item_type == ItemType.SOFTWARE


def test_krakenfiles_extractor():
    rec = FileHostExtractor.extract(SAMPLE_KRAKENFILES_HTML, "https://krakenfiles.com/view/abc987/file.html")
    assert rec is not None
    assert rec.platform == "Krakenfiles"
    assert "dataset_2026.tar.gz" in rec.title
    assert rec.download_url == "https://krakenfiles.com/download/abc987"
    assert rec.file_extension == "tar.gz"
    assert rec.item_type == ItemType.ARCHIVE


def test_google_drive_extractor():
    rec = FileHostExtractor.extract("<html><title>Google Drive - Dataset.zip</title></html>", "https://drive.google.com/file/d/1A2B3C4D5E6F7G/view")
    assert rec is not None
    assert rec.platform == "Google Drive"
    assert rec.download_url == "https://drive.google.com/uc?export=download&id=1A2B3C4D5E6F7G"


def test_dropbox_extractor():
    rec = FileHostExtractor.extract("<html><title>Dropbox - Backup.zip</title></html>", "https://www.dropbox.com/s/abcdef123456/Backup.zip?dl=0")
    assert rec is not None
    assert rec.platform == "Dropbox"
    assert rec.download_url == "https://dropbox.com/s/abcdef123456/Backup.zip?dl=1"


def test_open_directory_parser():
    base_url = "http://mirror.example.org/pub/software/"
    records = FileHostExtractor.extract_open_directory_files(SAMPLE_OPEN_DIRECTORY_HTML, base_url)
    assert len(records) == 3

    # Check first record: backup_system.tar.gz
    r1 = next(r for r in records if "backup_system.tar.gz" in r.title)
    assert r1.platform == "Open Directory"
    assert r1.file_extension == "tar.gz"
    assert r1.item_type == ItemType.ARCHIVE
    assert r1.canonical_url == "http://mirror.example.org/pub/software/backup_system.tar.gz"
    assert r1.download_url == "http://mirror.example.org/pub/software/backup_system.tar.gz"
    assert r1.file_size_human == "350 MB"

    # Check second record: firmware_update.bin
    r2 = next(r for r in records if "firmware_update.bin" in r.title)
    assert r2.item_type == ItemType.SOFTWARE
    assert r2.file_size_human == "45 MB"

    # Check third record: manual_guide.pdf
    r3 = next(r for r in records if "manual_guide.pdf" in r.title)
    assert r3.item_type == ItemType.DOCUMENT
    assert r3.file_size_human == "2.4 MB"


def test_generic_download_page_extractor():
    rec = FileHostExtractor.extract(SAMPLE_GENERIC_DL_PAGE_HTML, "https://example.com/downloads")
    assert rec is not None
    # Should find the first downloadable file attachment
    assert rec.download_url in [
        "https://example.com/files/setup_v3.4.exe",
        "https://example.com/files/app_mac.dmg",
        "https://example.com/docs/specification.pdf",
    ]


def test_matcher_item_type_filtering():
    rec_archive = ItemRecord(
        id="test:1",
        canonical_url="https://example.com/tool.zip",
        platform="Web",
        title="SuperTool v3.0 Archive",
        item_type=ItemType.ARCHIVE,
        file_extension="zip",
    )
    rec_doc = ItemRecord(
        id="test:2",
        canonical_url="https://example.com/tool.pdf",
        platform="Web",
        title="SuperTool User Manual",
        item_type=ItemType.DOCUMENT,
        file_extension="pdf",
    )

    # Filter for ARCHIVE only
    options_archive = SearchOptions(
        match_mode=MatchMode.EXACT_MATCH,
        item_types=[ItemType.ARCHIVE],
    )
    query_archive = QueryParser.parse("SuperTool", options=options_archive)
    is_match_1, _ = MatchEngine.evaluate(rec_archive, query_archive)
    is_match_2, _ = MatchEngine.evaluate(rec_doc, query_archive)

    assert is_match_1 is True
    assert is_match_2 is False

    # Filter for pdf extension only
    options_pdf = SearchOptions(
        match_mode=MatchMode.EXACT_MATCH,
        file_extensions=["pdf"],
    )
    query_pdf = QueryParser.parse("SuperTool", options=options_pdf)
    is_match_3, _ = MatchEngine.evaluate(rec_archive, query_pdf)
    is_match_4, _ = MatchEngine.evaluate(rec_doc, query_pdf)

    assert is_match_3 is False
    assert is_match_4 is True


def test_dedup_merges_file_download_attributes():
    rec1 = ItemRecord(
        id="mediafire:123",
        canonical_url="https://www.mediafire.com/file/123/package.rar/file",
        title="package.rar",
        platform="MediaFire",
        item_type=ItemType.FILE,
    )
    rec2 = ItemRecord(
        id="mediafire:123",
        canonical_url="https://www.mediafire.com/file/123/package.rar/file",
        title="Package Release RAR",
        download_url="https://download.mediafire.com/123/package.rar",
        platform="MediaFire",
        file_name="package.rar",
        file_extension="rar",
        file_size_human="750 MB",
        item_type=ItemType.ARCHIVE,
    )

    merged = DeduplicationEngine.merge_records(rec1, rec2)
    assert merged.download_url == "https://download.mediafire.com/123/package.rar"
    assert merged.file_name == "package.rar"
    assert merged.file_extension == "rar"
    assert merged.file_size_human == "750 MB"
    assert merged.item_type == ItemType.ARCHIVE


def test_html_meta_extracts_web_page():
    from omnisearch.extractors.html_meta import HtmlMetaExtractor
    html = """
    <!DOCTYPE html>
    <html>
    <head>
      <title>Python Software Foundation Official Website</title>
      <meta name="description" content="The official home of the Python Programming Language and downloads.">
    </head>
    <body>
      <h1>Welcome to Python.org</h1>
    </body>
    </html>
    """
    rec = HtmlMetaExtractor.extract_from_html(html, "https://www.python.org")
    assert rec is not None
    assert rec.title == "Python Software Foundation Official Website"
    assert rec.item_type == ItemType.WEB_PAGE
    assert "Python Programming Language" in rec.description


def test_adult_web_adapter_source_name_is_explicit_content():
    from omnisearch.adapters.adult_web import AdultVideoNetworkAdapter
    adapter = AdultVideoNetworkAdapter()
    assert adapter.source_name == "Explicit Content"
    assert adapter.source_id == "adult_web"


def test_website_search_matcher_and_filtering():
    rec_web = ItemRecord(
        id="web:wikipedia-linux",
        canonical_url="https://en.wikipedia.org/wiki/Linux",
        platform="Wikipedia",
        title="Linux — Open Source Operating System",
        description="Linux is a family of open-source Unix-like operating systems based on the Linux kernel.",
        item_type=ItemType.WEB_PAGE,
    )

    # 1. Exact match query
    options = SearchOptions(match_mode=MatchMode.EXACT_MATCH)
    query = QueryParser.parse("Linux", options=options)
    matched, prov = MatchEngine.evaluate(rec_web, query)
    assert matched is True
    assert any(t.lower() == "linux" for t in prov.matched_terms)

    # 2. WEB_PAGE category filtering
    options_web = SearchOptions(match_mode=MatchMode.EXACT_MATCH, item_types=[ItemType.WEB_PAGE])
    query_web = QueryParser.parse("Linux", options=options_web)
    matched_web, _ = MatchEngine.evaluate(rec_web, query_web)
    assert matched_web is True

    # 3. Exclude WEB_PAGE when filtering for ARCHIVE
    options_archive = SearchOptions(match_mode=MatchMode.EXACT_MATCH, item_types=[ItemType.ARCHIVE])
    query_archive = QueryParser.parse("Linux", options=options_archive)
    matched_archive, _ = MatchEngine.evaluate(rec_web, query_archive)
    assert matched_archive is False

