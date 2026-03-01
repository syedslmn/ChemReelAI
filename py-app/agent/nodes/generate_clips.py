from __future__ import annotations

import logging
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from ..state import ExperimentState
from .clients import NOVA_REEL_MODEL_ID, REEL_POLL_INTERVAL, S3_BUCKET, bedrock, s3

logger = logging.getLogger(__name__)


def generate_clips(state: ExperimentState) -> dict:
    """
    Node 2 — For each procedure step:
      1. Calls start_async_invoke on Nova Reel (output goes to S3).
      2. Polls get_async_invoke until Completed or Failed.
      3. Downloads the resulting clip from S3 to a local temp dir.

    After all clips are downloaded, concatenates them with ffmpeg and uploads
    the final video back to S3.
    """
    steps = state["procedure_steps"]
    run_id = str(uuid.uuid4())
    work_dir = Path(tempfile.mkdtemp(prefix="nova_clips_"))
    clip_s3_keys: list[str] = []
    local_clip_paths: list[str] = []

    try:
        logger.info("Starting video clip generation — %d steps, run_id: %s", len(steps), run_id)
        for i, step in enumerate(steps):
            clip_prefix = f"tmp/{run_id}/clip_{i:02d}"

            logger.info("Submitting step %d/%d to Nova Reel (%s): '%s'",
                        i + 1, len(steps), NOVA_REEL_MODEL_ID, step)
            reel_response = bedrock.start_async_invoke(
                modelId=NOVA_REEL_MODEL_ID,
                modelInput={
                    "taskType": "TEXT_VIDEO",
                    "textToVideoParams": {"text": step},
                    "videoGenerationConfig": {
                        "durationSeconds": 6,
                        "fps": 24,
                        "dimension": "1280x720",
                        "seed": i,
                    },
                },
                outputDataConfig={
                    "s3OutputDataConfig": {
                        "s3Uri": f"s3://{S3_BUCKET}/{clip_prefix}",
                    }
                },
            )
            invocation_arn = reel_response["invocationArn"]
            logger.info("Nova Reel invocation started — step %d/%d, ARN: %s",
                        i + 1, len(steps), invocation_arn)

            _wait_for_reel(invocation_arn, step_index=i, total_steps=len(steps))

            s3_key = f"{clip_prefix}/output.mp4"
            local_path = str(work_dir / f"clip_{i:02d}.mp4")
            logger.info("Downloading clip %d/%d from S3: s3://%s/%s",
                        i + 1, len(steps), S3_BUCKET, s3_key)
            s3.download_file(S3_BUCKET, s3_key, local_path)
            logger.info("Clip %d/%d downloaded to %s", i + 1, len(steps), local_path)

            clip_s3_keys.append(s3_key)
            local_clip_paths.append(local_path)

        logger.info("All %d clips ready. Concatenating with ffmpeg...", len(steps))
        final_video_key = _concat_and_upload(local_clip_paths, run_id)

        return {
            "clip_s3_keys": clip_s3_keys,
            "final_video_key": final_video_key,
        }

    except Exception as exc:
        logger.error("Node 2 (generate_clips) failed: %s", exc, exc_info=True)
        return {
            "error": f"Node 2 (generate_clips) failed: {exc}",
            "clip_s3_keys": clip_s3_keys,
            "final_video_key": None,
        }


def _wait_for_reel(invocation_arn: str, step_index: int, total_steps: int = 0) -> None:
    """Blocks until the Nova Reel async job completes or raises on failure."""
    while True:
        status_resp = bedrock.get_async_invoke(invocationArn=invocation_arn)
        status = status_resp["status"]

        if status == "Completed":
            logger.info("Nova Reel clip %d/%d completed", step_index + 1, total_steps)
            return
        elif status == "Failed":
            reason = status_resp.get("failureMessage", "unknown reason")
            raise RuntimeError(f"Nova Reel failed for step {step_index}: {reason}")

        logger.info("Nova Reel clip %d/%d status: %s — polling again in %ds",
                    step_index + 1, total_steps, status, REEL_POLL_INTERVAL)
        time.sleep(REEL_POLL_INTERVAL)


def _concat_and_upload(local_clip_paths: list[str], run_id: str) -> str:
    """Concatenates local clip files with ffmpeg, uploads to S3, returns the S3 key."""
    work_dir = Path(local_clip_paths[0]).parent

    concat_list = work_dir / "concat.txt"
    concat_list.write_text("\n".join(f"file '{p}'" for p in local_clip_paths))

    final_path = work_dir / "final_video.mp4"
    logger.info("Running ffmpeg to concatenate %d clips into %s", len(local_clip_paths), final_path)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(final_path),
        ],
        check=True,
        capture_output=True,
    )
    logger.info("ffmpeg concatenation complete: %s", final_path)

    final_key = f"experiments/{run_id}/final_video.mp4"
    logger.info("Uploading final video to S3: s3://%s/%s", S3_BUCKET, final_key)
    s3.upload_file(
        Filename=str(final_path),
        Bucket=S3_BUCKET,
        Key=final_key,
        ExtraArgs={"ContentType": "video/mp4"},
    )
    logger.info("Final video uploaded to S3 — key: %s", final_key)
    return final_key
