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

"""Drive the live deployment and record it.

A real run against the deployed URL: real Gemini, real Parallel, real timings on
the crew rail. Nothing is mocked, because the crew rail showing 00:11 for a
model call is the most convincing thing in the video and a judge can tell when
that has been faked.

Writes `timings.json` — when each narration beat actually began, in seconds from
the start of the recording. The assembler places the audio against those, so an
agent run that takes longer today than yesterday shifts the voice-over with it
instead of drifting out of sync.

    uv run python tools/video/capture.py
    uv run python tools/video/capture.py --local     # against localhost:8080
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
OUT = HERE / "capture"
AUDIO = HERE / "audio"

PROD = "https://sceneroom-320877670799.us-central1.run.app"
# Published in docs/SUBMISSION.md so judges can open the room — a spend gate,
# not a secret. Still read from the environment so rotating it does not mean
# editing a script.
ACCESS_CODE = os.getenv("SCENEROOM_ACCESS_CODE", "jongno-1963-50f10b")

W, H = 1440, 900

BRIEF = (
    "Detective Park corners the informant she has been chasing since episode "
    "three, and has to decide whether to draw her weapon"
)
SETTING = "Seoul, 1963"
BIBLE = (
    "DETECTIVE PARK SUN-HEE carries a service revolver, never an automatic. "
    "She was issued badge 1887 in 1961 and has never lost it.\n"
    "The Jongno precinct has no radio room; all dispatch runs through the "
    "Euljiro switchboard.\n"
    "Episode 3 established that Park does not smoke."
)


def audio_seconds() -> dict[str, float]:
    manifest = json.loads((AUDIO / "manifest.json").read_text())
    return {m["id"]: m["seconds"] for m in manifest}


class Director:
    """Keeps the recording clock and logs when each beat starts."""

    def __init__(self, page, lengths: dict[str, float], t0: float | None = None) -> None:
        self.page = page
        self.lengths = lengths
        # The recording starts when the context is created, not when the first
        # beat does. Timing beats from later shifts every cut earlier by the
        # navigation and unlock time — invisible on beats with long holds, and
        # fatal on the frame beat, where the payoff is in the last seconds.
        self.t0 = t0 if t0 is not None else time.perf_counter()
        self.marks: list[dict] = []
        self._current: str | None = None

    def now(self) -> float:
        return time.perf_counter() - self.t0

    def beat(self, beat_id: str) -> None:
        """Start a beat. The previous one ends here."""
        self._current = beat_id
        self.marks.append({"id": beat_id, "start": round(self.now(), 3)})
        print(f"  {self.now():6.1f}s  ▶ {beat_id}")

    def hold(self, extra: float = 0.0) -> None:
        """Stay on this beat until its narration would have finished."""
        want = self.lengths.get(self._current, 4.0) + extra
        started = self.marks[-1]["start"]
        remaining = want - (self.now() - started)
        if remaining > 0:
            self.page.wait_for_timeout(int(remaining * 1000))

    def save(self) -> None:
        total = self.now()
        for i, m in enumerate(self.marks):
            end = self.marks[i + 1]["start"] if i + 1 < len(self.marks) else total
            m["end"] = round(end, 3)
        (OUT / "timings.json").write_text(
            json.dumps({"total": round(total, 3), "beats": self.marks}, indent=2)
        )
        print(f"\nrecorded {total:.1f}s across {len(self.marks)} beats")


def run(base: str, headed: bool) -> int:
    OUT.mkdir(exist_ok=True)
    lengths = audio_seconds()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        ctx = browser.new_context(
            viewport={"width": W, "height": H},
            record_video_dir=str(OUT),
            record_video_size={"width": W, "height": H},
            device_scale_factor=2,          # crisp text when scaled for upload
        )
        page = ctx.new_page()
        recording_started = time.perf_counter()   # the video clock's zero
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(base, wait_until="networkidle")
        if page.is_visible("#gate"):
            page.fill("#gateCode", ACCESS_CODE)
            page.click("#gateForm button")
            page.wait_for_timeout(1200)

        d = Director(page, lengths, t0=recording_started)

        # 1 — the cold open: the problem, the edge, the shape of a pass, and
        # where evidence comes from. All four are cards or the sequence
        # diagram; the empty room is not the shot for any of them.
        for opener in ("problem", "edge", "walkthrough", "parallel"):
            d.beat(opener)
            d.hold()

        # 2 — the brief, typed for real so it reads as a person working.
        d.beat("brief")
        page.click("#intent")
        page.fill("#intent", "")
        page.type("#intent", BRIEF, delay=18)
        page.fill("#setting", SETTING)
        page.click("details.bible summary")
        page.type("#bible", BIBLE, delay=6)
        d.hold()

        # 3 — the crew starts. This is the ~40s wait, and it is the proof.
        d.beat("crew-start")
        page.click("#go")
        page.wait_for_selector("li.running", timeout=90_000)
        d.hold()

        d.beat("crew-checks")
        d.hold()

        d.beat("continuity")
        page.wait_for_selector(".note", timeout=600_000)   # the run finishes here
        page.wait_for_timeout(1200)
        # Show the canon conflict if the run produced one.
        canon = page.locator('.note:has(.kind:text-matches("canon", "i"))')
        if canon.count():
            canon.first.click()
            page.wait_for_timeout(900)
        d.hold()

        # 4 — flags on the page, and the bridge.
        d.beat("flags")
        spans = page.locator(".span")
        if spans.count() > 1:
            spans.nth(1).click()
            page.wait_for_timeout(900)
        d.hold()

        d.beat("rights")
        rights = page.locator('.note:has(.kind:text-matches("rights", "i"))')
        if rights.count():
            rights.first.click()
            page.wait_for_timeout(900)
        d.hold()

        # 5 — the beat the whole video exists for.
        d.beat("contested")
        contested = page.locator(".note.contested")
        if contested.count():
            contested.first.click()
            page.wait_for_timeout(900)
            contested.first.scroll_into_view_if_needed()
        d.hold()

        # 6 — the decision.
        d.beat("decide")
        keep = page.locator(".note.open .keep")
        if keep.count():
            keep.first.click()
            page.wait_for_selector("textarea[id^=rt-]", timeout=15_000)
            page.type("textarea[id^=rt-]",
                      "Deliberate: the beat needs the weapon in frame.", delay=22)
            page.wait_for_timeout(600)
            page.locator("button[id^=rc-]").first.click()
            page.wait_for_selector(".decided-mark", timeout=300_000)
        d.hold()

        # Clear whatever is still open, so the frame can be offered.
        #
        # A card must be opened before its buttons can be clicked: the deck
        # collapses everything but the selected card, so `.note .keep` exists in
        # the DOM and is not visible, and clicking it waits forever.
        for _ in range(8):
            pending = page.locator(".note:not(:has(.decided-mark)):has(.keep)")
            if not pending.count():
                break
            card = pending.first
            try:
                card.click()                       # open it
                page.wait_for_timeout(400)
                page.locator(".note.open .keep").first.click(timeout=8_000)
                page.wait_for_selector("textarea[id^=rt-]", timeout=8_000)
                page.fill("textarea[id^=rt-]", "Deliberate period licence.")
                page.locator("button[id^=rc-]").first.click()
                page.wait_for_timeout(2200)
            except Exception as exc:
                print(f"    (stopped clearing: {str(exc)[:80]})")
                break

        # 7 — the ledger, then the record as a document.
        d.beat("ledger")
        page.locator(".ledger").scroll_into_view_if_needed()
        page.wait_for_timeout(1500)
        d.hold()

        # 8 — the eval. Shown as the terminal output, not the app.
        d.beat("eval")
        d.hold()

        # 10 — the payoff frame.
        d.beat("frame")
        # Back to the top: the ledger beat scrolled away, and the button lives
        # in the stage header. An earlier cut filmed nothing here.
        page.evaluate("window.scrollTo({top: 0})")
        page.wait_for_timeout(600)
        btn = page.locator("#frameBtn")
        print(f"    frame button: count={btn.count()} visible={btn.is_visible() if btn.count() else False}")
        if btn.count() and btn.is_visible():
            btn.click()
            try:
                # The image, not the container. Waiting on the wrapper returned
                # before the picture existed and the beat ended on "Rendering...",
                # which is the one shot in the video that has to land.
                page.wait_for_function(
                    "() => { const i = document.getElementById('frameImg');"
                    "        return i && i.src && i.src.startsWith('data:'); }",
                    timeout=300_000,
                )
                page.locator("#frameImg").scroll_into_view_if_needed()
                page.wait_for_timeout(3500)   # hold on it; this is the payoff
                print("    frame rendered")
            except Exception as exc:  # the frame is the first thing we cut
                print(f"    (frame skipped: {str(exc)[:90]})")
        d.hold()

        d.beat("close")
        d.hold()

        d.save()
        video = page.video.path() if page.video else None
        ctx.close()          # video is only flushed on context close
        browser.close()

        if video:
            final = OUT / "screen.webm"
            pathlib.Path(video).replace(final)
            print(f"video: {final}")
        if errors:
            print(f"console errors: {errors}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()
    raise SystemExit(run("http://localhost:8080" if a.local else PROD, a.headed))
