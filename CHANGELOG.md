# Changelog

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
