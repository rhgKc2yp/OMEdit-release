#!/usr/bin/env bash
# Package only after verify.sh has succeeded on this exact tree.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
version="$(tr -d '\n' < "$root/build/omedit/VERSION")"
name="omedit-$version-x86_64.tar.gz"
mkdir -p "$root/dist"
tar --sort=name --mtime='UTC 2026-01-01' --owner=0 --group=0 --numeric-owner \
    -C "$root/build" -cf - omedit | gzip -n -6 > "$root/dist/$name"
(cd "$root/dist" && sha256sum "$name" > "$name.sha256")
cp "$root/build/omedit/SOURCES" "$root/dist/SOURCES"
cp "$root/build/omedit/SOURCES.lock.json" "$root/dist/SOURCES.lock.json"
