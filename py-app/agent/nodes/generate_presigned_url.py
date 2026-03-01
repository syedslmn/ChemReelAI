from __future__ import annotations

import logging

from ..state import ExperimentState
from .clients import PRESIGNED_URL_EXPIRY, S3_BUCKET, s3

logger = logging.getLogger(__name__)


def generate_presigned_url(state: ExperimentState) -> dict:
    """
    Node 3 — Creates a presigned S3 URL for the concatenated video so the
    browser can play it directly without requiring AWS credentials.
    """
    final_key = state.get("final_video_key")
    if not final_key:
        return {"error": "Node 3 (generate_presigned_url): no final_video_key in state."}

    try:
        logger.info("Generating presigned URL for S3 key: %s (expires in %ds)",
                    final_key, PRESIGNED_URL_EXPIRY)
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": final_key},
            ExpiresIn=PRESIGNED_URL_EXPIRY,
        )
        logger.info("Presigned URL generated successfully for key: %s", final_key)
        return {"video_url": url}

    except Exception as exc:
        logger.error("Node 3 (generate_presigned_url) failed: %s", exc, exc_info=True)
        return {"error": f"Node 3 (generate_presigned_url) failed: {exc}", "video_url": None}
