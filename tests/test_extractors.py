"""
Tests for structured metadata extractors: JSON-LD, OpenGraph, HTML Meta, oEmbed, and MediaRSS.
"""

from omnisearch.extractors.json_ld import JsonLdExtractor
from omnisearch.extractors.opengraph import OpenGraphExtractor
from omnisearch.extractors.html_meta import HtmlMetaExtractor
from omnisearch.extractors.oembed import OEmbedExtractor
from omnisearch.extractors.page_extractor import PageExtractor
from omnisearch.adapters.mrss import MRSSAdapter


SAMPLE_JSON_LD_HTML = """
<!DOCTYPE html>
<html>
<head>
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "VideoObject",
    "name": "Introduction to Quantum Computing",
    "description": "Learn qubits, superposition, and quantum gates.",
    "thumbnailUrl": "https://example.com/thumb.jpg",
    "uploadDate": "2024-01-15T08:00:00Z",
    "duration": "PT15M33S",
    "embedUrl": "https://example.com/embed/quantum101",
    "keywords": "quantum, computing, physics, qubit",
    "author": {
      "@type": "Person",
      "name": "Dr. Alice Smith"
    }
  }
  </script>
</head>
<body></body>
</html>
"""

SAMPLE_OPENGRAPH_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta property="og:type" content="video.other" />
  <meta property="og:title" content="Deep Space Exploration Documentary" />
  <meta property="og:description" content="Exploring galaxies beyond the Milky Way." />
  <meta property="og:video" content="https://example.com/videos/space.mp4" />
  <meta property="og:image" content="https://example.com/space_poster.jpg" />
  <meta property="og:site_name" content="SpaceCinema" />
  <meta property="video:duration" content="3600" />
  <meta property="video:tag" content="astronomy" />
  <meta property="video:tag" content="documentary" />
</head>
<body></body>
</html>
"""

SAMPLE_MRSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>Science Webcasts</title>
    <item>
      <title>Mars Rover Mission Update</title>
      <link>https://example.com/mars-rover</link>
      <description>Latest findings from the Jezero crater.</description>
      <media:thumbnail url="https://example.com/mars_thumb.jpg"/>
      <media:content url="https://example.com/mars_video.mp4" duration="720"/>
      <media:keywords>mars, rover, nasa, space</media:keywords>
    </item>
  </channel>
</rss>
"""


def test_json_ld_extractor():
    records = JsonLdExtractor.extract_from_html(SAMPLE_JSON_LD_HTML, "https://example.com/quantum")
    assert len(records) == 1
    rec = records[0]
    assert rec.title == "Introduction to Quantum Computing"
    assert rec.duration_seconds == 933  # 15*60 + 33
    assert rec.uploader_name == "Dr. Alice Smith"
    assert "qubit" in rec.tags
    assert rec.embed_url == "https://example.com/embed/quantum101"


def test_opengraph_extractor():
    rec = OpenGraphExtractor.extract_from_html(SAMPLE_OPENGRAPH_HTML, "https://example.com/doc")
    assert rec is not None
    assert rec.title == "Deep Space Exploration Documentary"
    assert rec.duration_seconds == 3600
    assert rec.platform == "SpaceCinema"
    assert "astronomy" in rec.tags


def test_mrss_adapter_parser():
    records = MRSSAdapter.parse_feed(SAMPLE_MRSS_XML, "https://example.com/feed.xml")
    assert len(records) == 1
    rec = records[0]
    assert rec.title == "Mars Rover Mission Update"
    assert rec.duration_seconds == 720
    assert "nasa" in rec.tags


def test_page_extractor_merges_multiple_sources():
    combined_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <title>Documentary Channel</title>
      {SAMPLE_JSON_LD_HTML}
      {SAMPLE_OPENGRAPH_HTML}
    </head>
    <body></body>
    </html>
    """
    records = PageExtractor.extract_from_html(combined_html, "https://example.com/watch")
    assert len(records) >= 1
    first = records[0]
    assert first.title != ""
