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

# ── TEMP FLAG: set True to skip Nova Reel and reuse existing S3 clips ────
USE_MOCK_CLIPS = False
_MOCK_RUN_ID = "08ee89a7-34f6-46b6-9d5c-4e2447551880"
_MOCK_CLIP_KEYS = [
    f"tmp/{_MOCK_RUN_ID}/clip_00/268a1fyq9vzy/output.mp4",
    f"tmp/{_MOCK_RUN_ID}/clip_01/hy18wo1l52wy/output.mp4",
    f"tmp/{_MOCK_RUN_ID}/clip_02/ljmj8cu9xx4q/output.mp4",
    f"tmp/{_MOCK_RUN_ID}/clip_03/k1nw3997def5/output.mp4",
    f"tmp/{_MOCK_RUN_ID}/clip_04/wofiuduxjpr4/output.mp4",
    f"tmp/{_MOCK_RUN_ID}/clip_05/1dqujznq833a/output.mp4",
]


def generate_clips(state: ExperimentState) -> dict:
    """
    Node 2 — Parallel approach:
      1. Submit ALL steps to Nova Reel concurrently (start_async_invoke).
      2. Poll ALL invocations until every one completes or fails.
      3. Download all clips from S3 and concatenate with ffmpeg.
      4. Upload the final video to S3.

    When USE_MOCK_CLIPS is True, skips Nova Reel entirely and reuses
    existing clips from S3 for testing.
    """
    steps = state["procedure_steps"]
    run_id = str(uuid.uuid4())
    work_dir = Path(tempfile.mkdtemp(prefix="nova_clips_"))
    clip_s3_keys: list[str] = []
    local_clip_paths: list[str] = []

    try:
        if USE_MOCK_CLIPS:
            # ── MOCK MODE: download existing clips from S3 ─────────────
            logger.info("MOCK MODE — skipping Nova Reel, reusing %d existing clips from run %s",
                        len(_MOCK_CLIP_KEYS), _MOCK_RUN_ID)
            # Use as many mock clips as we have steps (cycle if needed)
            for i in range(len(steps)):
                s3_key = _MOCK_CLIP_KEYS[i % len(_MOCK_CLIP_KEYS)]
                local_path = str(work_dir / f"clip_{i:02d}.mp4")

                logger.info("Downloading mock clip %d/%d from S3: s3://%s/%s",
                            i + 1, len(steps), S3_BUCKET, s3_key)
                s3.download_file(S3_BUCKET, s3_key, local_path)

                clip_s3_keys.append(s3_key)
                local_clip_paths.append(local_path)
        else:
            # ── REAL MODE: call Nova Reel ──────────────────────────────
            # Phase 1: Submit all jobs in parallel
            logger.info("Starting video clip generation — %d steps, run_id: %s", len(steps), run_id)
            invocations: list[dict] = []  # {arn, step_index, clip_prefix}

            for i, step in enumerate(steps):
                clip_prefix = f"tmp/{run_id}/clip_{i:02d}"

                reel_prompt = (
                    f"6-second realistic laboratory video.\n\n"
                    f"Modern chemistry lab, wooden lab bench, neutral white lighting, "
                    f"fixed camera angle at table height, same student wearing white "
                    f"lab coat and safety goggles.\n\n"
                    f"Action: {step}"
                )

                logger.info("Submitting step %d/%d to Nova Reel (%s): '%s'",
                            i + 1, len(steps), NOVA_REEL_MODEL_ID, reel_prompt)
                arn = _submit_with_retry(reel_prompt, clip_prefix, i)
                logger.info("Nova Reel invocation started — step %d/%d, ARN: %s",
                            i + 1, len(steps), arn)
                invocations.append({"arn": arn, "step_index": i, "clip_prefix": clip_prefix})

                # Stagger submissions to avoid Bedrock throttling
                if i < len(steps) - 1:
                    time.sleep(2)

            logger.info("All %d Nova Reel jobs submitted. Invocations: %s", len(steps), invocations)
            logger.info("Waiting for completion...")

            # Phase 2: Poll all jobs until every one finishes
            _wait_for_all(invocations, len(steps))
            logger.info("All %d Nova Reel jobs completed successfully.", len(steps))

            # Phase 3: Download clips
            for inv in invocations:
                i = inv["step_index"]
                s3_key = _find_clip_key(inv["clip_prefix"], i, len(steps))
                local_path = str(work_dir / f"clip_{i:02d}.mp4")

                logger.info("Downloading clip %d/%d from S3: s3://%s/%s",
                            i + 1, len(steps), S3_BUCKET, s3_key)
                s3.download_file(S3_BUCKET, s3_key, local_path)
                logger.info("Clip %d/%d downloaded to %s", i + 1, len(steps), local_path)

                clip_s3_keys.append(s3_key)
                local_clip_paths.append(local_path)

        # ── Common: concatenate with title cards and upload ────────────
        logger.info("All %d clips downloaded. Concatenating with ffmpeg...", len(steps))
        final_video_key = _concat_and_upload(local_clip_paths, steps, run_id)

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


MAX_SUBMIT_RETRIES = 3
SUBMIT_RETRY_DELAY = 5  # seconds


def _submit_with_retry(step_text: str, clip_prefix: str, seed: int) -> str:
    """Submits a Nova Reel job with retry on transient ServiceUnavailable errors."""
    for attempt in range(1, MAX_SUBMIT_RETRIES + 1):
        try:
            reel_response = bedrock.start_async_invoke(
                modelId=NOVA_REEL_MODEL_ID,
                modelInput={
                    "taskType": "TEXT_VIDEO",
                    "textToVideoParams": {"text": step_text},
                    "videoGenerationConfig": {
                        "durationSeconds": 6,
                        "fps": 24,
                        "dimension": "1280x720",
                        "seed": seed,
                    },
                },
                outputDataConfig={
                    "s3OutputDataConfig": {
                        "s3Uri": f"s3://{S3_BUCKET}/{clip_prefix}/",
                    }
                },
            )
            return reel_response["invocationArn"]
        except bedrock.exceptions.ServiceUnavailableException:
            if attempt == MAX_SUBMIT_RETRIES:
                raise
            wait = SUBMIT_RETRY_DELAY * attempt
            logger.warning("Nova Reel submit attempt %d/%d failed (ServiceUnavailable), "
                           "retrying in %ds...", attempt, MAX_SUBMIT_RETRIES, wait)
            time.sleep(wait)
    raise RuntimeError("Unreachable")  # satisfy type checker


def _wait_for_all(invocations: list[dict], total_steps: int) -> None:
    """Polls all Nova Reel invocations until every one is Completed or raises on failure."""
    pending = {inv["arn"]: inv["step_index"] for inv in invocations}

    while pending:
        logger.info("Polling %d pending Nova Reel job(s)...", len(pending))
        completed_arns = []

        for arn, step_index in pending.items():
            status_resp = bedrock.get_async_invoke(invocationArn=arn)
            status = status_resp["status"]

            if status == "Completed":
                logger.info("Nova Reel clip %d/%d completed", step_index + 1, total_steps)
                completed_arns.append(arn)
            elif status == "Failed":
                reason = status_resp.get("failureMessage", "unknown reason")
                raise RuntimeError(
                    f"Nova Reel failed for step {step_index + 1}/{total_steps}: {reason}"
                )
            else:
                logger.info("Nova Reel clip %d/%d status: %s",
                            step_index + 1, total_steps, status)

        for arn in completed_arns:
            del pending[arn]

        if pending:
            logger.info("Waiting %ds before next poll (%d job(s) still pending)...",
                        REEL_POLL_INTERVAL, len(pending))
            time.sleep(REEL_POLL_INTERVAL)


def _find_clip_key(clip_prefix: str, step_index: int, total_steps: int) -> str:
    """Lists objects under the clip prefix and returns the first .mp4 key found."""
    resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=clip_prefix)
    contents = resp.get("Contents", [])
    logger.info("S3 objects under '%s': %s", clip_prefix,
                [obj["Key"] for obj in contents])
    for obj in contents:
        if obj["Key"].endswith(".mp4"):
            return obj["Key"]
    raise FileNotFoundError(
        f"No .mp4 file found under s3://{S3_BUCKET}/{clip_prefix} "
        f"for step {step_index + 1}/{total_steps}"
    )


def _make_step_title_clip(
    step_index: int, step_text: str, work_dir: Path,
    width: int = 1280, height: int = 720, duration: int = 3, fps: int = 24,
) -> str:
    """Creates a 3-second title-card video clip showing 'Step N' and the step text."""
    out_path = str(work_dir / f"title_{step_index:02d}.mp4")

    # Write step label and body to separate text files to avoid escaping issues
    label_file = work_dir / f"label_{step_index:02d}.txt"
    body_file = work_dir / f"body_{step_index:02d}.txt"

    label_file.write_text(f"Step {step_index + 1}", encoding="utf-8")

    # Wrap long text (~45 chars per line)
    words = step_text.split()
    lines: list[str] = []
    current = ""
    for w in words:
        if current and len(current) + len(w) + 1 > 45:
            lines.append(current)
            current = w
        else:
            current = f"{current} {w}" if current else w
    if current:
        lines.append(current)
    body_file.write_text("\n".join(lines), encoding="utf-8")

    logger.info("Generating title card for step %d: '%s'", step_index + 1, step_text[:60])

    # Use textfile= instead of text= to avoid all escaping problems
    label_path_esc = str(label_file).replace("\\", "/").replace(":", "\\:")
    body_path_esc = str(body_file).replace("\\", "/").replace(":", "\\:")

    vf = (
        f"drawtext=textfile='{label_path_esc}':"
        f"fontsize=52:fontcolor=0x63b3ed:x=(w-text_w)/2:y=(h/2)-80,"
        f"drawtext=textfile='{body_path_esc}':"
        f"fontsize=28:fontcolor=0xcbd5e1:x=(w-text_w)/2:y=(h/2)-10"
    )

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x1e293b:s={width}x{height}:d={duration}:r={fps}",
            "-f", "lavfi",
            "-i", "anullsrc=r=48000:cl=stereo",
            "-vf", vf,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-t", str(duration),
            out_path,
        ],
        check=True,
        capture_output=True,
    )
    logger.info("Title card created: %s", out_path)
    return out_path


def _concat_and_upload(local_clip_paths: list[str], steps: list[str], run_id: str) -> str:
    """
    Interleaves 3-second step title cards before each clip,
    concatenates everything with ffmpeg, uploads to S3, returns the S3 key.
    """
    work_dir = Path(local_clip_paths[0]).parent

    # Build interleaved list: [title_0, clip_0, title_1, clip_1, ...]
    interleaved: list[str] = []
    for i, clip_path in enumerate(local_clip_paths):
        step_text = steps[i] if i < len(steps) else f"Step {i + 1}"
        title_path = _make_step_title_clip(i, step_text, work_dir)
        interleaved.append(title_path)
        interleaved.append(clip_path)

    # Re-encode all clips to a common format first for safe concat
    normalized: list[str] = []
    for j, path in enumerate(interleaved):
        norm_path = str(work_dir / f"norm_{j:03d}.mp4")
        logger.info("Normalizing segment %d/%d: %s", j + 1, len(interleaved), path)
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", path,
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "48000", "-ac", "2",
                "-r", "24",
                "-s", "1280x720",
                norm_path,
            ],
            check=True,
            capture_output=True,
        )
        normalized.append(norm_path)

    concat_list = work_dir / "concat.txt"
    concat_list.write_text("\n".join(f"file '{p}'" for p in normalized))

    final_path = work_dir / "final_video.mp4"
    logger.info("Running ffmpeg to concatenate %d segments into %s", len(normalized), final_path)
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
