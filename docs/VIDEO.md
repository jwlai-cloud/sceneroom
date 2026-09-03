# Demo video — shot plan

**Runtime target 2:50.** Pre-recorded; the hosted URL stays live separately, so
nothing here depends on a live call surviving judging.

**The one thing a judge must remember:** *it refused to decide, and said who
should.* Everything else is setup for that beat.

## Before recording

- [ ] Confirm `PARALLEL_PROCESSOR=base` (what production runs — `pro` scores
      higher and rules on contested history, which the film says we never do).
- [ ] Do a throwaway run first — Cloud Run cold start adds 5–15s to the first
      hit and you do not want that in take one.
- [ ] Browser at 1500×950, **Night** theme, zoom 100%.
- [ ] Hide bookmarks bar. Clear the recent-scenes panel or accept it as
      evidence the ledger persists — it reads well either way.
- [ ] Have the Joseon brief ready: it is the one that reliably produces
      `contested`.

## The cut

| # | Time | On screen | Narration |
|---|---|---|---|
| 1 | 0:00–0:16 | The MBC headline, then the apology story. Hold. | "In June, a Korean drama apologised on air and cut scenes after viewers caught historical errors the production missed. The errors weren't the problem. Nobody could tell which deviations were deliberate." |
| 2 | 0:16–0:30 | Sceneroom, empty. Type the brief: *A scholar notices a court record has been altered.* Setting: Joseon, 1443. | "Sceneroom is a scene room for scripted production. A writer gives an intent." |
| 3 | 0:30–0:52 | **Click Run the crew.** Stay on the crew rail. Let it run — do not cut. | "Seven agents. The writer drafts. The extractor pulls out every checkable claim. Continuity checks the production bible. Then three agents ask three different questions." |
| 4 | 0:52–1:05 | Crew rail continues; Verifier and Fandom tick over with real timings. | "The verifier asks whether it's true — against the live web, through Parallel. Rights asks whether using it needs permission. And the fandom agent asks something else entirely: what has this audience already litigated?" |
| 5 | 1:05–1:20 | Scene page fills in. Underlined spans. **Click one** — the bridge draws to its note. | "Flags land inline on the page. Every one is linked to its note and its sources." |
| 6 | 1:20–1:45 | **The contested flag.** Zoom the amber block: *"Sources disagree — the crew will not pick a side."* Then the routing line. | "This one is different. Credible sources actively disagree. The system doesn't pick a side — it says so, states both positions, and routes it to a human. An agent that knows the limit of its own authority is worth more than one claiming omniscience." |
| 7 | 1:45–2:05 | A `contradicted` flag. **Click Keep — deliberate.** Type a rationale. Record it. | "Not every deviation is a mistake. Bridgerton is anachronistic on purpose. So keeping something is a supported answer — the choice is logged, with the real fact beside it." |
| 8 | 2:05–2:20 | Ledger strip fills. Cut to the BigQuery console: same rows. | "Every verdict, decision and rationale is appended to BigQuery. Append-only, because a record you can edit isn't provenance." |
| 9 | 2:20–2:32 | Click **Download the record**. Show the Markdown. | "When a controversy lands, this is what the studio produces: what was checked, against which source, decided by whom, and why." |
| 10 | 2:32–2:45 | **Render the frame.** The still appears. | "And the scene you can actually shoot." |
| 11 | 2:45–2:50 | Hold on the frame. Text: *no unreviewed claim ships.* | "It doesn't promise the scene is correct. It promises no claim shipped unreviewed." |

## Beat 10 is the payoff — say this if there's room

The frame shows the detective holding the handie-talkie: the anachronism the
writer chose to **keep**. The picture shows the deliberate choice; the ledger
says why. That's the whole product in one image.

## Direction notes

- **Do not cut the 30-second run.** It is the proof the system is multi-step,
  and the crew rail with real timings is the most convincing thing on screen.
  Narrate over it (beats 3–4) rather than speeding it up. If you must compress,
  ramp to 1.5× and keep the timings legible.
- **Zoom on beat 6, not beat 5.** The contested block is the memorable frame.
- **Never say "AI fact-checker."** Say *scene room*, *system of record*, *no
  unreviewed claim ships*.
- **Show the offline banner never.** If `PARALLEL LIVE` isn't green, stop and
  fix it before recording — the whole track depends on that being live.

## Capture

Playwright drives the page for real motion and real backend calls (see
`hackathon-demo-video`), or record the screen directly. Either way the run must
be a genuine one: the timings on the crew rail are real, and a judge who has
seen a hundred demos can tell.
