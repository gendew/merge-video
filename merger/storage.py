"""
S3/TOS storage helpers for uploading files and generating presigned URLs.
"""
import mimetypes
import os
from typing import Optional

import boto3
from botocore.client import Config


def storage_enabled() -> bool:
    return bool(
        os.getenv("S3_ACCESS_KEY")
        and os.getenv("S3_SECRET_KEY")
        and os.getenv("S3_BUCKET_OUTPUT")
    )


def _client():
    endpoint = os.getenv("S3_ENDPOINT")
    region = os.getenv("S3_REGION")
    access_key = os.getenv("S3_ACCESS_KEY")
    secret_key = os.getenv("S3_SECRET_KEY")
    addressing = os.getenv("S3_ADDRESSING_STYLE", "virtual")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(s3={"addressing_style": addressing}),
    )


def upload_file(local_path: str, bucket: str, key: str, content_type: Optional[str] = None, logger=None) -> str:
    if not storage_enabled():
        raise RuntimeError("Storage not configured")
    if not bucket:
        raise ValueError("Bucket is required for upload")
    client = _client()
    extra = {}
    ctype = content_type or mimetypes.guess_type(key)[0]
    if ctype:
        extra["ContentType"] = ctype
    if logger:
        logger.info("Uploading %s to %s/%s", local_path, bucket, key)
    upload_kwargs = {}
    if extra:
        upload_kwargs["ExtraArgs"] = extra
    client.upload_file(local_path, bucket, key, **upload_kwargs)
    return f"s3://{bucket}/{key}"


def presigned_url(bucket: str, key: str, expire_seconds: Optional[int] = None) -> str:
    if not storage_enabled():
        raise RuntimeError("Storage not configured")
    client = _client()
    expires = expire_seconds or int(os.getenv("OUTPUT_URL_EXPIRE_SECONDS", "86400"))
    return client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires,
    )
