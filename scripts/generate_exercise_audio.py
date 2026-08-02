#!/usr/bin/env python3
"""Generate versioned exercise cue audio and a browser-readable manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SPEECH_ENDPOINT = "https://api.openai.com/v1/audio/speech"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "static/exercises/audio/prompts.json"
DEFAULT_OUTPUT = REPO_ROOT / "static/exercises/audio"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def content_hash(config: dict[str, object], text: str) -> str:
    payload = json.dumps(
        {
            "model": config["model"],
            "voice": config["voice"],
            "response_format": config["response_format"],
            "speed": config["speed"],
            "text": text,
        },
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def request_audio(api_key: str, config: dict[str, object], text: str) -> bytes:
    body = json.dumps(
        {
            "model": config["model"],
            "voice": config["voice"],
            "input": text,
            "response_format": config["response_format"],
            "speed": config["speed"],
        }
    ).encode("utf-8")
    request = Request(
        SPEECH_ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "FengDock-exercise-audio-generator/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            audio = response.read()
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Speech API returned HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Speech API request failed: {error.reason}") from error
    if len(audio) < 256:
        raise RuntimeError("Speech API returned an unexpectedly small audio file")
    return audio


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required")

    config = json.loads(args.source.read_text(encoding="utf-8"))
    cues = config.get("cues")
    if not isinstance(cues, dict) or not cues:
        raise SystemExit("prompts.json must contain a non-empty cues object")

    manifest_cues: dict[str, dict[str, str]] = {}
    generated = 0
    for cue_id, text in cues.items():
        if not isinstance(cue_id, str) or not isinstance(text, str) or not text.strip():
            raise SystemExit(f"Invalid cue entry: {cue_id!r}")
        digest = content_hash(config, text)
        extension = str(config["response_format"])
        filename = f"{cue_id}.{digest[:12]}.{extension}"
        target = args.output / filename
        if not target.exists():
            print(f"Generating {cue_id}...")
            atomic_write(target, request_audio(api_key, config, text))
            generated += 1
            time.sleep(0.08)
        manifest_cues[cue_id] = {
            "file": filename,
            "text": text,
            "sha256": digest,
        }

    manifest = {
        "version": max((cue["sha256"] for cue in manifest_cues.values()), default="")[:12],
        "language": config["language"],
        "model": config["model"],
        "voice": config["voice"],
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cues": manifest_cues,
    }
    atomic_write(
        args.output / "manifest.json",
        (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
    )
    print(f"Audio pack ready: {len(manifest_cues)} cues ({generated} generated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
