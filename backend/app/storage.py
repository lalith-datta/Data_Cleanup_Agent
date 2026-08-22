"""Storage adapter — local dir now, Supabase Storage later behind this interface."""

from pathlib import Path

from .config import get_settings


class StorageAdapter:
    def save_upload(self, run_id: int, filename: str, data: bytes) -> str:
        raise NotImplementedError

    def read(self, path: str) -> bytes:
        raise NotImplementedError


class LocalStorage(StorageAdapter):
    def __init__(self) -> None:
        self.root = Path(get_settings().upload_dir)

    def ensure_ready(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def save_upload(self, run_id: int, filename: str, data: bytes) -> str:
        dest_dir = self.root / str(run_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / Path(filename).name
        dest.write_bytes(data)
        return str(dest)

    def read(self, path: str) -> bytes:
        return Path(path).read_bytes()


def get_storage() -> StorageAdapter:
    return LocalStorage()
