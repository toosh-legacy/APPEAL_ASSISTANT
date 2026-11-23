"""BlobStore on Azurite through the official Azure Storage SDK (same SDK as Blob Storage in Phase C)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from azure.storage.blob import BlobSasPermissions, BlobServiceClient, generate_blob_sas

from appeal_core.settings import get_settings


class AzuriteBlobStore:
    def __init__(self, connection_string: str | None = None, container: str | None = None):
        s = get_settings()
        self.cs = connection_string or s.blob_connection_string
        self.container = container or s.blob_container
        self.client = BlobServiceClient.from_connection_string(self.cs)
        self._ensured = False

    def _ensure(self) -> None:
        if not self._ensured:
            cc = self.client.get_container_client(self.container)
            if not cc.exists():
                cc.create_container()
            self._ensured = True

    def create_upload_url(self, blob_name: str, minutes: int = 10) -> tuple[str, datetime]:
        """Write-only (create) SAS for one blob, valid `minutes`."""
        self._ensure()
        expiry = datetime.now(UTC) + timedelta(minutes=minutes)
        sas = generate_blob_sas(
            account_name=self.client.account_name,
            container_name=self.container,
            blob_name=blob_name,
            account_key=self.client.credential.account_key,
            permission=BlobSasPermissions(create=True, write=True),
            expiry=expiry,
        )
        url = f"{self.client.url.rstrip('/')}/{self.container}/{blob_name}?{sas}"
        return url, expiry

    def put(self, blob_name: str, data: bytes) -> str:
        self._ensure()
        self.client.get_blob_client(self.container, blob_name).upload_blob(data, overwrite=False)
        return f"{self.container}/{blob_name}"

    def get(self, blob_name: str) -> bytes:
        return self.client.get_blob_client(self.container, blob_name).download_blob().readall()

    def delete(self, blob_name: str) -> None:
        try:
            self.client.get_blob_client(self.container, blob_name).delete_blob()
        except Exception:
            pass

    def ping(self) -> bool:
        try:
            self._ensure()
            return True
        except Exception:
            return False
