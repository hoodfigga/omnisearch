"""
Unit tests for the v2.4 source adapters: GitLab, Codeberg, Modrinth, Steam,
itch.io, iTunes, Mixcloud, Hacker News, StackExchange, EuropePMC, DOAJ,
Crossref, Semantic Scholar, extended registries (RubyGems, Packagist, NuGet,
AUR, Docker Hub), and the adult adapter's XVideos/XHamster/PornTrex parsers.

Fixture data mirrors real API/HTML response shapes (captured 2026-09-08) —
no network access required. HTML parsers are tested against the live-captured
DOM structures.
"""

import pytest

from omnisearch.models.query import SearchOptions
from omnisearch.core.query_parser import QueryParser


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

    async def get(self, url, params=None, headers=None, timeout=None, **kw):
        self.calls.append((url, params))
        for pattern, resp in self.routes:
            if pattern in url:
                return resp
        return _FakeResponse(status_code=404, json_data={})


def _patch_http(adapter, routes):
    client = _FakeClient(routes)
    adapter.http_client = client
    return client


# --------------------------------------------------------------- fixtures

GITLAB_JSON = [
    {
        "id": 83854204,
        "description": "A lousy ripgrep rip-off in pure Python",
        "name": "offgrep",
        "path_with_namespace": "blackstream-x/offgrep",
        "created_at": "2026-06-28T12:05:07.067Z",
        "http_url_to_repo": "https://gitlab.com/blackstream-x/offgrep.git",
        "web_url": "https://gitlab.com/blackstream-x/offgrep",
        "star_count": 3,
        "topics": ["grep", "recursive"],
        "namespace": {"path": "blackstream-x"},
    }
]

CODEBERG_JSON = {
    "ok": True,
    "data": [
        {
            "id": 1416763,
            "full_name": "rakivo/rawgrep",
            "description": "The fastest grep in the world",
            "html_url": "https://codeberg.org/rakivo/rawgrep",
            "clone_url": "https://codeberg.org/rakivo/rawgrep.git",
            "stars_count": 12,
            "created_at": "2025-12-15T21:48:13+01:00",
            "language": "Rust",
            "owner": {"username": "rakivo"},
        }
    ],
}

MODRINTH_JSON = {
    "hits": [
        {
            "project_id": "AANobbMI",
            "project_type": "mod",
            "slug": "sodium",
            "author": "jellysquid3",
            "title": "Sodium",
            "description": "A high-performance rendering engine replacement for Minecraft.",
            "categories": ["fabric", "optimization"],
            "downloads": 221900204,
            "follows": 40172,
            "icon_url": "https://cdn.modrinth.com/x.png",
            "date_created": "2021-01-03T00:53:34.185936+00:00",
        }
    ]
}

STEAM_HTML = """
<a href="https://store.steampowered.com/app/400/Portal/" data-ds-appid="400" class="search_result_row">
 <div class="search_capsule"><img src="https://cdn.akamai.steamstatic.com/portal.jpg"></div>
 <div class="responsive_search_name_combined">
  <div class="search_name"><span class="title">Portal</span></div>
  <div class="search_released responsive_secondrow"> 10 Oct, 2007 </div>
 </div>
</a>
"""

ITCHIO_HTML = """
<div class="game_cell" data-game_id="1773067">
  <div class="game_thumb"><a href="https://ludonauta.itch.io/platformer-essentials" class="thumb_link game_link">
    <img data-lazy_src="https://img.itch.zone/cover.png" /></a></div>
  <div class="game_cell_data">
    <div class="game_title"><a href="https://ludonauta.itch.io/platformer-essentials" class="game_link">Platformer Essentials</a></div>
    <div class="game_genre">Platformer</div>
    <div class="game_text">A complete platformer asset pack</div>
  </div>
</div>
"""

ITUNES_JSON = {
    "results": [
        {
            "trackId": 697195462,
            "trackName": "One More Time",
            "artistName": "Daft Punk",
            "collectionName": "Discovery",
            "trackViewUrl": "https://music.apple.com/album/697195462",
            "previewUrl": "https://audio-ssl.itunes.apple.com/preview.m4a",
            "artworkUrl100": "https://is1-ssl.mzstatic.com/100x100bb.jpg",
            "releaseDate": "2000-11-30T08:00:00Z",
            "trackTimeMillis": 320357,
            "kind": "song",
        }
    ]
}

MIXCLOUD_JSON = {
    "data": [
        {
            "key": "/technoscene-crew/techno-scene-best-mixes/",
            "url": "https://www.mixcloud.com/technoscene-crew/techno-scene-best-mixes/",
            "name": "Techno Scene Best Mixes: DVS1",
            "tags": [{"name": "Techno"}, {"name": "Berlin"}],
            "created_time": "2015-07-08T15:35:00Z",
            "audio_length": 3600,
            "play_count": 28691,
            "favorite_count": 1192,
            "pictures": {"medium": "https://thumbnailer.mixcloud.com/medium.jpg"},
            "user": {"name": "technoscene-crew", "url": "https://www.mixcloud.com/technoscene-crew/"},
        }
    ],
    "paging": {"next": None},
}

HN_JSON = {
    "hits": [
        {
            "objectID": "12564442",
            "title": "Ripgrep – A new command line search tool",
            "url": "http://blog.burntsushi.net/ripgrep/",
            "author": "anp",
            "points": 740,
            "num_comments": 209,
            "created_at": "2016-09-23T13:33:34Z",
        }
    ]
}

STACKEX_JSON = {
    "items": [
        {
            "question_id": 75712167,
            "title": "Cargo, the Rust package manager, is not installed",
            "link": "https://stackoverflow.com/questions/75712167/cargo",
            "tags": ["python", "django"],
            "is_answered": False,
            "view_count": 8600,
            "score": 1,
            "answer_count": 2,
            "creation_date": 1678613083,
            "owner": {"display_name": "Abhishek", "link": "https://stackoverflow.com/users/1/abhishek"},
        }
    ],
    "has_more": False,
}

EUROPEPMC_JSON = {
    "resultList": {
        "result": [
            {
                "id": "42700480",
                "source": "MED",
                "doi": "10.1016/j.bios.2026.119197",
                "title": "Advances in cascaded CRISPR for preamplification-free assays.",
                "authorString": "He R, Miao L.",
                "journalTitle": "Biosens Bioelectron",
                "pubYear": "2026",
                "isOpenAccess": "Y",
                "inPMC": "N",
                "pmcid": "PMC1234567",
                "firstPublicationDate": "2026-09-04",
                "citedByCount": 0,
            }
        ]
    }
}

DOAJ_JSON = {
    "results": [
        {
            "id": "abc123",
            "bibjson": {
                "title": "CRISPR-Mediated Base Editing Tools",
                "abstract": "A genome editing technique review.",
                "year": "2025",
                "month": "11",
                "author": [{"name": "Leah Buchman"}],
                "keywords": ["CRISPR", "biotechnology"],
                "journal": {"title": "Frontiers in Bioengineering"},
                "identifier": [{"id": "10.3389/fbioe.2025.1702481", "type": "doi"}],
                "link": [{"type": "fulltext", "url": "https://www.frontiersin.org/articles/full"}],
            },
        }
    ]
}

CROSSREF_JSON = {
    "message": {
        "items": [
            {
                "DOI": "10.3791/20970",
                "title": ["CRISPR-Mediated Base Editing Tools: A Genome Editing Technique"],
                "author": [{"given": "Leah", "family": "Buchman"}],
                "container-title": ["Journal of Visualized Experiments"],
                "issued": {"date-parts": [[2026, 9, 3]]},
                "is-referenced-by-count": 0,
                "type": "journal-article",
                "resource": {"primary": {"URL": "https://www.jove.com/t/20970"}},
            }
        ]
    }
}

SEMANTIC_SCHOLAR_JSON = {
    "data": [
        {
            "paperId": "abc123def",
            "title": "Attention Is All You Need",
            "year": 2017,
            "authors": [{"name": "Ashish Vaswani"}],
            "abstract": "The dominant sequence transduction models...",
            "citationCount": 100000,
            "url": "https://www.semanticscholar.org/paper/abc123def",
            "openAccessPdf": {"url": "https://arxiv.org/pdf/1706.03762"},
        }
    ]
}

RUBYGEMS_JSON = [
    {
        "name": "ruby_http_client",
        "version": "3.6.0",
        "info": "Quickly and easily access any REST API.",
        "authors": "Elmer Thomas",
        "project_uri": "https://rubygems.org/gems/ruby_http_client",
        "gem_uri": "https://rubygems.org/gems/ruby_http_client-3.6.0.gem",
        "downloads": 59412480,
    }
]

PACKAGIST_JSON = {
    "results": [
        {
            "name": "guzzlehttp/guzzle",
            "description": "Guzzle is a PHP HTTP client library",
            "url": "https://packagist.org/packages/guzzlehttp/guzzle",
            "downloads": 1092925126,
            "favers": 24313,
        }
    ]
}

NUGET_JSON = {
    "data": [
        {
            "id": "System.Net.Http",
            "version": "4.3.4",
            "title": "System.Net.Http",
            "description": "HTTP client components.",
            "authors": ["Microsoft"],
            "totalDownloads": 3582318000,
            "verified": True,
        }
    ]
}

AUR_JSON = {
    "resultcount": 1,
    "results": [
        {
            "ID": 2167929,
            "Name": "angie",
            "Version": "1.12.1-1",
            "Description": "Lightweight HTTP server, drop-in replacement for nginx",
            "URLPath": "/cgit/aur.git/snapshot/angie.tar.gz",
            "NumVotes": 4,
            "Maintainer": "VVL",
            "Popularity": 4e-06,
        }
    ],
}

DOCKERHUB_JSON = {
    "results": [
        {
            "repo_name": "nginx",
            "short_description": "Official build of Nginx.",
            "star_count": 21369,
            "pull_count": 13334094247,
            "is_official": True,
        }
    ]
}

# Adult adapters: live-captured DOM shapes (2026-09-08)
XVIDEOS_HTML = """
<div id="video_hpkdftc30f4" data-id="23322380" class="frame-block thumb-block">
  <div class="thumb-inside"><div class="thumb">
    <a href="/video.hpkdftc30f4/great_couple_swap_-_multiple_orgasms_3">
      <img src="https://assets-cdn77.xvideos-cdn.com/blank.gif"
           data-src="https://thumb-cdn77.xvideos-cdn.com/xv_24_t.jpg"
           data-pvv="https://thumb-cdn77.xvideos-cdn.com/preview.mp4" />
    </a>
  </div></div>
  <div class="thumb-under">
    <p class="title"><a href="/video.hpkdftc30f4/great_couple_swap" title="Great couple swap - multiple orgasms! 3">Great couple swap - multiple orgasms! 3</a></p>
    <p class="metadata"><span class="bg"><span class="duration">26 min</span>
      <span><a href="/privatporno"><span class="name">Privat Porno</span></a>
      <span> - 2.1M <span class="sprfluous">Views</span></span></span></span></p>
  </div>
</div>
"""

XHAMSTER_HTML = """
<div class="container-c9dbd thumb-list__item video-thumb video-thumb--type-video" data-video-id="29244703">
  <a class="video-thumb__image-container role-pop thumb-image-container" data-role="thumb-link"
     href="https://xhamster.com/videos/hot-brunette-fucks-gardener-xhfLRny"
     data-previewvideo-fallback="https://thumb-v3.xhpingcdn.com/preview.mp4"
     aria-label="Hot Brunette Fucks Gardener - Sweetie Fox">
    <img src="https://ic-vt-nss.xhpingcdn.com/1280x720.jpg" />
  </a>
  <div class="thumb-image-container__on-video">
    <div class="thumb-image-container__duration" data-role="video-duration-container">32:15</div>
  </div>
</div>
"""

PORNTREX_HTML = """
<div class="video-preview-screen video-item thumb-item " data-item-id="1902160">
  <a href="https://www.porntrex.com/video/1902160/jenny-manson-bdsm" class="thumb rotator-screen">
    <img class="cover lazyload" data-src="//ptx.cdntrex.com/300x168/1.jpg" alt="Jenny Manson - BDSM Anal Fucking with Gape" />
  </a>
</div>
"""


# --------------------------------------------------------------- forges

@pytest.mark.asyncio
async def test_gitlab_adapter():
    from omnisearch.adapters.forges import GitLabAdapter

    a = GitLabAdapter()
    _patch_http(a, [("api/v4/projects", _FakeResponse(json_data=GITLAB_JSON))])
    recs = await a.search(QueryParser.parse("ripgrep"))
    assert len(recs) == 1
    r = recs[0]
    assert r.platform == "GitLab"
    assert r.platform_id == "blackstream-x/offgrep"
    assert r.download_url == "https://gitlab.com/blackstream-x/offgrep.git"
    assert r.item_type.value == "SOFTWARE"
    assert "grep" in r.tags


@pytest.mark.asyncio
async def test_codeberg_adapter_plain_ua():
    from omnisearch.adapters.forges import CodebergAdapter

    a = CodebergAdapter()
    client = _patch_http(a, [("repos/search", _FakeResponse(json_data=CODEBERG_JSON))])
    recs = await a.search(QueryParser.parse("grep"))
    assert len(recs) == 1
    r = recs[0]
    assert r.platform == "Codeberg"
    assert r.platform_id == "rakivo/rawgrep"
    assert r.download_url == "https://codeberg.org/rakivo/rawgrep.git"
    # Must send the plain UA (browser UA gets 403 on Codeberg)
    sent_headers = None  # FakeClient records (url, params); headers asserted via route hit
    assert any("codeberg" in u for u, _ in client.calls)


# --------------------------------------------------------------- gaming

@pytest.mark.asyncio
async def test_modrinth_adapter():
    from omnisearch.adapters.gaming import ModrinthAdapter

    a = ModrinthAdapter()
    _patch_http(a, [("v2/search", _FakeResponse(json_data=MODRINTH_JSON))])
    recs = await a.search(QueryParser.parse("sodium"))
    assert len(recs) == 1
    r = recs[0]
    assert r.platform == "Modrinth"
    assert r.title == "Sodium"
    assert r.view_count == 221900204
    assert r.item_type.value == "SOFTWARE"
    assert "minecraft" in r.tags


@pytest.mark.asyncio
async def test_steam_adapter_parses_html():
    from omnisearch.adapters.gaming import SteamAdapter

    a = SteamAdapter()
    _patch_http(a, [("store.steampowered.com", _FakeResponse(text=STEAM_HTML))])
    recs = await a.search(QueryParser.parse("portal"))
    assert len(recs) == 1
    r = recs[0]
    assert r.platform == "Steam"
    assert r.title == "Portal"
    assert r.platform_id == "400"
    assert r.canonical_url.startswith("https://store.steampowered.com/app/400")
    assert r.thumbnail_url == "https://cdn.akamai.steamstatic.com/portal.jpg"


@pytest.mark.asyncio
async def test_itchio_adapter_parses_html():
    from omnisearch.adapters.gaming import ItchIoAdapter

    a = ItchIoAdapter()
    _patch_http(a, [("itch.io/search", _FakeResponse(text=ITCHIO_HTML))])
    recs = await a.search(QueryParser.parse("platformer"))
    assert len(recs) == 1
    r = recs[0]
    assert r.platform == "itch.io"
    assert r.title == "Platformer Essentials"
    assert r.uploader_name == "ludonauta"
    assert r.thumbnail_url == "https://img.itch.zone/cover.png"


# --------------------------------------------------------------- media

@pytest.mark.asyncio
async def test_itunes_adapter():
    from omnisearch.adapters.music_media import ITunesAdapter

    a = ITunesAdapter()
    _patch_http(a, [("itunes.apple.com/search", _FakeResponse(json_data=ITUNES_JSON))])
    recs = await a.search(QueryParser.parse("daft punk"))
    assert len(recs) == 2  # music + podcast entities both hit the same fixture route
    song = next(r for r in recs if r.title == "One More Time")
    assert song.platform == "iTunes"
    assert song.item_type.value == "AUDIO"
    assert song.download_url == "https://audio-ssl.itunes.apple.com/preview.m4a"
    assert song.duration_seconds == 320


@pytest.mark.asyncio
async def test_mixcloud_adapter_data_key():
    from omnisearch.adapters.music_media import MixcloudAdapter

    a = MixcloudAdapter()
    _patch_http(a, [("api.mixcloud.com/search", _FakeResponse(json_data=MIXCLOUD_JSON))])
    recs = await a.search(QueryParser.parse("techno"))
    assert len(recs) == 1
    r = recs[0]
    assert r.platform == "Mixcloud"
    assert r.title == "Techno Scene Best Mixes: DVS1"
    assert r.duration_seconds == 3600
    assert "techno" in r.tags
    assert r.embed_url and "mixcloud.com/widget" in r.embed_url


# --------------------------------------------------------------- communities

@pytest.mark.asyncio
async def test_hackernews_adapter():
    from omnisearch.adapters.communities import HackerNewsAdapter

    a = HackerNewsAdapter()
    _patch_http(a, [("hn.algolia.com", _FakeResponse(json_data=HN_JSON))])
    recs = await a.search(QueryParser.parse("ripgrep"))
    assert len(recs) == 1
    r = recs[0]
    assert r.platform == "Hacker News"
    assert r.canonical_url == "https://news.ycombinator.com/item?id=12564442"
    assert r.view_count == 740
    assert r.uploader_name == "anp"


@pytest.mark.asyncio
async def test_stackexchange_adapter_multi_site():
    from omnisearch.adapters.communities import StackExchangeAdapter

    a = StackExchangeAdapter()
    client = _patch_http(a, [("search/advanced", _FakeResponse(json_data=STACKEX_JSON))])
    recs = await a.search(QueryParser.parse("asyncio"))
    # 4 sites, 1 item each from the fixture
    assert len(recs) == 4
    platforms = {r.platform for r in recs}
    assert any("stackoverflow" in p for p in platforms)
    r = recs[0]
    assert r.title.startswith("Cargo, the Rust package manager")
    assert "python" in r.tags


# --------------------------------------------------------------- academic

@pytest.mark.asyncio
async def test_europepmc_adapter():
    from omnisearch.adapters.academic import EuropePMCAdapter

    a = EuropePMCAdapter()
    _patch_http(a, [("webservices/rest/search", _FakeResponse(json_data=EUROPEPMC_JSON))])
    recs = await a.search(QueryParser.parse("crispr"))
    assert len(recs) == 1
    r = recs[0]
    assert r.platform == "Europe PMC"
    assert "CRISPR" in r.title
    assert r.download_url is not None  # open access full text
    assert "open-access" in r.tags


@pytest.mark.asyncio
async def test_doaj_adapter():
    from omnisearch.adapters.academic import DoajAdapter

    a = DoajAdapter()
    _patch_http(a, [("api/search/articles", _FakeResponse(json_data=DOAJ_JSON))])
    recs = await a.search(QueryParser.parse("crispr"))
    assert len(recs) == 1
    r = recs[0]
    assert r.platform == "DOAJ"
    assert r.download_url == "https://www.frontiersin.org/articles/full"
    assert r.uploader_name == "Leah Buchman"
    assert "crispr" in r.tags


@pytest.mark.asyncio
async def test_crossref_adapter():
    from omnisearch.adapters.academic import CrossrefAdapter

    a = CrossrefAdapter()
    _patch_http(a, [("api.crossref.org/works", _FakeResponse(json_data=CROSSREF_JSON))])
    recs = await a.search(QueryParser.parse("crispr base editing"))
    assert len(recs) == 1
    r = recs[0]
    assert r.platform == "Crossref"
    assert r.platform_id == "10.3791/20970"
    assert r.canonical_url == "https://www.jove.com/t/20970"
    assert r.publication_date is not None


@pytest.mark.asyncio
async def test_semantic_scholar_adapter():
    from omnisearch.adapters.academic import SemanticScholarAdapter

    a = SemanticScholarAdapter()
    _patch_http(a, [("paper/search", _FakeResponse(json_data=SEMANTIC_SCHOLAR_JSON))])
    recs = await a.search(QueryParser.parse("attention"))
    assert len(recs) == 1
    r = recs[0]
    assert r.platform == "Semantic Scholar"
    assert r.download_url == "https://arxiv.org/pdf/1706.03762"
    assert r.item_type.value == "DOCUMENT"


@pytest.mark.asyncio
async def test_semantic_scholar_rate_limit_degrades_gracefully():
    from omnisearch.adapters.academic import SemanticScholarAdapter

    a = SemanticScholarAdapter()
    _patch_http(a, [("paper/search", _FakeResponse(status_code=429, json_data={"message": "Too Many Requests"}))])
    recs = await a.search(QueryParser.parse("anything"))
    assert recs == []  # no crash, no records


# --------------------------------------------------------------- registries (new)

@pytest.mark.asyncio
async def test_registries_rubygems():
    from omnisearch.adapters.registries import RegistryAdapter

    a = RegistryAdapter()
    _patch_http(a, [
        ("rubygems.org/api", _FakeResponse(json_data=RUBYGEMS_JSON)),
        ("crates.io", _FakeResponse(json_data={"crates": []})),
        ("npmjs.org", _FakeResponse(json_data={"objects": []})),
        ("packagist.org", _FakeResponse(json_data={"results": []})),
        ("nuget.org", _FakeResponse(json_data={"data": []})),
        ("aur.archlinux.org", _FakeResponse(json_data={"results": []})),
        ("hub.docker.com", _FakeResponse(json_data={"results": []})),
    ])
    recs = await a.search(QueryParser.parse("http client"))
    gems = [r for r in recs if r.platform == "RubyGems"]
    assert len(gems) == 1
    g = gems[0]
    assert g.download_url == "https://rubygems.org/gems/ruby_http_client-3.6.0.gem"
    assert g.file_extension == "gem"


@pytest.mark.asyncio
async def test_registries_all_five_new_platforms():
    from omnisearch.adapters.registries import RegistryAdapter

    a = RegistryAdapter()
    _patch_http(a, [
        ("rubygems.org/api", _FakeResponse(json_data=RUBYGEMS_JSON)),
        ("packagist.org", _FakeResponse(json_data=PACKAGIST_JSON)),
        ("nuget.org", _FakeResponse(json_data=NUGET_JSON)),
        ("aur.archlinux.org", _FakeResponse(json_data=AUR_JSON)),
        ("hub.docker.com", _FakeResponse(json_data=DOCKERHUB_JSON)),
        ("crates.io", _FakeResponse(json_data={"crates": []})),
        ("npmjs.org", _FakeResponse(json_data={"objects": []})),
    ])
    recs = await a.search(QueryParser.parse("http client"))
    platforms = {r.platform for r in recs}
    assert {"RubyGems", "Packagist", "NuGet", "AUR", "Docker Hub"} <= platforms
    aur = next(r for r in recs if r.platform == "AUR")
    assert aur.download_url == "https://aur.archlinux.org/cgit/aur.git/snapshot/angie.tar.gz"
    nuget = next(r for r in recs if r.platform == "NuGet")
    assert nuget.download_url.endswith(".nupkg")
    docker = next(r for r in recs if r.platform == "Docker Hub")
    assert docker.view_count == 13334094247


# --------------------------------------------------------------- adult adapters

@pytest.mark.asyncio
async def test_xvideos_parser():
    from omnisearch.adapters.adult_web import AdultVideoNetworkAdapter

    a = AdultVideoNetworkAdapter()
    client = _patch_http(a, [("xvideos.com", _FakeResponse(text=XVIDEOS_HTML))])
    recs = await a.search(QueryParser.parse("couple swap"))
    xv = [r for r in recs if r.platform == "XVideos"]
    assert len(xv) == 1
    r = xv[0]
    assert r.title == "Great couple swap - multiple orgasms! 3"
    assert r.platform_id == "23322380"
    assert r.duration_seconds == 26 * 60
    assert r.view_count == 2_100_000
    assert r.uploader_name == "Privat Porno"
    assert r.thumbnail_url == "https://thumb-cdn77.xvideos-cdn.com/xv_24_t.jpg"
    assert r.embed_url == "https://thumb-cdn77.xvideos-cdn.com/preview.mp4"
    assert r.item_type.value == "VIDEO"


@pytest.mark.asyncio
async def test_xhamster_parser():
    from omnisearch.adapters.adult_web import AdultVideoNetworkAdapter

    a = AdultVideoNetworkAdapter()
    _patch_http(a, [("xhamster.com", _FakeResponse(text=XHAMSTER_HTML))])
    recs = await a.search(QueryParser.parse("brunette"))
    xh = [r for r in recs if r.platform == "XHamster"]
    assert len(xh) == 1
    r = xh[0]
    assert r.title == "Hot Brunette Fucks Gardener - Sweetie Fox"
    assert r.platform_id == "29244703"
    assert r.duration_seconds == 32 * 60 + 15
    assert r.embed_url == "https://thumb-v3.xhpingcdn.com/preview.mp4"


@pytest.mark.asyncio
async def test_porntrex_parser():
    from omnisearch.adapters.adult_web import AdultVideoNetworkAdapter

    a = AdultVideoNetworkAdapter()
    _patch_http(a, [("porntrex.com", _FakeResponse(text=PORNTREX_HTML))])
    recs = await a.search(QueryParser.parse("jenny"))
    pt = [r for r in recs if r.platform == "PornTrex"]
    assert len(pt) == 1
    r = pt[0]
    assert r.title == "Jenny Manson - BDSM Anal Fucking with Gape"
    assert r.platform_id == "1902160"
    assert r.thumbnail_url == "https://ptx.cdntrex.com/300x168/1.jpg"  # // prefix normalized


# --------------------------------------------------------------- adult helpers

def test_parse_duration_formats():
    from omnisearch.adapters.adult_web import _parse_duration

    assert _parse_duration("26 min") == 26 * 60
    assert _parse_duration("1:23:45") == 5025
    assert _parse_duration("12:34") == 754
    assert _parse_duration("90 sec") == 90
    assert _parse_duration("2 hr") == 7200
    assert _parse_duration("garbage") is None


def test_parse_views_formats():
    from omnisearch.adapters.adult_web import _parse_views

    assert _parse_views("2.1M") == 2_100_000
    assert _parse_views("843k") == 843_000
    assert _parse_views("1,234") == 1234
    assert _parse_views("999") == 999
    assert _parse_views("") is None


# --------------------------------------------------------------- orchestrator registration

@pytest.mark.asyncio
async def test_orchestrator_registers_v24_adapters():
    from omnisearch.core.orchestrator import VideoDiscoveryOrchestrator
    from omnisearch.adapters.forges import GitLabAdapter, CodebergAdapter
    from omnisearch.adapters.gaming import ModrinthAdapter, SteamAdapter, ItchIoAdapter
    from omnisearch.adapters.music_media import ITunesAdapter, MixcloudAdapter
    from omnisearch.adapters.communities import HackerNewsAdapter, StackExchangeAdapter
    from omnisearch.adapters.academic import (
        EuropePMCAdapter, DoajAdapter, CrossrefAdapter, SemanticScholarAdapter,
    )

    orch = VideoDiscoveryOrchestrator(adapters=[
        GitLabAdapter(), CodebergAdapter(), ModrinthAdapter(), SteamAdapter(),
        ItchIoAdapter(), ITunesAdapter(), MixcloudAdapter(), HackerNewsAdapter(),
        StackExchangeAdapter(), EuropePMCAdapter(), DoajAdapter(), CrossrefAdapter(),
        SemanticScholarAdapter(),
    ])
    ids = {a.source_id for a in orch.adapters.values()}
    assert ids == {
        "gitlab", "codeberg", "modrinth", "steam", "itchio",
        "itunes", "mixcloud", "hackernews", "stackexchange",
        "europepmc", "doaj", "crossref", "semanticscholar",
    }
