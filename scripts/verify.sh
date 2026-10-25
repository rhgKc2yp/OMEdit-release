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

cat > cpp.mos <<'EOF'
setCommandLineOptions("--simCodeTarget=Cpp");
loadString("model CppDecay Real x(start=1,fixed=true); equation der(x)=-x; end CppDecay;");
simulate(CppDecay,stopTime=1,numberOfIntervals=100,outputFormat="csv");
getErrorString();
loadString("model CppEvent Real x(start=1,fixed=true); equation der(x)=-1; when x < 0 then reinit(x,1); end when; end CppEvent;");
simulate(CppEvent,stopTime=2.5,numberOfIntervals=250,outputFormat="csv");
getErrorString();
EOF
omc cpp.mos | tee cpp.log
python3 - <<'PY'
import csv
import math
for model, expected in [("CppDecay", math.exp(-1)), ("CppEvent", 0.5)]:
    with open(f"{model}_res.csv") as stream:
        rows = list(csv.DictReader(stream))
    value = float(rows[-1]["x"])
    # The C++ target prints CSV values with limited decimal precision.
    assert abs(value - expected) < 2e-5, (model, value, expected)
    print(f"{model}: x(final)={value}, expected={expected}")
PY
echo 'C++ simulation and event/reinitialization checks passed.'
