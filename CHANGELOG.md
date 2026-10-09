# Changelog

## 1.13.0 - 2026-10-09

- Add an accessible A/B role-swap button for selected benchmark runs; swapping clears the current report and export until the user explicitly compares again.
- Keep recent comparisons unchanged by a swap; after an explicit compare, the reversed ordered pair is recorded as its own session entry.
- Disable swapping for missing, stale, same-run or non-integer selections; block selector signals during the atomic swap.

## 1.12.0 - 2026-10-09

- Keep the last 10 distinct successful A/B comparisons in a collapsed, session-only list; repeat pairs move to the top.
- Restore a recent pair into A/B selectors without reusing its old report; require an explicit Compare action. Mark pairs unavailable if a run leaves history and relink the same run when its pin/reference flag changes.
- Keep the list local to the current session and outside benchmark storage and exports.

## 1.11.0 - 2026-10-09

- Let one pinned benchmark be marked as the active baseline for the current app session, with a visible history marker; unpinning it clears the session selection.
- Add a shortcut to assign the active baseline and one selected ordinary run to A/B, while requiring an explicit Compare action before producing a report or export.
- Keep the active selection out of stored history and exports; changing it does not change benchmark data.

## 1.10.0 - 2026-10-09

- Show all benchmark runs with exactly matching game, scene and metric in a read-only history view, including pinned references; keep history schema and exports unchanged.
- Label row numbers as local history positions, not capture timestamps or chronology; show missing legacy frame-budget summaries as unavailable.
- Offer the view from a keyboard-accessible button and the history context menu, and explain when only one matching run exists.

## 1.9.1 - 2026-10-09

- Keep the probable-duplicate CSV dialog usable for long batches with a bounded, scrollable list sized for the monitor that owns the parent window.
- Show each file's selection number alongside its basename so duplicate filenames remain distinguishable without exposing full paths.

## 1.9.0 - 2026-10-09

- Warn before importing CSV runs whose complete aggregate fingerprint matches an existing run or an earlier accepted file in the same batch; no history schema change or file identity is stored.
- Treat matches as probable only: users can explicitly keep any flagged run, and captures under 30 frames skip fingerprint checks.

## 1.8.0 - 2026-10-09

- Add a one-action helper to select the nearest earlier benchmark run with the same explicitly labeled game, scene and metric kind.
- Keep candidate matching strict and non-mutating: missing labels or no prior match leave the current pair intact, and the user must still press Compare to generate a report.
- Provide the action from both a history context menu and a keyboard-accessible button; no history schema or export fields change.

## 1.7.0 - 2026-10-09

- Add up to five pinned benchmark reference runs that survive the 100 ordinary-run history limit.
- Evict only the oldest unpinned runs on import; preserve pinned positions, include references in search and A/B selection, and require confirmation before an unpin that would exceed the normal history cap.
- Migrate benchmark history v1-v8 to schema v9 with existing runs unpinned; keep reference flags local and out of aggregate exports.

## 1.6.0 - 2026-10-09

- Add a descriptive within-run frametime tail spread (p99 minus median) to pair reports and aggregate-only CSV/JSON exports; version the pair JSON schema as v4.
- Label the metric as descriptive, not a significance test or a guarantee of perceived smoothness; retain existing causal and repeatability cautions.

## 1.5.0 - 2026-10-09

- Add a literal, case-insensitive search to locate benchmark runs for the full-history Baseline/Variant selectors without changing the current pair while typing.
- Show duplicate source names as distinct numbered history results; explicitly assign a selected result to A or B using its original history index.
- Keep no-match and cleared searches from changing the pair; require a fresh comparison after changing a pair so an old pair report cannot be exported as if current.
- Validate selected history indices before comparison and add search-helper regression tests for empty, literal, case-insensitive, duplicate-name, checklist and setting-snapshot queries.

## 1.4.0 - 2026-10-09

- Add a case-insensitive text filter for benchmark history across filename, game, scene, metric kind, local note and optional setting snapshot.
- Show matching versus total run counts; clear list selection when the filter changes while preserving temporary A/B group assignments and showing how many members are hidden. The filter applies to the list used for group assignment, not the full-history Baseline/Variant selectors or explicit exports.
- Clear an active history filter after successful batch import so the automatically compared newest pair remains visible.
- Clarify in repeated-group reports that the list filter changes only assignment visibility; comparisons still use all runs already assigned to each group.

## 1.3.0 - 2026-10-09

- Import multiple benchmark CSV files in one operation for faster repeated A/B capture workflows.
- Apply the current game, scene and manually selected checklist context consistently to each selected file; report per-file parse failures and continue importing valid files. Numbered notices disambiguate repeated filenames and summarize omitted errors/warnings.
- Save each batch atomically and keep the in-memory and on-disk history aligned to the newest 100 runs.
- Automatically compare the two newest retained runs after a successful import; document this selection in the README.

## 1.2.0 - 2026-10-09

- Add cross-game frame-budget comparisons for 30/60/90/120/144/165/240 FPS, using counts of accepted frames at or below each exact `1000/FPS` threshold.
- Store only seven aggregate counts per new benchmark; retain no raw frame times and mark pre-v1.2 history as unavailable rather than treating it as 0%.
- Include the selected target and aggregate within-budget share in comparison reports and exports; group summaries use per-CSV percentages and keep exports aggregate-only.
- Migrate benchmark history schemas v1-v7 to schema v8; preserve legacy records without fabricated frame-budget values.

## 1.1.0 - 2026-10-09

- Summarize optional PresentMon CPU Busy, GPU Time and GPU Busy counters over accepted frametime rows; show median, p95 and per-counter coverage without bottleneck claims.
- Keep extra counter summaries local and omit them from single-run and repeated-group CSV/JSON exports.
- Migrate benchmark history schemas v1-v6 to schema v7 with empty optional counter summaries for older runs.

## 1.0.1 - 2026-10-09

- Show anonymous per-CSV benchmark rows and accepted frame counts in repeated A/B reports to make run-to-run spread visible.
- Keep group CSV/JSON exports aggregate-only; clarify that row order follows benchmark history and is not capture chronology.

## 1.0.0 - 2026-10-09

- Add temporary A/B groups for repeated benchmark CSVs, requiring at least three separate runs per group and matching game, scene and frametime metric labels.
- Summarize each group's per-CSV aggregate results with median and inclusive interquartile range; do not pool frame samples or infer statistical significance/causality.
- Export aggregate-only repeated comparison CSV/JSON without filenames, user labels, notes, or frame data.
- Keep temporary groups in the current app session only; benchmark history remains on schema v6.

## 0.9.0 - 2026-10-09

- Add optional per-game checklists for manually changed settings to benchmark runs and show the differences as context in A/B reports, without causal claims.
- Keep checklist selections local and out of CSV/JSON exports; do not read or modify game settings through this checklist.
- Label manual checklist lists by game in A/B reports and avoid set differences when the selected games differ.
- Migrate benchmark history schemas v1-v5 into schema v6 with empty checklist selections for older runs.
- Add a clear Skyrim hint directing users to the separate read-only INI snapshot option.

## 0.8.0 - 2026-10-09

- Optionally attach a read-only snapshot of the selected allowlisted Skyrim setting to a benchmark; store only its key and integer value, never its INI path.
- Show setting snapshots side by side in A/B reports as context, without causal claims; keep snapshots out of CSV/JSON exports.
- Migrate benchmark history schemas v1–v4 into schema v5 with empty snapshot fields for older runs.
- Keep the PresentMon import, local change note and Windows package/runtime improvements introduced in v0.7.0.

## 0.7.0 - 2026-10-09

- Make the PySide6 DLL and platform-plugin paths explicit so PyInstaller does not depend on unrelated runtime DLLs; CI launches the frozen app and checks the main window before packaging.
- Import PresentMon per-frame CSV using `MsBetweenDisplayChange` or `MsBetweenPresents`, preserving the metric identity in local history and exports.
- Detect comma, semicolon and tab delimiters; accept decimal comma only with semicolon/tab separated files.
- Apply `FrameType` filters and show import warnings for skipped/missing samples and frame types, including the dropped-row share.
- Keep a short, local-only note about the settings changed for each benchmark and show the notes side by side in A/B reports; never include them in exports.
- Warn prominently when A/B runs use different frametime metrics; migrate history schemas v1–v3 into schema v4.
- Build from an explicitly selected Python environment and smoke-test the executable extracted from the release archive in CI.

## 0.6.0 - 2026-10-09

- Tag local benchmark runs with an optional game and scene/preset label; warn when A/B labels differ or are missing.
- Keep unlabelled benchmark history in v1 format; switch to schema v2 only after a game or scene label is saved, while keeping legacy entries available.
- Keep labels local and out of aggregate CSV/JSON exports.
- Check the expected current-file SHA-256 during apply and restore, and revalidate the supported path before atomic replacement. The checks are sequential; see README for the remaining concurrent-write limitation.
- Resolve Windows Documents through the Known Folder API, including redirected OneDrive profiles.

## 0.5.0 - 2026-10-09

- Export aggregate-only A/B benchmark comparisons as CSV or versioned JSON.
- Exports omit source filenames, paths, source CSV content, and raw frame samples.
- Include frame-time bucket counts/shares and explicitly label two-run results as non-causal.
- Show exact source filenames only in the on-screen comparison, not in exported reports.

## 0.4.0 - 2026-10-09

- Improve benchmark comparisons with per-bucket normalized shares and percentage-point deltas in the text report.
- Warn when baseline and variant sample counts differ by more than 5%; label runs as Baseline (A) and Variant (B).
- Clarify that run differences alone do not establish that a setting caused the change.

## 0.3.0 - 2026-10-09

- Persist up to 100 benchmark summaries locally across application restarts.
- Store only the source file name and aggregate frame-time metrics; never retain source CSV files, raw samples, or absolute source paths.
- Validate the versioned history format and write it atomically with size and field checks.

## 0.2.0 - 2026-10-09

- Add a second reversible Skyrim profile for grass density in `Skyrim.ini`, including a deliberate grass-off preset (`iMinGrassSize=0`).
- Add exact-file backups, diff preview, SHA-256 verification and restore support for both Skyrim INI files.
- Add profile-specific warnings, values and source links; reject negative density values.
- Add a frame-time distribution chart with before/after buckets for quick stutter comparison.
- Restrict release write permissions to a post-quality tag-only job and refresh GitHub Actions dependencies.

## 0.1.0 - 2026-10-09

- Add a Windows desktop UI, read-only system overview, and read-only Steam detection for Skyrim Special Edition.
- Add one reversible Skyrim grass-distance profile with a line-level preview, byte-exact backup, SHA-256 verification, atomic write, and restore protection.
- Add game-specific manual graphics checklists for 12 additional popular titles; no unsupported automatic file or anti-cheat edits.
- Add CSV analysis for average FPS, 1% low, median and p99 frame time to compare before and after runs.
- Add safety checks, regression tests, portable Windows packaging, and a GitHub Actions quality and release workflow.
