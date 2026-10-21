"""Small private image-store port and filesystem adapter. No HTTP/public mounting."""

import os
from pathlib import Path
from typing import Protocol


class ImageStore(Protocol):
    def put(self, key: str, content: bytes) -> None: ...
    def read(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalImageStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, key):
        if "/" in key or "\\" in key or key.startswith("."):
            raise ValueError("Invalid private object key")
        path = self.root / key
        if path.is_symlink():
            raise ValueError("Object symlinks are forbidden")
        return path

    def put(self, key, content):
        path = self.path(key)
        # Reserve key exclusively; readers cannot reach it until DB finalization marks ready.
        with path.open("xb") as handle:
            os.chmod(path, 0o600)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        directory = os.open(self.root, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def read(self, key):
        return self.path(key).read_bytes()

    def delete(self, key):
        self.path(key).unlink(missing_ok=True)
