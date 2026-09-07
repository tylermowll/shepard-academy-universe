"""Private S3 object transport for an explicitly configured AWS deployment."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal
from uuid import UUID

import boto3
from botocore.config import Config

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class S3Storage:
    """Opaque keys, TLS, encryption and bounded responses; credentials use workload IAM."""

    def __init__(
        self,
        bucket: str,
        region: str,
        client: S3Client | None = None,
        *,
        prefix: Literal["objects", "backups"] = "objects",
    ):
        self.bucket = bucket
        self.prefix = prefix
        self.client = client or boto3.client(
            "s3",
            region_name=region,
            config=Config(retries={"total_max_attempts": 1}, connect_timeout=5, read_timeout=30),
        )

    def put(self, key: UUID, data: bytes) -> None:
        if len(data) > 64 * 1024 * 1024:
            raise ValueError("Object exceeds the 64 MiB cloud transfer limit.")
        self.client.put_object(
            Bucket=self.bucket,
            Key=self.prefix + "/" + str(key),
            Body=data,
            ServerSideEncryption="AES256",
            ContentType="application/octet-stream",
            CacheControl="no-store",
        )

    def get(self, key: UUID) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=self.prefix + "/" + str(key))
        body = response["Body"]
        try:
            if response.get("ContentLength", 0) > 64 * 1024 * 1024:
                raise ValueError("Object exceeds the cloud transfer limit.")
            data = body.read(64 * 1024 * 1024 + 1)
            if len(data) > 64 * 1024 * 1024:
                raise ValueError("Object exceeds the cloud transfer limit.")
            return data
        finally:
            body.close()

    def delete(self, key: UUID) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self.prefix + "/" + str(key))

    def close(self) -> None:
        self.client.close()
