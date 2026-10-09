# FrameForge — project state

Updated: 2026-10-09

## Current version

- Published baseline before this work: v1.0.1.
- Published: v1.1.0, optional local PresentMon counter summaries.
- Local source checks: 82 unit tests pass; 4 platform-dependent symlink tests are skipped. GitHub Actions on the v1.1.0 tag passed the full quality suite, Windows portable build, and executable startup smoke test.
- GUI smoke: repeated A/B report showed optional GPU Busy values, per-run coverage, and explicit missing-column rows.
- Windows portable build: GitHub release asset downloaded, SHA-256 verified, and launched as `FrameForge — Game Tuning Studio`.
- Release archive: [FrameForge v1.1.0](https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.1.0), `FrameForge-1.1.0-windows-x64.zip`.
- Published ZIP SHA-256: `e5965ae357f48324f823d184be5cd4db43b228a0d0e96a034bf646d40beee174`.
- DeepSeek review: no blocking defects found from the supplied implementation description; wording clarifies that coverage is over accepted frametime rows and zero values are reported as recorded.

## v1.1.0 behavior

- Imports optional PresentMon `MsCPUBusy`/`CPUBusy`, `MsGPUTime`/`GPUTime`, and `MsGPUBusy`/`GPUBusy` columns.
- Reports median, nearest-rank p95, and valid-value coverage locally; does not infer a performance bottleneck or GPU scheduling mode.
- Persists only per-run summaries in local history schema v7; v1–v6 records migrate with no optional counter data.
- Keeps the counters out of single-run and repeated-group CSV/JSON exports.

## Next

1. Update the profile portfolio/release links to highlight v1.1.0.
2. Continue FrameForge improvements within the five-hour work block.
