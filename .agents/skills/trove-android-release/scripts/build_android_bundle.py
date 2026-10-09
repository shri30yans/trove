#!/usr/bin/env python3
# ruff: noqa: T201
"""Build and verify a signed Trove Android App Bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
MOBILE_ROOT = REPO_ROOT / "mobile"
ENV_CREDENTIAL_KEYS = {
    "TROVE_UPLOAD_KEYSTORE": "Keystore",
    "TROVE_UPLOAD_ALIAS": "Alias",
    "TROVE_UPLOAD_STORE_PASSWORD": "Store password",
    "TROVE_UPLOAD_KEY_PASSWORD": "Key password",
}


class BuildError(Exception):
    """An actionable local release build error."""


def load_credentials(explicit_path: str | None) -> dict[str, str]:
    env_values = {key: os.environ.get(key, "") for key in ENV_CREDENTIAL_KEYS}
    credentials_path = explicit_path or os.environ.get("TROVE_UPLOAD_CREDENTIALS_FILE")
    if not credentials_path:
        macos_path = (
            Path.home()
            / "Library/Application Support/TroveApp/play-upload/credentials.txt"
        )
        if macos_path.is_file():
            credentials_path = str(macos_path)

    if credentials_path:
        path = Path(credentials_path).expanduser().resolve()
        try:
            metadata = path.stat()
        except OSError as error:
            raise BuildError(f"Cannot read the upload credential file: {path}") from error
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise BuildError(
                "The upload credential file must belong to this user and have no group/other permissions. "
                "Run chmod 600 on the file."
            )
        parsed: dict[str, str] = {}
        for line in path.read_text().splitlines():
            if ": " in line:
                name, value = line.split(": ", 1)
                parsed[name] = value
        credentials = {key: parsed.get(label, "") for key, label in ENV_CREDENTIAL_KEYS.items()}
    else:
        credentials = env_values

    missing = [key for key, value in credentials.items() if not value]
    if missing:
        raise BuildError(
            "Upload signing credentials are missing. Set TROVE_UPLOAD_CREDENTIALS_FILE "
            "to a private credential file or provide all four TROVE_UPLOAD_* environment variables."
        )
    credentials["TROVE_UPLOAD_KEYSTORE"] = str(
        Path(credentials["TROVE_UPLOAD_KEYSTORE"]).expanduser().resolve()
    )
    keystore = Path(credentials["TROVE_UPLOAD_KEYSTORE"])
    if not keystore.is_file():
        raise BuildError(f"Upload keystore does not exist: {keystore}")
    return credentials


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env=env,
            check=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise BuildError(f"Required build tool was not found: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        raise BuildError(
            f"Build command failed with exit code {error.returncode}: {command[0]}"
        ) from error


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_bundle(bundle: Path, credentials: dict[str, str], env: dict[str, str]) -> None:
    verify = subprocess.run(
        ["jarsigner", "-verify", str(bundle)], capture_output=True, text=True, env=env, check=False
    )
    if verify.returncode != 0 or "jar verified." not in verify.stdout.lower():
        raise BuildError("The generated AAB did not pass jarsigner verification.")

    fingerprint = subprocess.run(
        [
            "keytool",
            "-exportcert",
            "-keystore",
            credentials["TROVE_UPLOAD_KEYSTORE"],
            "-alias",
            credentials["TROVE_UPLOAD_ALIAS"],
            "-storepass:env",
            "TROVE_UPLOAD_STORE_PASSWORD",
        ],
        capture_output=True,
        env=env,
        check=True,
    )
    expected = sha256(fingerprint.stdout)
    certificate = subprocess.run(
        ["keytool", "-printcert", "-jarfile", str(bundle)],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    fingerprints = re.findall(
        r"SHA256:\s*((?:[0-9A-Fa-f]{2}:){31}[0-9A-Fa-f]{2})", certificate.stdout
    )
    actual = {value.replace(":", "").lower() for value in fingerprints}
    if expected not in actual:
        raise BuildError("AAB signer does not match the configured Play upload keystore.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--credentials-file",
        help="Private file containing Keystore, Alias, Store password, and Key password entries.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "artifacts",
        help="Where to copy the verified AAB (default: repository artifacts/).",
    )
    args = parser.parse_args()

    try:
        credentials = load_credentials(args.credentials_file)
        config = json.loads((MOBILE_ROOT / "app.json").read_text())["expo"]
        version = config["version"]
        android = config.get("android", {})
        package_name = android.get("package")
        if not isinstance(package_name, str) or not re.fullmatch(
            r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+", package_name
        ):
            raise BuildError(
                f"Invalid Android package ID {package_name!r}; use lowercase package segments."
            )
        version_code = android.get("versionCode", 1)
        if not isinstance(version_code, int) or version_code < 1:
            raise BuildError("android.versionCode in mobile/app.json must be a positive integer.")

        output_dir = args.output_dir.expanduser().resolve()
        output = output_dir / f"Trove-{version}-{version_code}.aab"
        if output.exists():
            raise BuildError(f"Refusing to overwrite existing bundle: {output}")

        env = os.environ.copy()
        env["NODE_ENV"] = "production"
        env.update(credentials)
        env.update(
            {
                "ORG_GRADLE_PROJECT_android.injected.signing.store.file": credentials[
                    "TROVE_UPLOAD_KEYSTORE"
                ],
                "ORG_GRADLE_PROJECT_android.injected.signing.store.password": credentials[
                    "TROVE_UPLOAD_STORE_PASSWORD"
                ],
                "ORG_GRADLE_PROJECT_android.injected.signing.key.alias": credentials[
                    "TROVE_UPLOAD_ALIAS"
                ],
                "ORG_GRADLE_PROJECT_android.injected.signing.key.password": credentials[
                    "TROVE_UPLOAD_KEY_PASSWORD"
                ],
            }
        )

        android_root = MOBILE_ROOT / "android"
        prebuild = ["npx", "expo", "prebuild", "--platform", "android", "--no-install"]
        generated_gradle = android_root / "app/build.gradle"
        if generated_gradle.is_file():
            generated = generated_gradle.read_text()
            match = re.search(r"applicationId\s+['\"]([^'\"]+)['\"]", generated)
            if match and match.group(1) != package_name:
                prebuild.insert(-1, "--clean")
        run(prebuild, cwd=MOBILE_ROOT, env=env)
        gradlew = android_root / "gradlew"
        run([str(gradlew), ":app:bundleRelease", "--no-daemon"], cwd=android_root, env=env)

        bundle = android_root / "app/build/outputs/bundle/release/app-release.aab"
        if not bundle.is_file() or bundle.stat().st_size == 0:
            raise BuildError("Gradle completed without producing the expected release AAB.")
        verify_bundle(bundle, credentials, env)

        output_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundle, output)
        if sha256(bundle.read_bytes()) != sha256(output.read_bytes()):
            output.unlink(missing_ok=True)
            raise BuildError("Copied AAB checksum did not match the build output.")
        print(f"Verified Android App Bundle: {output}")
        print(f"Package: {package_name}; version: {version}; versionCode: {version_code}")
        return 0
    except (BuildError, KeyError, json.JSONDecodeError, OSError, subprocess.CalledProcessError) as error:
        print(f"Android bundle build failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
