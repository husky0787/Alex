"""Raw bodies are stored outside the frontend bucket and never contain request headers."""
from pathlib import Path


class LocalRawStore:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def save(self, key: str, body: bytes) -> str:
        target = (self.root / key).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Invalid raw object key")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(body)
        return target.as_uri()

    def read(self, key: str) -> bytes:
        target = (self.root / key).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Invalid raw object key")
        return target.read_bytes()


class S3RawStore:
    """Use an explicitly provisioned private data bucket, never frontend hosting."""
    def __init__(self, bucket: str, client):
        self.bucket = bucket
        self.client = client

    def save(self, key: str, body: bytes) -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType="application/json",
                               ServerSideEncryption="AES256", IfNoneMatch="*")
        return f"s3://{self.bucket}/{key}"

    def read(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        with response["Body"] as stream:
            return stream.read()
