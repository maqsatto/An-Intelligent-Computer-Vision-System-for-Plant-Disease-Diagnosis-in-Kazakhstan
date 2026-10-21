"""Explicitly select an integrity-checked local research bundle; production still refuses it."""

import argparse
from pathlib import Path

from agrovision_runtime import validate_research_bundle

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("directory", type=Path)
args = parser.parse_args()
bundle = validate_research_bundle(args.directory)
path = Path(".env")
if not path.exists():
    raise SystemExit("Run python scripts/setup_local.py first")
lines = [
    line
    for line in path.read_text().splitlines()
    if not line.startswith(("AGRO_ENVIRONMENT=", "AGRO_DEV_PREDICTOR=", "AGRO_RESEARCH_BUNDLE_DIR="))
]
lines += [
    "AGRO_ENVIRONMENT=development",
    "AGRO_DEV_PREDICTOR=false",
    "AGRO_RESEARCH_BUNDLE_DIR=" + str(bundle.directory),
]
path.write_text("\n".join(lines) + "\n")
path.chmod(0o600)
print(
    f"Selected research bundle {bundle.manifest['version']}. Restart API/worker; all outcomes remain inconclusive."
)
