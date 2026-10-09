# FrameForge — project state

Updated: 2026-10-09

## Current version

- Published baseline before this work: v1.0.1.
- Work in progress: v1.1.0, optional local PresentMon counter summaries.
- Current source checks: 82 unit tests pass; 4 platform-dependent symlink tests are skipped.
- GUI smoke: repeated A/B report showed optional GPU Busy values, per-run coverage, and explicit missing-column rows.
- Windows portable build: launch verified as `FrameForge — Game Tuning Studio`.
- Release archive: `dist/FrameForge-1.1.0-windows-x64.zip`.
- SHA-256: `e55bb83cd8c7e7b5458fac6bfa407bae83d9ff6762fd38bb2ecb29ca96d47e9e`.
- DeepSeek review: no blocking defects found from the supplied implementation description; wording clarifies that coverage is over accepted frametime rows and zero values are reported as recorded.

## v1.1.0 behavior

- Imports optional PresentMon `MsCPUBusy`/`CPUBusy`, `MsGPUTime`/`GPUTime`, and `MsGPUBusy`/`GPUBusy` columns.
- Reports median, nearest-rank p95, and valid-value coverage locally; does not infer a performance bottleneck or GPU scheduling mode.
- Persists only per-run summaries in local history schema v7; v1–v6 records migrate with no optional counter data.
- Keeps the counters out of single-run and repeated-group CSV/JSON exports.

## Next

1. Commit and push v1.1.0 source.
2. Verify branch/tag GitHub Actions and publish the GitHub Release with the tested archive and checksum.
3. Update the profile portfolio/release links after publication.
