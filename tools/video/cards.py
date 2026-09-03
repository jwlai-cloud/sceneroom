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

"""Footage for the beats the app cannot show.

Three of them were playing over the console while the voice talked about
something else — a quarter of the runtime doing nothing:

- **problem** — twenty-one seconds of an empty page under the opening.
- **eval** — the strongest engineering story in the video, told over a UI that
  has nothing to do with it.
- **architecture** — same.

Each is captured as its own clip and the assembler prefers it over the screen
recording. The eval card shows the real numbers from `evals/run_eval.py`; the
architecture clip drives the real topology diagram.

    uv run --with playwright python tools/video/cards.py
"""

from __future__ import annotations

import pathlib

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
OUT = HERE / "capture" / "aux"
SEQUENCE = HERE.parent.parent / "docs" / "sceneroom-run.html"

W, H = 1440, 900

SHELL = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Courier+Prime:wght@400;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&display=swap');
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    width:1440px; height:900px; overflow:hidden;
    background:#12100f; color:#ece8e4;
    font-family:'Source Serif 4',Georgia,serif;
    display:grid; place-items:center;
    background-image:
      radial-gradient(120%% 90%% at 12%% -10%%, rgba(56,166,207,.13), transparent 60%%),
      radial-gradient(90%% 80%% at 100%% 0%%, rgba(237,187,0,.09), transparent 55%%);
  }
  .wrap { width:1060px; }
  .eyebrow { font-family:'Courier Prime',monospace; font-size:12px; letter-spacing:.22em;
             text-transform:uppercase; color:#7d7979; font-weight:700; }
  h1 { font-size:52px; line-height:1.12; font-weight:600; margin:18px 0 20px; letter-spacing:-.01em; }
  p  { font-size:21px; line-height:1.5; color:#9b9797; max-width:860px; }
  .rule { height:1px; background:#2d2b2b; margin:26px 0; }
  .mono { font-family:'Courier Prime',monospace; }
  .amber { color:#edbb00; } .flag { color:#ff458e; } .live { color:#38a6cf; }
</style>
"""

PROBLEM = SHELL + """
<div class="wrap">
  <span class="eyebrow">Seoul · June 2026</span>
  <h1>A drama apologised on air,<br>and cut scenes after broadcast.</h1>
  <div class="rule"></div>
  <p>Viewers had caught historical errors the production missed.</p>
  <p style="margin-top:14px;color:#ece8e4">
    The errors were not the real problem. Nobody could tell which deviations
    were <em>deliberate</em>.</p>
</div>
"""

EDGE = SHELL + """
<style>
  .cols { display:grid; grid-template-columns:1fr 1fr; gap:0; margin-top:26px;
          border:1px solid #2d2b2b; border-radius:3px; overflow:hidden; }
  .col { padding:24px 26px; }
  .col + .col { border-left:1px solid #2d2b2b; background:rgba(56,166,207,.05); }
  .col h2 { font-family:'Courier Prime',monospace; font-size:12px; letter-spacing:.2em;
            text-transform:uppercase; font-weight:700; margin-bottom:14px; }
  .col li { font-size:19px; line-height:1.55; color:#9b9797; list-style:none; margin-bottom:9px; }
  .col li b { color:#ece8e4; font-weight:600; }
</style>
<div class="wrap">
  <span class="eyebrow">What everyone builds &middot; what nobody ships</span>
  <h1>Checking a claim is the commodity.<br>The <em>record</em> is the product.</h1>
  <div class="cols">
    <div class="col">
      <h2 style="color:#7d7979">Any model with search</h2>
      <li>Tells you a claim looks wrong</li>
      <li>Rules on it, including disputes</li>
      <li>Leaves nothing behind</li>
    </div>
    <div class="col">
      <h2 class="live">Sceneroom</h2>
      <li><b>Writes the scene</b>, then makes it prove itself</li>
      <li><b>Refuses to rule</b> on contested history &mdash; routes it</li>
      <li><b>Appends every call</b>: source, decider, reason</li>
    </div>
  </div>
</div>
"""

# The real output of `uv run python evals/run_eval.py --compare`, before and
# after the instruction fix. Nothing here is invented.
EVAL = SHELL + """
<style>
  .term { background:#0d0c0b; border:1px solid #2d2b2b; border-radius:3px;
          padding:26px 30px; box-shadow:16px 20px 0 rgba(0,0,0,.34); }
  .term .cmd { color:#38a6cf; font-size:17px; margin-bottom:18px; }
  table { width:100%; border-collapse:collapse; font-size:19px; }
  td { padding:9px 10px; border-bottom:1px solid #1f1e1d; }
  td.n { text-align:right; font-variant-numeric:tabular-nums; }
  .lbl { color:#9b9797; } .hi { color:#ece8e4; font-weight:700; }
  .note { margin-top:20px; font-size:18px; color:#9b9797; }
</style>
<div class="wrap">
  <span class="eyebrow">Evaluation · 15 claims with known answers</span>
  <div class="term mono" style="margin-top:16px">
    <div class="cmd">$ uv run python evals/run_eval.py --compare</div>
    <table>
      <tr><td class="lbl">processor</td><td class="n lbl">correct</td>
          <td class="n lbl">missed</td><td class="n lbl">wrong</td></tr>
      <tr><td class="hi">base &nbsp;<span class="live">— shipped</span></td>
          <td class="n hi">9 / 15</td>
          <td class="n amber">6</td><td class="n live">0</td></tr>
      <tr><td class="hi">pro</td><td class="n hi">11 / 15</td>
          <td class="n amber">3</td><td class="n flag">1 &nbsp;←</td></tr>
    </table>
  </div>
  <p class="note">
    <span class="flag mono">1 wrong</span> — it ruled on whether Sejong invented
    Hangul unaided. Specialists genuinely disagree.<br>
    That is the one thing this system must never do.
  </p>
</div>
"""


def shot(page, html: str, path: pathlib.Path, seconds: float) -> None:
    page.set_content(html)
    page.wait_for_timeout(600)
    page.wait_for_timeout(int(seconds * 1000))
    print(f"  {path.name}")


def record(browser, name: str, seconds: float, drive) -> None:
    """Record one aux shot. `drive` gets the page and does whatever it needs."""
    ctx = browser.new_context(
        viewport={"width": W, "height": H},
        record_video_dir=str(OUT), record_video_size={"width": W, "height": H},
        device_scale_factor=2)
    page = ctx.new_page()
    drive(page)
    page.wait_for_timeout(int(seconds * 1000))
    video = page.video.path()
    ctx.close()
    pathlib.Path(video).replace(OUT / f"{name}.webm")
    print(f"  {name}.webm")


def diagram(page, views: tuple[str, ...], each: int) -> None:
    """Open the sequence diagram and step it through its own guided views."""
    page.goto(f"file://{SEQUENCE}", wait_until="networkidle")
    page.wait_for_timeout(2000)
    # The diagram opens light; the rest of the film is dark, and a white flash
    # mid-cut reads as a different product. Toggle until it agrees.
    for _ in range(3):
        if page.evaluate("document.documentElement.getAttribute('data-theme')") == "dark":
            break
        page.click("#btn-theme")
        page.wait_for_timeout(700)
    else:
        print("  (theme stayed light)")
    page.wait_for_timeout(800)
    for label in views:
        b = page.locator("button").filter(has_text=label)
        if b.count():
            b.first.click()
        else:
            print(f"  (no view button for {label!r})")
        page.wait_for_timeout(each)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()

        for beat, html, secs in (
            ("problem", PROBLEM, 20),
            ("edge", EDGE, 22),
            ("eval", EVAL, 24),
        ):
            record(browser, beat, secs, lambda pg, h=html: pg.set_content(h))

        # The walkthrough is the whole pass; the Parallel beat is the one view
        # that shows where evidence actually comes from.
        record(browser, "walkthrough", 2,
               lambda pg: diagram(pg, ("Draft and extract", "The human decision"), 9000))
        record(browser, "parallel", 2,
               lambda pg: diagram(pg, ("Where evidence comes from",), 18000))

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
