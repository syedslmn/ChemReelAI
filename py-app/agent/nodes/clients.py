from __future__ import annotations

import os

import boto3

_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

bedrock = boto3.client("bedrock-runtime", region_name=_REGION)
s3 = boto3.client("s3", region_name=_REGION)

S3_BUCKET = "nova-hackathon-videos"
NOVA_PRO_MODEL_ID = "amazon.nova-pro-v1:0"
NOVA_REEL_MODEL_ID = "amazon.nova-reel-v1:0"
PRESIGNED_URL_EXPIRY = 3600  # seconds
REEL_POLL_INTERVAL = 15      # seconds between Nova Reel status checks
