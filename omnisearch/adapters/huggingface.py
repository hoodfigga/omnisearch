"""
HuggingFace Source Adapter: ML models and datasets via the public Hub API.

Models get direct-download weights pages; datasets expose parquet/data access.
"""

from __future__ import annotations
import logging
from typing import List
from omnisearch.models.query import SearchQuery
from omnisearch.models.video import VideoMetadataSource, VideoRecord, ItemType
from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.extractors.json_ld import parse_iso_datetime

logger = logging.getLogger(__name__)


class HuggingFaceAdapter(BaseSourceAdapter):
    """Discovers ML models and datasets on the HuggingFace Hub."""

    @property
    def source_id(self) -> str:
        return "huggingface"

    @property
    def source_name(self) -> str:
        return "HuggingFace Hub (models & datasets)"

    async def search(self, query: SearchQuery, page: int = 1) -> List[VideoRecord]:
        search_terms = " ".join(query.extracted_phrases + query.extracted_terms) or query.raw_query
        if not search_terms.strip():
            return []

        records: List[VideoRecord] = []
        try:
            params = {"search": search_terms, "limit": 20, "sort": "downloads", "direction": -1}
            resp = await self.http_client.get(
                "https://huggingface.co/api/models", params=params, timeout=8.0
            )
            if resp.status_code == 200:
                for m in resp.json():
                    model_id = m.get("id", "")
                    if not model_id:
                        continue
                    pipeline = m.get("pipeline_tag")
                    tags = ["huggingface", "model", "ai-weights"]
                    if pipeline:
                        tags.append(pipeline)
                    records.append(
                        VideoRecord(
                            id=f"hf_model:{model_id}",
                            canonical_url=f"https://huggingface.co/{model_id}",
                            download_url=f"https://huggingface.co/{model_id}/resolve/main/README.md",
                            platform="HuggingFace",
                            platform_id=model_id,
                            title=model_id,
                            description=f"ML model ({pipeline or 'general'}) — {m.get('downloads', 0):,} downloads, {m.get('likes', 0):,} likes",
                            item_type=ItemType.SOFTWARE,
                            uploader_name=model_id.split("/")[0] if "/" in model_id else None,
                            publication_date=parse_iso_datetime(m.get("createdAt") or m.get("lastModified")),
                            view_count=m.get("downloads"),
                            like_count=m.get("likes"),
                            tags=tags,
                            metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                            raw_metadata={"hf_model": {k: m.get(k) for k in ("id", "downloads", "likes", "pipeline_tag", "tags")}},
                        )
                    )
        except Exception as exc:
            logger.debug("HuggingFace models search error: %s", exc)

        # Datasets
        try:
            params = {"search": search_terms, "limit": 15, "sort": "downloads", "direction": -1}
            resp = await self.http_client.get(
                "https://huggingface.co/api/datasets", params=params, timeout=8.0
            )
            if resp.status_code == 200:
                for d in resp.json():
                    ds_id = d.get("id", "")
                    if not ds_id:
                        continue
                    records.append(
                        VideoRecord(
                            id=f"hf_dataset:{ds_id}",
                            canonical_url=f"https://huggingface.co/datasets/{ds_id}",
                            download_url=f"https://huggingface.co/datasets/{ds_id}/resolve/main/README.md",
                            platform="HuggingFace",
                            platform_id=ds_id,
                            title=ds_id,
                            description=f"Dataset — {d.get('downloads', 0):,} downloads, {d.get('likes', 0):,} likes",
                            item_type=ItemType.DATASET,
                            uploader_name=ds_id.split("/")[0] if "/" in ds_id else None,
                            publication_date=parse_iso_datetime(d.get("createdAt") or d.get("lastModified")),
                            view_count=d.get("downloads"),
                            like_count=d.get("likes"),
                            tags=["huggingface", "dataset", "ai-data"],
                            metadata_sources=[VideoMetadataSource.OFFICIAL_API],
                            raw_metadata={"hf_dataset": {k: d.get(k) for k in ("id", "downloads", "likes", "tags")}},
                        )
                    )
        except Exception as exc:
            logger.debug("HuggingFace datasets search error: %s", exc)

        return records
