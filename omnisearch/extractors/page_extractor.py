"""
Unified Page Extractor: Merges FileHost, Open Directory, JSON-LD, OpenGraph, Twitter Cards, HTML Meta, and oEmbed extractors.
"""

from __future__ import annotations
from typing import List, Optional
from bs4 import BeautifulSoup

from omnisearch.models.video import ItemRecord, VideoRecord
from omnisearch.core.dedup import DeduplicationEngine
from omnisearch.extractors.json_ld import JsonLdExtractor
from omnisearch.extractors.opengraph import OpenGraphExtractor
from omnisearch.extractors.html_meta import HtmlMetaExtractor
from omnisearch.extractors.oembed import OEmbedExtractor
from omnisearch.extractors.file_hosts import FileHostExtractor


class PageExtractor:
    """Unified HTML page metadata and file extractor."""

    @classmethod
    def extract_from_html(cls, html_content: str, page_url: str) -> List[ItemRecord]:
        if not html_content:
            return []

        extracted_records: List[ItemRecord] = []
        soup = BeautifulSoup(html_content, "html.parser")

        # 0. Check specialized File Hosting / Cyberlocker extractor
        if FileHostExtractor.is_file_host_url(page_url):
            file_host_rec = FileHostExtractor.extract(html_content, page_url)
            if file_host_rec:
                extracted_records.append(file_host_rec)

        # 1. Check if page is an Open HTTP Directory (Apache/Nginx Index of /)
        if FileHostExtractor.is_open_directory(soup, page_url):
            dir_files = FileHostExtractor.extract_open_directory_files(html_content, page_url)
            if dir_files:
                extracted_records.extend(dir_files)
            else:
                dir_root = FileHostExtractor._extract_open_directory_root(soup, page_url)
                if dir_root:
                    extracted_records.append(dir_root)

        # 2. JSON-LD VideoObject / MediaObject
        json_ld_records = JsonLdExtractor.extract_from_html(html_content, page_url)
        extracted_records.extend(json_ld_records)

        # 3. OpenGraph
        og_record = OpenGraphExtractor.extract_from_html(html_content, page_url)
        if og_record:
            extracted_records.append(og_record)

        # 4. HTML Meta / Twitter Cards
        html_meta_record = HtmlMetaExtractor.extract_from_html(html_content, page_url)
        if html_meta_record:
            extracted_records.append(html_meta_record)

        # 5. Generic Download Page fallback (detects download links / file attachments)
        if not extracted_records:
            generic_rec = FileHostExtractor._extract_generic_download_page(soup, page_url)
            if generic_rec:
                extracted_records.append(generic_rec)

        if not extracted_records:
            return []

        # Merge extracted records for the same page
        deduped, _ = DeduplicationEngine.deduplicate(extracted_records)
        return deduped
