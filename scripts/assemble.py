#!/usr/bin/env python3
"""Assemble a traceable runtime tree from a resolved lock; execute no payloads."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]


def checked_download(package, directory):
    target = directory / (package["name"] + ".deb")
    if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != package["sha256"]:
        with urllib.request.urlopen(package["url"], timeout=120) as response, target.open("wb") as output:
            shutil.copyfileobj(response, output)
    if target.stat().st_size != package["size"] or hashlib.sha256(target.read_bytes()).hexdigest() != package["sha256"]:
        raise ValueError(f"size/hash mismatch: {package['name']}")
    return target


def installed_files(component):
    ref = component["ref"]
    commit = subprocess.check_output(["flatpak", "info", "--system", "--show-commit", ref], text=True).strip()
    if commit != component["commit"]:
        raise ValueError(f"{ref}: installed commit {commit} differs from lock {component['commit']}")
    return pathlib.Path(subprocess.check_output(
        ["flatpak", "info", "--system", "--show-location", ref], text=True).strip()) / "files"


def unpack_deb(archive, unpack):
    if shutil.which("dpkg-deb"):
        subprocess.run(["dpkg-deb", "-x", str(archive), str(unpack)], check=True)
        return
    # Developer machines need not be Debian. Builder's bsdtar reads .deb
    # containers without installing the distro package manager on the host.
    tool = ["bsdtar"] if shutil.which("bsdtar") else [
        "flatpak", "run", "--command=bsdtar", "org.flatpak.Builder"]
    unpack.mkdir()
    with subprocess.Popen([*tool, "-xOf", str(archive), "data.tar*"], stdout=subprocess.PIPE) as reader:
        subprocess.run([*tool, "--no-same-owner", "-xf", "-", "-C", str(unpack)],
                       stdin=reader.stdout, check=True)
        reader.stdout.close()
        if reader.wait():
            raise ValueError(f"could not read {archive}")


def needed(path):
    output = subprocess.check_output(["readelf", "-d", str(path)], text=True)
    return re.findall(r"\(NEEDED\).*\[(.*?)\]", output)


def copy_qt(base, sdk, bundle):
    """Copy the runtime dependency closure, preserving SONAME links."""
    destination = bundle / "qt"
    (destination / "lib").mkdir(parents=True)
    (destination / "libexec").mkdir()
    libraries = {}
    for path in (base / "lib").rglob("*.so*"):
        if path.is_file():
            libraries[path.name] = path
    runtime_names = {path.name for path in (sdk / "lib").rglob("*.so*") if path.is_file()}
    pending = ["libQt6WebEngineCore.so.6", "libQt6WebEngineWidgets.so.6"]
    helper = base / "lib/libexec/QtWebEngineProcess"
    shutil.copy2(helper, destination / "libexec/QtWebEngineProcess")
    pending.extend(name for name in needed(helper) if name not in runtime_names)
    copied = set()
    while pending:
        name = pending.pop()
        if name in copied:
            continue
        source = libraries[name]
        real = source.resolve()
        if not (destination / "lib" / real.name).exists():
            shutil.copy2(real, destination / "lib" / real.name)
        if name != real.name:
            (destination / "lib" / name).symlink_to(real.name)
        copied.add(name)
        pending.extend(dep for dep in needed(real) if dep not in runtime_names and dep not in copied)
    shutil.copytree(base / "resources", destination / "resources")
    locales = destination / "translations/qtwebengine_locales"
    locales.mkdir(parents=True)
    for locale in ["en-US", "en-GB", "de", "fr", "zh-CN", "zh-TW"]:
        shutil.copy2(base / "translations/qtwebengine_locales" / f"{locale}.pak", locales)
    # Include license texts shipped by the BaseApp without developer tooling.
    for relative in ["share/licenses", "share/doc"]:
        if (base / relative).is_dir():
            shutil.copytree(base / relative, destination / relative)
    shutil.copy2(base / "manifest.json", destination / "manifest.json")
    return destination


def assemble(lock, output):
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    output.mkdir(parents=True)
    downloads = output.parent / "downloads"
    downloads.mkdir(exist_ok=True)
    stage = output.parent / "stage"
    if stage.exists():
        raise ValueError(f"staging directory already exists: {stage}")
    stage.mkdir()
    upstream = output / "usr"
    upstream.mkdir()
    for package in lock["packages"]:
        print(f"fetching {package['name']} {package['version']}", flush=True)
        archive = checked_download(package, downloads)
        unpack = stage / package["name"]
        unpack_deb(archive, unpack)
        if package["kind"] == "openmodelica":
            shutil.copytree(unpack / "usr", upstream, dirs_exist_ok=True, symlinks=True)
        else:
            # Debian runtime libraries only: no unused OpenSceneGraph plugin
            # modules, developer tools or absolute /usr symlinks.
            source = unpack / "usr/lib/x86_64-linux-gnu"
            dest = upstream / "lib/x86_64-linux-gnu"
            dest.mkdir(parents=True, exist_ok=True)
            for path in source.glob("*.so*"):
                qt5 = {"libqt5core5t64": "libQt5Core.so.",
                       "libqt5gui5t64": "libQt5Gui.so.",
                       "libqt5widgets5t64": "libQt5Widgets.so."}.get(package["name"])
                if qt5 and not path.name.startswith(qt5):
                    continue
                if path.is_symlink():
                    (dest / path.name).symlink_to(os.readlink(path))
                elif path.is_file():
                    shutil.copy2(path, dest / path.name)
            for relative in ["blas", "lapack"]:
                if (source / relative).exists():
                    shutil.copytree(source / relative, dest / relative, symlinks=True)
            doc = unpack / "usr/share/doc"
            if doc.exists():
                shutil.copytree(doc, upstream / "share/doc", dirs_exist_ok=True, symlinks=True)
    for name, subfolder in [("blas", "blas"), ("lapack", "lapack")]:
        (upstream / "lib" / f"lib{name}.so").symlink_to(f"x86_64-linux-gnu/{subfolder}/lib{name}.so.3")
    qt = copy_qt(installed_files(lock["baseapp"]), installed_files(lock["sdk"]), output)
    shutil.copytree(ROOT / "bundle", output, dirs_exist_ok=True, symlinks=True)
    for path in (output / "bin").iterdir():
        path.chmod(0o755)
    (output / "VERSION").write_text(lock["version"] + "\n")
    (output / "SOURCES.lock.json").write_text(json.dumps(lock, indent=2) + "\n")
    sources = ["SHA256\tSIZE\tURL\tCOMPONENT"]
    for item in lock["indexes"]:
        sources.append(f"{item['sha256']}\t-\t{item['url']}\tPackages index")
    for item in lock["packages"]:
        sources.append(f"{item['sha256']}\t{item['size']}\t{item['url']}\t{item['name']} {item['version']}")
    for kind in ["baseapp", "sdk"]:
        item = lock[kind]
        sources.append(f"{item['commit']}\t-\t{item['url']}\tOSTree {item['ref']}")
    (output / "SOURCES").write_text("\n".join(sources) + "\n")
    hashes = []
    for path in sorted(qt.rglob("*")):
        if path.is_file() and not path.is_symlink():
            hashes.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(output)}")
    (output / "QT-FILES.sha256").write_text("\n".join(hashes) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lock", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()
    assemble(json.loads(args.lock.read_text()), args.output.resolve())
