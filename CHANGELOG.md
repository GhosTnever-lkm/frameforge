# Changelog

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
