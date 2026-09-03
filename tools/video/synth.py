# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Narration audio, one file per beat, via Cloud Text-to-Speech.

Chirp3-HD by default — the voices that do not sound like a screen reader.

Per beat rather than one long file, because the video is cut to the audio: each
beat's real duration decides how long its shot stays up, so a sentence is never
clipped mid-word.

    uv run python tools/video/synth.py                 # synthesise
    uv run python tools/video/synth.py --list-voices   # audition candidates

Run it with `env -u GOOGLE_APPLICATION_CREDENTIALS`, or ADC resolves to the
TrafficGuard service account in the shell profile and this 403s.
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import subprocess
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from narration import BEATS

OUT = pathlib.Path(__file__).parent / "audio"
PROJECT = "agent-era"
ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"

# Charon is the steadiest of the Chirp3 voices for documentary narration —
# lower, unhurried, no upward inflection at the end of statements.
VOICE = "en-US-Chirp3-HD-Charon"
CANDIDATES = [
    "en-US-Chirp3-HD-Charon",
    "en-US-Chirp3-HD-Algenib",
    "en-US-Chirp3-HD-Achernar",
    "en-US-Studio-Q",
]


def token() -> str:
    import google.auth
    from google.auth.transport.requests import Request

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    return creds.token


def synth(text: str, voice: str, tok: str) -> bytes:
    body = {
        "input": {"text": text},
        "voice": {"languageCode": "en-US", "name": voice},
        # Slightly under normal pace: the script is dense, and these voices
        # stay intelligible when slowed but get muddy when pushed faster.
        "audioConfig": {"audioEncoding": "MP3", "speakingRate": 0.99},
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {tok}",
            "x-goog-user-project": PROJECT,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return base64.b64decode(json.load(r)["audioContent"])


def duration(path: pathlib.Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default=VOICE)
    ap.add_argument("--list-voices", action="store_true",
                    help="synthesise one line in each candidate voice, to audition")
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    tok = token()

    if args.list_voices:
        line = ("The system refuses to rule. It states both positions, "
                "and routes it to a named human.")
        for v in CANDIDATES:
            p = OUT / f"_audition-{v}.mp3"
            p.write_bytes(synth(line, v, tok))
            print(f"  {v}  ->  {p}")
        return 0

    total = 0.0
    manifest = []
    for beat in BEATS:
        path = OUT / f"{beat['id']}.mp3"
        path.write_bytes(synth(beat["text"], args.voice, tok))
        secs = duration(path)
        total += secs
        manifest.append({"id": beat["id"], "seconds": round(secs, 2), "hold": beat["hold"]})
        print(f"  {beat['id']:<14} {secs:>5.1f}s")

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    mins, secs = divmod(total, 60)
    print(f"\ntotal narration: {int(mins)}:{secs:04.1f}  ({args.voice})")
    if total > 175:
        print("OVER BUDGET for a 3-minute cut — trim narration.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
