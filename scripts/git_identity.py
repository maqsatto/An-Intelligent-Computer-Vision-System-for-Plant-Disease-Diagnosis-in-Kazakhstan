#!/usr/bin/env python3
"""Select a repository-local Git author for that person's own changes."""

import argparse
import subprocess

PROFILES = {
    "owner": ("maqsatto", "m.syrtbay@outlook.com"),
    "friend": ("v2207function", "kaiz.almaz.01@mail.ru"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=PROFILES)
    args = parser.parse_args()
    subprocess.run(["git", "rev-parse", "--show-toplevel"], check=True, capture_output=True)
    name, email = PROFILES[args.profile]
    subprocess.run(["git", "config", "--local", "user.name", name], check=True)
    subprocess.run(["git", "config", "--local", "user.email", email], check=True)
    print(f"Repository author: {name} <{email}>. Global configuration is unchanged.")


if __name__ == "__main__":
    main()
