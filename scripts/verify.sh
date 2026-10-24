#!/usr/bin/env bash
# Run inside org.kde.Sdk//6.11, with only the unpacked bundle on the app path.
set -euo pipefail
bundle_dir="$(realpath "${1:?usage: verify.sh /path/to/omedit}")"
. "$bundle_dir/libexec/environment"
failed=0
checked=0
while IFS= read -r -d '' path; do
    # Only ELF executables/shared objects. Archives containing ELF object files
    # are deliberately skipped; the simulation test exercises their linkage.
    magic="$(od -An -tx1 -N4 "$path" | tr -d ' \n')"
    [ "$magic" = 7f454c46 ] || continue
    type="$(readelf -h "$path" | awk '/Type:/{print $2}')"
    case "$type" in EXEC|DYN) ;; *) continue ;; esac
    checked=$((checked + 1))
    output="$(ldd "$path" 2>&1)" || {
        if ! grep -Eq 'not a dynamic executable|statically linked' <<<"$output"; then
            printf '%s\n%s\n' "$path" "$output" >&2
            failed=1
        fi
    }
    if grep -q 'not found' <<<"$output"; then
        printf '%s\n%s\n' "$path" "$output" >&2
        failed=1
    fi
done < <(find "$bundle_dir" -type f -print0)
[ "$checked" -gt 0 ] && [ "$failed" -eq 0 ]
echo "All $checked ELF binaries/shared libraries have their dependencies."
version="$(omc --version)"
expected="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["upstream_version"])' "$bundle_dir/SOURCES.lock.json")"
grep -F "OpenModelica $expected" <<<"$version"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work"
cat > smoke.mos <<'EOF'
loadString("model Decay Real x(start=1, fixed=true); equation der(x)=-x; end Decay;");
simulate(Decay, stopTime=1.0, numberOfIntervals=100);
getErrorString();
EOF
omc smoke.mos | tee simulation.log
grep -F 'The simulation finished successfully.' simulation.log
test -s Decay_res.mat
echo 'Headless simulation passed using the bundle defaults.'
