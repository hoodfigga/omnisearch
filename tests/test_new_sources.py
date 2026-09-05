"""
Unit tests for the v2.2 source adapters: GitHub, HuggingFace, Zenodo, arXiv,
OpenLibrary, Wikimedia Commons, Openverse, Nyaa, npm/crates.io registries.

These tests parse recorded fixture data (real API response shapes captured
2026-09-05) — no network access required.
"""

import json
import pytest

from omnisearch.models.query import SearchOptions
from omnisearch.core.query_parser import QueryParser
from omnisearch.adapters.github import GitHubAdapter
from omnisearch.adapters.huggingface import HuggingFaceAdapter
from omnisearch.adapters.academic import ZenodoAdapter, ArxivAdapter
from omnisearch.adapters.library_media import OpenLibraryAdapter, WikimediaCommonsAdapter
from omnisearch.adapters.openverse import OpenverseAdapter
from omnisearch.adapters.torrents import NyaaAdapter
from omnisearch.adapters.registries import RegistryAdapter
from omnisearch.extractors.file_hosts import parse_size_str


# --------------------------------------------------------------- fixtures

GITHUB_SEARCH_JSON = {
    "total_count": 52339,
    "items": [
        {
            "full_name": "BurntSushi/ripgrep",
            "html_url": "https://github.com/BurntSushi/ripgrep",
            "clone_url": "https://github.com/BurntSushi/ripgrep.git",
            "description": "ripgrep recursively searches directories for a regex pattern",
            "stargazers_count": 20007,
            "language": "Rust",
            "created_at": "2014-09-13T18:45:27Z",
            "owner": {"login": "BurntSushi", "html_url": "https://github.com/BurntSushi"},
            "topics": ["search", "grep"],
        }
    ],
}

GITHUB_RELEASE_JSON = {
    "html_url": "https://github.com/BurntSushi/ripgrep/releases/tag/14.1.0",
    "tag_name": "14.1.0",
    "published_at": "2024-09-01T00:00:00Z",
    "author": {"login": "BurntSushi"},
    "assets": [
        {
            "name": "ripgrep-14.1.0-x86_64-pc-windows-msvc.zip",
            "browser_download_url": "https://github.com/BurntSushi/ripgrep/releases/download/14.1.0/ripgrep-14.1.0-x86_64-pc-windows-msvc.zip",
            "size": 1751234,
        }
    ],
}

ZENODO_JSON = {
    "hits": {
        "hits": [
            {
                "id": 16537543,
                "created": "2026-01-15T00:00:00Z",
                "doi": "10.5281/zenodo.16537543",
                "metadata": {"title": "SYMBA D6.1 Report"},
                "files": [
                    {
                        "key": "report.pdf",
                        "size": 2202807,
                        "links": {"self": "https://zenodo.org/api/records/16537543/files/report.pdf/content"},
                    }
                ],
            }
        ]
    }
}

ARXIV_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <title>Attention Is All You Need</title>
    <summary>The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.</summary>
    <published>2017-06-12T17:57:34Z</published>
    <author><name>Ashish Vaswani</name></author>
  </entry>
</feed>"""

OPENLIBRARY_JSON = {
    "numFound": 2584,
    "docs": [
        {
            "title": "Dracula",
            "author_name": ["Bram Stoker"],
            "key": "/works/OL85892W",
            "ia": ["dracula00stok_8"],
            "ebook_access": "public",
            "first_publish_year": 1897,
            "cover_i": 8234563,
        },
        {
            "title": "Private Edition",
            "key": "/works/OL999W",
            "ebook_access": "no_ebook",
        },
    ],
}

COMMONS_JSON = {
    "query": {
        "pages": {
            "12345": {
                "pageid": 12345,
                "title": "File:Bela Lugosi as Dracula.jpg",
                "imageinfo": [
                    {
                        "url": "https://upload.wikimedia.org/wikipedia/commons/9/90/Bela_Lugosi_as_Dracula.jpg?utm_source=commons.wikimedia.org",
                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Bela_Lugosi_as_Dracula.jpg",
                        "size": 597101,
                        "mime": "image/jpeg",
                    }
                ],
            }
        }
    }
}

OPENVERSE_JSON = {
    "result_count": 2,
    "results": [
        {
            "id": "abc-123",
            "title": "Piano Jazz Singer",
            "url": "https://live.staticflickr.com/3146/2480058458.jpg",
            "creator": "John",
            "license": "CC-BY",
            "provider": "Flickr",
            "foreign_landing_url": "https://flickr.com/photo/123",
        }
    ],
}

NYAA_RSS = """<?xml version="1.0"?>
<rss xmlns:nyaa="https://nyaa.si/xmlns/nyaa" version="2.0">
  <channel>
    <item>
      <title>Koha Live CD Release 3</title>
      <link>https://nyaa.si/download/96659.torrent</link>
      <guid>https://nyaa.si/view/96659</guid>
      <pubDate>Tue, 03 Nov 2009 07:03:00 -0000</pubDate>
      <nyaa:seeders>5</nyaa:seeders>
      <nyaa:leechers>2</nyaa:leechers>
      <nyaa:downloads>100</nyaa:downloads>
      <nyaa:infoHash>45008e48c8800b7d7643337b2e70a634e4c69f6a</nyaa:infoHash>
      <nyaa:category>Software - Applications</nyaa:category>
      <nyaa:size>624.0 MiB</nyaa:size>
    </item>
  </channel>
</rss>"""

NPM_JSON = {
    "objects": [
        {
            "package": {
                "name": "express",
                "version": "5.2.1",
                "description": "Fast, unopinionated, minimalist web framework",
                "links": {"npm": "https://www.npmjs.com/package/express"},
                "author": {"name": "TJ Holowaychuk"},
            }
        }
    ]
}

CRATES_JSON = {
    "crates": [
        {
            "name": "serde",
            "description": "A generic serialization/deserialization framework",
            "downloads": 100000000,
            "max_stable_version": "1.0.200",
        }
    ]
}


# --------------------------------------------------------------- helpers

class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class _FakeClient:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def get(self, url, params=None, headers=None, timeout=None, safe_only=False, **kw):
        self.calls.append((url, params))
        for pattern, resp in self.routes:
            if pattern in url:
                return resp
        return _FakeResponse(status_code=404, json_data={})


def _patch_http(adapter, routes):
    client = _FakeClient(routes)
    adapter.http_client = client
    return client


# --------------------------------------------------------------- tests

def test_parse_size_str_mib():
    assert parse_size_str("624.0 MiB") == int(624.0 * 1024 * 1024)
    assert parse_size_str("1.5 GiB") == int(1.5 * 1024**3)
    assert parse_size_str("450.5 MB") == int(450.5 * 1024 * 1024)


@pytest.mark.asyncio
async def test_github_adapter_repos_and_releases():
    a = GitHubAdapter()
    _patch_http(a, [
        ("search/repositories", _FakeResponse(json_data=GITHUB_SEARCH_JSON)),
        ("releases/latest", _FakeResponse(json_data=GITHUB_RELEASE_JSON)),
    ])
    q = QueryParser.parse("ripgrep")
    recs = await a.search(q)
    assert len(recs) == 2  # 1 repo + 1 release asset
    repo = next(r for r in recs if r.id == "github:BurntSushi/ripgrep")
    assert repo.platform == "GitHub"
    assert repo.download_url == "https://github.com/BurntSushi/ripgrep.git"
    assert repo.view_count == 20007
    asset = next(r for r in recs if r.id.startswith("github_release:"))
    assert asset.download_url.endswith(".zip")
    assert asset.file_size_bytes == 1751234
    assert asset.item_type.value == "ARCHIVE"


@pytest.mark.asyncio
async def test_huggingface_adapter_models_and_datasets():
    a = HuggingFaceAdapter()
    _patch_http(a, [
        ("api/models", _FakeResponse(json_data=[
            {"id": "meta-llama/Llama-3.1-8B-Instruct", "downloads": 5738381, "likes": 6792, "pipeline_tag": "text-generation"}
        ])),
        ("api/datasets", _FakeResponse(json_data=[
            {"id": "ILSVRC/imagenet-1k", "downloads": 117008, "likes": 894}
        ])),
    ])
    q = QueryParser.parse("llama")
    recs = await a.search(q)
    assert len(recs) == 2
    model = next(r for r in recs if r.id.startswith("hf_model:"))
    ds = next(r for r in recs if r.id.startswith("hf_dataset:"))
    assert model.item_type.value == "SOFTWARE"
    assert ds.item_type.value == "DATASET"
    assert model.view_count == 5738381


@pytest.mark.asyncio
async def test_zenodo_adapter_files_with_direct_links():
    a = ZenodoAdapter()
    _patch_http(a, [("api/records", _FakeResponse(json_data=ZENODO_JSON))])
    q = QueryParser.parse("climate data")
    recs = await a.search(q)
    assert len(recs) == 1
    r = recs[0]
    assert r.download_url == "https://zenodo.org/api/records/16537543/files/report.pdf/content"
    assert r.file_size_bytes == 2202807
    assert r.platform == "Zenodo"


@pytest.mark.asyncio
async def test_arxiv_adapter_parses_atom():
    recs = ArxivAdapter._parse_atom(ARXIV_ATOM)
    assert len(recs) == 1
    r = recs[0]
    assert r.title == "Attention Is All You Need"
    assert r.download_url == "http://arxiv.org/pdf/1706.03762v7"
    assert r.file_extension == "pdf"
    assert r.uploader_name == "Ashish Vaswani"


@pytest.mark.asyncio
async def test_openlibrary_adapter_public_ebooks():
    a = OpenLibraryAdapter()
    _patch_http(a, [("search.json", _FakeResponse(json_data=OPENLIBRARY_JSON))])
    q = QueryParser.parse("dracula")
    recs = await a.search(q)
    assert len(recs) == 2
    public = next(r for r in recs if "Dracula" == r.title)
    assert public.download_url == "https://archive.org/download/dracula00stok_8/dracula00stok_8.pdf"
    private = next(r for r in recs if r.title == "Private Edition")
    assert private.download_url is None


@pytest.mark.asyncio
async def test_commons_adapter_direct_upload_urls():
    a = WikimediaCommonsAdapter()
    _patch_http(a, [("api.php", _FakeResponse(json_data=COMMONS_JSON))])
    q = QueryParser.parse("dracula")
    recs = await a.search(q)
    assert len(recs) == 1
    r = recs[0]
    # utm tracking params stripped
    assert r.download_url == "https://upload.wikimedia.org/wikipedia/commons/9/90/Bela_Lugosi_as_Dracula.jpg"
    assert r.item_type.value == "IMAGE"
    assert r.file_size_bytes == 597101


@pytest.mark.asyncio
async def test_openverse_adapter_image_and_audio():
    a = OpenverseAdapter()
    _patch_http(a, [
        ("v1/images", _FakeResponse(json_data=OPENVERSE_JSON)),
        ("v1/audio", _FakeResponse(json_data={"results": [
            {"id": "aud-1", "title": "Piano Solo", "url": "https://jamendo.com/a.mp3", "creator": "Jane", "license": "CC0", "duration": 240, "provider": "Jamendo"}
        ]})),
    ])
    q = QueryParser.parse("piano jazz")
    recs = await a.search(q)
    assert len(recs) == 2
    img = next(r for r in recs if r.id.startswith("openverse_image:"))
    aud = next(r for r in recs if r.id.startswith("openverse_audio:"))
    assert img.item_type.value == "IMAGE"
    assert aud.item_type.value == "AUDIO"
    assert aud.duration_seconds == 240


@pytest.mark.asyncio
async def test_nyaa_adapter_parses_rss(monkeypatch):
    monkeypatch.delenv("OMNISEARCH_ADULT_ENABLED", raising=False)
    a = NyaaAdapter()
    recs = a._parse_feed(NYAA_RSS, "Nyaa")
    assert len(recs) == 1
    r = recs[0]
    assert r.download_url == "https://nyaa.si/download/96659.torrent"
    assert r.file_extension == "torrent"
    assert r.file_size_bytes == int(624.0 * 1024 * 1024)
    assert r.view_count == 100
    assert r.like_count == 5  # seeders
    assert "45008e48c880" in r.description


@pytest.mark.asyncio
async def test_registry_adapter_npm_and_crates():
    a = RegistryAdapter()
    _patch_http(a, [
        ("registry.npmjs.org", _FakeResponse(json_data=NPM_JSON)),
        ("crates.io", _FakeResponse(json_data=CRATES_JSON)),
    ])
    q = QueryParser.parse("web framework")
    recs = await a.search(q)
    assert len(recs) == 2
    npm = next(r for r in recs if r.platform == "npm")
    crate = next(r for r in recs if r.platform == "crates.io")
    assert npm.download_url == "https://registry.npmjs.org/express/-/express-5.2.1.tgz"
    assert npm.item_type.value == "SOFTWARE"
    assert crate.download_url == "https://crates.io/api/v1/crates/serde/1.0.200/download"
    assert crate.file_extension == "crate"


@pytest.mark.asyncio
async def test_orchestrator_registers_new_adapters():
    from omnisearch.core.orchestrator import VideoDiscoveryOrchestrator

    orch = VideoDiscoveryOrchestrator(adapters=[])  # empty to avoid default net-touching adapters
    # Verify the default adapter list includes all new source ids
    from omnisearch.adapters.github import GitHubAdapter
    from omnisearch.adapters.huggingface import HuggingFaceAdapter
    from omnisearch.adapters.academic import ZenodoAdapter, ArxivAdapter
    from omnisearch.adapters.library_media import OpenLibraryAdapter, WikimediaCommonsAdapter
    from omnisearch.adapters.openverse import OpenverseAdapter
    from omnisearch.adapters.torrents import NyaaAdapter
    from omnisearch.adapters.registries import RegistryAdapter

    orch2 = VideoDiscoveryOrchestrator(adapters=[
        GitHubAdapter(), HuggingFaceAdapter(), ZenodoAdapter(), ArxivAdapter(),
        OpenLibraryAdapter(), WikimediaCommonsAdapter(), OpenverseAdapter(),
        NyaaAdapter(), RegistryAdapter(),
    ])
    ids = {a.source_id for a in orch2.adapters.values()}
    assert ids == {"github", "huggingface", "zenodo", "arxiv", "openlibrary", "commons", "openverse", "nyaa", "registries"}
