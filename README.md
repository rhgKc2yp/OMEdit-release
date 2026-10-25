# OMEdit release bundle

Community packaging of the official stable OpenModelica Linux binaries for
`org.kde.Sdk//6.11`. This repository does not compile or patch OpenModelica or Qt.
It assembles a relocatable archive for the FlatPark package, keeping the large
Qt WebEngine binaries in a GitHub release rather than FlatPark's repository.

The archive runs **inside KDE SDK 6.11**, which supplies Qt and the C/C++
toolchain used by simulations. It does not promise compatibility with an
arbitrary host distribution. x86_64 is supported initially.

## Inputs and traceability

`scripts/resolve.py` selects only OpenModelica's official release channel, then
reads the versioned Trixie package archive and Debian Trixie's package index.
Every `.deb` is checked against the index's SHA-256 and size before extraction.
No Debian maintainer scripts run.

The optional OMSens library also links Qt 5, so its three required Qt 5
libraries, double-conversion and md4c are included. These do not replace the
runtime's Qt 6 used by OMEdit.

Qt WebEngine comes from an exact Flathub commit of
`io.qt.qtwebengine.BaseApp//6.11`. The assembler verifies the installed commit,
copies the WebEngine Core/Widgets library dependency closure, its helper,
resources and six locales, and records hashes of the copied files. It does not
copy the complete BaseApp, its headers, Qt PDF, QML modules or development tools.
Only the STL and OBJ readers from Debian's OpenSceneGraph plugin collection are
included. The launcher sets their search path relative to the bundle.

The stable `libomccpp` package supplies the C++ simulation target, with matching
Debian Boost headers/libraries and the CPU OpenMP runtime. Its generated make
configuration uses relocatable bundle paths and the SDK's GCC flags. Boost
development tools and archives, LLVM and OpenMP offloading tools are excluded.

FMI/SSP schemas come from the same stable release's `omsimulator` package.
A relative link beside the embeddable library exposes its schema directory.
The standalone simulator executable and Python tools are not included.

Each archive and release includes `SOURCES` and `SOURCES.lock.json`, identifying
the original URLs, package versions/hashes, package-index hashes, BaseApp commit,
SDK commit and recipe hash. `QT-FILES.sha256` records individual Qt file hashes.
OpenModelica and Debian package copyright files are preserved in `usr/share/doc`.

OpenModelica source and licensing: https://github.com/OpenModelica/OpenModelica

Qt BaseApp source recipe and patches:
https://github.com/flathub/io.qt.qtwebengine.BaseApp/tree/branch/6.11

## Local build

Requires Python 3, `dpkg-deb`, `readelf`, GNU tar/gzip, Flatpak, and system-wide
Flathub. Install the BaseApp and KDE SDK 6.11. The installed commits must match
the generated lock (use `flatpak update --commit=...` if they differ).

```sh
mkdir -p build
python3 scripts/resolve.py > build/inputs.lock.json
python3 scripts/assemble.py build/inputs.lock.json build/omedit
flatpak run --unshare=network --filesystem="$PWD" --command=bash \
  org.kde.Sdk//6.11 "$PWD/scripts/verify.sh" "$PWD/build/omedit"
bash scripts/package.sh
```

The verifier checks every ELF executable/shared library for unresolved imports,
checks `omc --version`, and generates, compiles and runs a headless simulation
using the launchers' default compiler settings. The workflow repeats the checks
after extracting the finished archive at a different path.
It also checks C++ decay and event/reinitialization simulations numerically.
Valid and invalid FMI/SSP XML fixtures exercise the bundled schemas offline.

Within the runtime, run `omedit/bin/omedit` or `omedit/bin/omc`. The launchers set
resource/library paths relative to their own directory. The default Debian
compiler command names `clang` and `clang++` dispatch to the SDK's GCC toolchain.
Qt WebEngine's Flatpak sandbox remains enabled. Its helper launcher restores
the bundle's library environment after the portal launches a sandboxed child.

## Releases and dependency updates

Pushes and pull requests build and validate but do not publish. Run the release
workflow manually with `publish` enabled for the first public release. The daily
schedule then checks for upstream releases, changed Debian package hashes, new
BaseApp/SDK commits and recipe changes.

The version is `<upstream>-r<input-fingerprint>`. This includes rebuilds where
OpenModelica's version stays unchanged. Unrelated package-index changes do not
trigger rebuilds. Existing releases/assets are never overwritten. Scheduled
releases use the same validation gate as manual releases. The FlatPark resolver
reads this repository's latest release.

Before contributing a second architecture, resolve its own package indexes,
BaseApp and SDK commits and perform the same native validation. Do not reuse
x86_64 hashes or claim aarch64 support without that validation.
