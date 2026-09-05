"""
Tests for File Hosting / Cyberlocker Extractor and Adapter (Bunkr, Pixeldrain, Tmpfiles, etc.).
"""

import pytest
from bs4 import BeautifulSoup
from omnisearch.extractors.file_hosts import FileHostExtractor
from omnisearch.extractors.page_extractor import PageExtractor
from omnisearch.adapters.file_hosts import FileHostingAdapter


SAMPLE_BUNKR_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>Bunkr - Exclusive Video Clip 1080p</title>
</head>
<body>
  <h1>Exclusive Video Clip 1080p</h1>
  <video src="https://media-files.bunkr.is/videos/clip1080p.mp4" poster="https://media-files.bunkr.is/thumbs/clip1080p.jpg"></video>
</body>
</html>
"""

SAMPLE_TMPFILES_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>tmpfiles.org - sample_record.mp4</title>
</head>
<body>
  <h1>Uploaded Video File</h1>
  <video src="https://tmpfiles.org/dl/12345/sample_record.mp4"></video>
  <a href="https://tmpfiles.org/dl/12345/sample_record.mp4">Download</a>
</body>
</html>
"""


def test_bunkr_extraction():
    rec = FileHostExtractor.extract(SAMPLE_BUNKR_HTML, "https://bunkr.is/v/clip1080p")
    assert rec is not None
    assert rec.platform == "Bunkr"
    assert "Exclusive Video Clip" in rec.title
    assert rec.embed_url == "https://media-files.bunkr.is/videos/clip1080p.mp4"
    assert rec.thumbnail_url == "https://media-files.bunkr.is/thumbs/clip1080p.jpg"
    assert "file-host" in rec.tags


def test_tmpfiles_extraction():
    rec = FileHostExtractor.extract(SAMPLE_TMPFILES_HTML, "https://tmpfiles.org/12345/sample_record.mp4")
    assert rec is not None
    assert rec.platform == "Tmpfiles"
    assert "sample_record.mp4" in rec.title
    assert "https://tmpfiles.org/dl/12345/sample_record.mp4" in rec.download_url
    assert "https://tmpfiles.org/dl/12345/sample_record.mp4" in rec.embed_url


def test_page_extractor_dispatches_file_hosts():
    records = PageExtractor.extract_from_html(SAMPLE_BUNKR_HTML, "https://bunkr.cr/d/video123")
    assert len(records) >= 1
    assert records[0].platform == "Bunkr"


def test_file_hosting_adapter_properties():
    adapter = FileHostingAdapter()
    assert adapter.source_id == "file_hosts"
    assert "File Hosts" in adapter.source_name
    assert adapter.is_enabled is True
