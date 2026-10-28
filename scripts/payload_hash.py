
#!/usr/bin/env python3
"""Hash the deployable payload, excluding changing build metadata."""

import hashlib
import os
import pathlib
import stat
import sys

EXCLUDED = {
    "VERSION",
    "SOURCES",
    "SOURCES.lock.json",
}


def payload_hash(root: pathlib.Path) -> str:
    digest = hashlib.sha256()

    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()

        if relative in EXCLUDED:
            continue

        mode = path.lstat().st_mode
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")

        if stat.S_ISLNK(mode):
            digest.update(b"symlink\0")
            digest.update(os.readlink(path).encode("utf-8"))
        elif stat.S_ISDIR(mode):
            digest.update(b"directory\0")
        elif stat.S_ISREG(mode):
            digest.update(b"file\0")
            digest.update(str(stat.S_IMODE(mode)).encode())
            digest.update(b"\0")
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
        else:
            raise ValueError(f"Unsupported file type: {path}")

        digest.update(b"\0")

    return digest.hexdigest()


if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1])
    print(payload_hash(root))
