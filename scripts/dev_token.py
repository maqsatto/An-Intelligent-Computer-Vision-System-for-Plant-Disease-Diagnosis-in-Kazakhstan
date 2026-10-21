"""Issue an explicit development bearer, optionally to a private local file."""

import argparse
from pathlib import Path

from agrovision.config import get_settings
from agrovision.identity.auth import create_dev_token

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--subject", default="demo-user")
parser.add_argument("--output", type=Path)
args = parser.parse_args()
token = create_dev_token(get_settings(), args.subject)
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(token + "\n")
    args.output.chmod(0o600)
    print(f"Wrote private development token to {args.output}")
else:
    print(token)
