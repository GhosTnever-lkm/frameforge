# FrameForge — project state

Updated: 2026-10-09

## Current version

- Published: v1.2.0, cross-game frame-budget reporting.
- Local v1.2.0 checks: 88 unit tests pass; 4 platform-dependent symlink tests are skipped; compileall, diff check and offscreen GUI smoke pass.
- GitHub Actions run [37869046502](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37869046502) passed tests, Windows portable build and startup smoke.
- Published archive: [FrameForge v1.2.0](https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.2.0), `FrameForge-1.2.0-windows-x64.zip`; SHA-256 `66fbef54b64881b252890330a24f3a886d7d02a9a04b837002b6b6e2a9c57ac4`.
- Downloaded release archive, verified its SHA-256, extracted it and launched `FrameForge.exe`; the window title was `FrameForge — Game Tuning Studio` and the process responded.
- DeepSeek reviewed v1.2.0 and found no blockers in the described scope.
- Portfolio last published card: v1.1.0; update it after the v1.3.0 release is verified.

## v1.2.0 behavior

- Stores seven overlapping aggregate frame-budget counts at CSV import for the supported FPS presets; raw frame samples remain discarded.
- Shows the selected threshold in A/B and repeated-run reports; old history migrates to schema v8 with an explicit unavailable value.
- Keeps single and group exports aggregate-only and includes the selected target.

## Work in progress: v1.3.0

- Multi-select benchmark CSV import applies one shared game/scene/checklist context, saves valid selections as a single bounded batch, and reports per-file failures.
- Keeps history aligned with the newest 100 runs in memory and on disk; removes group references to evicted runs and validates minimum group size on compare.
- Adds numbered error/warning rows and counts omitted messages; README documents automatic comparison of the newest retained pair.
- Local checks: 88 unit tests pass (4 symlink skips), compileall and diff check pass. Offscreen GUI smokes pass for mixed valid/invalid imports, 100-run truncation, group cleanup, and 13-file error summaries.
- DeepSeek initially reported a false positive about `SafetyError`; after checking the actual parser and its `ValueError` inheritance, it retracted the finding and confirmed no blockers. Also confirmed group validation reruns the three-run minimum.

## Next

1. Publish v1.3.0 after final local verification.
2. Update the portfolio card and verify the Pages deployment.
3. Continue FrameForge improvements within the five-hour work block.
