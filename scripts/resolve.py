#!/usr/bin/env python3
"""Resolve official stable binaries and exact Flathub commits into a lock file."""
import argparse
import gzip
import hashlib
import json
import pathlib
import re
import subprocess
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OM_PACKAGES = ["omc", "omc-common", "libomc", "libomcsimulation", "libomccpp", "omedit",
               "libomplot", "libomsimulator", "libomsensplugin", "omlibrary"]
DEBIAN_PACKAGES = ["libicu76", "libblas3", "liblapack3", "libomniorb4-3t64",
                   "libomnithread4", "libopenscenegraph161", "libopenthreads21",
                   "libqt5core5t64", "libqt5gui5t64", "libqt5widgets5t64",
                   "libdouble-conversion3", "libmd4c0", "libboost1.83-dev",
                   "libboost-atomic1.83.0", "libboost-filesystem1.83.0",
                   "libboost-serialization1.83.0", "libboost-program-options1.83.0",
                   "libomp5-19"]


def fetch(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def packages(url):
    content = fetch(url)
    records = {}
    for paragraph in gzip.decompress(content).decode().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in paragraph.splitlines()
                      if ": " in line and not line.startswith(" "))
        if "Package" in fields:
            records[fields["Package"]] = fields
    return records, {"url": url, "sha256": hashlib.sha256(content).hexdigest()}


def flatpak_input(ref):
    commit = subprocess.check_output(
        ["flatpak", "remote-info", "--system", "--show-commit", "flathub", ref],
        text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{64}", commit):
        raise ValueError(f"invalid commit for {ref}: {commit}")
    return {"ref": ref, "commit": commit,
            "url": "https://dl.flathub.org/repo/", "remote": "flathub"}


def resolve(version=None):
    version = version or json.loads(fetch("https://openmodelica.org/api/linux.json"))["version"]["release"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("only official numbered stable releases are supported")
    base = f"https://build.openmodelica.org/omc/builds/linux/releases/{version}"
    debian = "https://deb.debian.org/debian"
    om_index, om_source = packages(f"{base}/dists/trixie/release/binary-amd64/Packages.gz")
    deb_index, deb_source = packages(f"{debian}/dists/trixie/main/binary-amd64/Packages.gz")
    result = {"format": 1, "upstream_version": version, "arch": "x86_64",
              "suite": "trixie", "indexes": [om_source, deb_source], "packages": []}
    for names, index, origin, kind in [(OM_PACKAGES, om_index, base, "openmodelica"),
                                       (DEBIAN_PACKAGES, deb_index, debian, "debian")]:
        for name in names:
            record = index[name]
            if kind == "openmodelica" and record["Version"].split("-", 1)[0] != version:
                raise ValueError(f"unexpected upstream version for {name}")
            result["packages"].append({"name": name, "version": record["Version"],
                "kind": kind, "url": f"{origin}/{record['Filename']}",
                "sha256": record["SHA256"], "size": int(record["Size"])})
    result["baseapp"] = flatpak_input("app/io.qt.qtwebengine.BaseApp/x86_64/6.11")
    result["sdk"] = flatpak_input("runtime/org.kde.Sdk/x86_64/6.11")
    # A recipe change must generate a rebuild, too. Package-index hashes are
    # recorded for provenance but unrelated uploads must not trigger releases.
    recipe = hashlib.sha256()
    for path in sorted([*ROOT.glob("scripts/*"), *ROOT.glob("bundle/**/*"),
                        *ROOT.glob(".github/workflows/*")]):
        if path.is_file():
            recipe.update(str(path.relative_to(ROOT)).encode() + b"\0" + path.read_bytes())
    result["recipe_sha256"] = recipe.hexdigest()
    identity = {key: value for key, value in result.items() if key != "indexes"}
    result["fingerprint"] = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    result["version"] = f"{version}-r{result['fingerprint'][:16]}"
    result["tag"] = f"v{result['version']}"
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version")
    args = parser.parse_args()
    print(json.dumps(resolve(args.version), indent=2))
