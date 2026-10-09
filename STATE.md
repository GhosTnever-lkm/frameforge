# FrameForge — project state

Updated: 2026-10-09

## Current version

- Published: v1.6.0, descriptive per-run frametime tail spread. Release workflow [37871967572](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37871967572) passed; archive SHA-256 `fe606643804cedae66a3a456ab46cf2625de6b74576c1806a4fa106a63b021c7`.
- Portfolio commit `90ba35b3e6dc4427ed6e9d88cd7740faa3a1f5f6` updates the FrameForge card to v1.6.0; Pages run [37872052967](https://github.com/GhosTnever-lkm/GhosTnever-lkm.github.io/actions/runs/37872052967) passed and the live page was verified.
- Local v1.6.0 release checks: 99 tests passed; 4 symlink tests skipped due to environment privileges; compile, package and release smoke passed.

- Published: v1.4.0, searchable benchmark history list and explicit group-filter scope.
- GitHub Actions release run [37869978554](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37869978554) passed tests, compilation, Windows build and release publication.
- Published archive: [FrameForge v1.4.0](https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.4.0), `FrameForge-1.4.0-windows-x64.zip`; SHA-256 `e0d814e9f7c9bccb8e421a53b518a8695f3ea1a4db3469b9471913e3b831d604`.
- Downloaded the published archive, verified its SHA-256 and launched its EXE; the app window responded with title `FrameForge — Game Tuning Studio`.
- Portfolio updated in commit `d4798a94dd1f181a5b2c5987e59692bedff0dcbc`; Pages deployment [37870291926](https://github.com/GhosTnever-lkm/GhosTnever-lkm.github.io/actions/runs/37870291926) succeeded. Reloaded the live page and confirmed its FrameForge description, release link and Windows ZIP link show v1.4.0.
- Local v1.4.0 baseline: 88 unit tests pass; 4 platform-dependent symlink tests are skipped; compileall, diff check and GUI smoke pass.

- Published: v1.3.0, batch benchmark CSV import.
- Local checks for v1.3.0: 88 unit tests pass; 4 platform-dependent symlink tests are skipped; compileall, diff check and GUI smokes pass.
- GitHub Actions run [37869482152](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37869482152) passed tests, Windows portable build and startup smoke.
- Published archive: [FrameForge v1.3.0](https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.3.0), `FrameForge-1.3.0-windows-x64.zip`; SHA-256 `a3b1dee165cbd38beebffa69dd7f5e1ccc597f794e8a38217f870c215e07830b`.
- Downloaded the v1.3.0 archive, verified its SHA-256, extracted it and launched the EXE; the window title was `FrameForge — Game Tuning Studio` and the process responded.
- DeepSeek reviewed the batch import; after retracting a false positive, it found no confirmed blockers. The review scope clarified per-file error handling, history truncation, group minima, filter behavior, and auto-pair visibility.
- Portfolio card: [live site](https://ghostnever-lkm.github.io/) now links to v1.3.0 and describes frame budgets and batch CSV import. Deployment run [37869842446](https://github.com/GhosTnever-lkm/GhosTnever-lkm.github.io/actions/runs/37869842446) succeeded and the refreshed page shows the new copy and links.

- Published: v1.2.0, cross-game frame-budget reporting.
- Local v1.2.0 checks: 88 unit tests pass; 4 platform-dependent symlink tests are skipped; compileall, diff check and offscreen GUI smoke pass.
- GitHub Actions run [37869046502](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37869046502) passed tests, Windows portable build and startup smoke.
- Published archive: [FrameForge v1.2.0](https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.2.0), `FrameForge-1.2.0-windows-x64.zip`; SHA-256 `66fbef54b64881b252890330a24f3a886d7d02a9a04b837002b6b6e2a9c57ac4`.
- Downloaded release archive, verified its SHA-256, extracted it and launched `FrameForge.exe`; the window title was `FrameForge — Game Tuning Studio` and the process responded.
- DeepSeek reviewed v1.2.0 and found no blockers in the described scope.

## v1.2.0 behavior

- Stores seven overlapping aggregate frame-budget counts at CSV import for the supported FPS presets; raw frame samples remain discarded.
- Shows the selected threshold in A/B and repeated-run reports; old history migrates to schema v8 with an explicit unavailable value.
- Keeps single and group exports aggregate-only and includes the selected target.

## v1.3.0 behavior

- Multi-select benchmark CSV import applies one shared game/scene/checklist context, saves valid selections as a single bounded batch, and reports per-file failures.
- Keeps history aligned with the newest 100 runs in memory and on disk; removes group references to evicted runs and validates minimum group size on compare.
- Adds numbered error/warning rows and counts omitted messages; README documents automatic comparison of the newest retained pair.
- Offscreen GUI smokes pass for mixed valid/invalid imports, 100-run truncation, group cleanup, and 13-file error summaries.

## v1.4.0 behavior

- Adds a case-insensitive history-list filter across CSV name, game, scene, metric type, local note, setting snapshot and checklist labels. It does not alter the saved history.
- Clears list selection when the filter changes; existing A/B group membership persists and status reports how many group members are hidden.
- Makes the scope explicit: Baseline/Variant selectors and exports use full history; group reports use every assigned member. A successful batch import clears the active filter before showing the newest pair.
- Local checks: 88 unit tests pass (4 symlink skips); compileall and diff check pass. GUI smokes cover case-insensitive/literal search, zero matches, reset, selection/group behavior, full combo options, hidden group counts, and import resetting the filter.
- DeepSeek review found no confirmed blockers. Remaining design choice: the filter is only for the group-assignment list; Baseline/Variant selectors remain full-history.

## v1.5.0 behavior

- Adds a case-insensitive literal search across the full benchmark history to locate entries for Baseline/Variant. Search results keep the source history index in `UserRole`; duplicate filenames have distinct numbered rows.
- Typing, clearing or getting no matches never changes the selected pair. Users explicitly assign one selected result to A or B. Changing a selected pair clears its old pair report/export until a fresh comparison is run; group reports remain unaffected.
- Adds selected-index bounds validation and five unit tests for empty query, literal/case-insensitive matching, duplicate labels/original indices, checklist labels and setting snapshots.
- Local test suite currently: 94 passed, 4 platform-dependent symlink skips. `compileall` and `git diff --check` pass; the UI version matches `VERSION`. Qt offscreen smokes verify duplicate-name identities, a filtered row 0 assigning original history index 47, no-result behavior, invalid pair rejection, and pair-report/group-export state.
- DeepSeek recommended this separate search/list/explicit-assignment design. Its first code-review concern about `itemData(index)` was resolved by an exact Qt smoke where result row 0 stores history index 47 and correctly assigns combo item 47; DeepSeek withdrew the concern and confirmed no blockers. The concern about batch truncation is addressed by the import flow synchronously selecting and comparing the newest retained pair before returning.

## Work in progress: v1.7.0

- Adds up to five pinned reference runs that survive the 100-run ordinary history cap; imports evict only the oldest ordinary entries.
- History schema v9 migrates old records as unpinned, rejects malformed flags and over-budget stores, and keeps reference markers out of aggregate exports.
- UI supports pin/unpin, searches and A/B selection; a full-cap unpin warns before eviction and explicitly identifies when the just-unpinned oldest run will be deleted.
- DeepSeek adversarial review found no confirmed blockers; its residual UX case was handled with the clearer warning above.
- Local test suite: 103 passed, 4 platform-dependent symlink skips; compileall and diff check pass.

## Next

1. Complete v1.7.0 release gates, publish the Windows build and verify startup/checksum.
2. Update and verify the portfolio card and changelog for v1.7.0.
3. Continue FrameForge work within the five-hour work block.
