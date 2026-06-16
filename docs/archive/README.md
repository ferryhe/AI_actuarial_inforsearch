# Historical Documentation Archive

This archive preserves dated planning notes, implementation reports, test checklists, older security summaries, and other historical project documents.

These files are **not** the source of truth for current product behavior. Many were written during earlier Flask/server-rendered UI, Replit workflow, migration, or phase-planning periods and may contain stale commands, incomplete TODOs, old status percentages, or superseded architecture assumptions.

For current documentation, start with:

- [Root README](../../README.md)
- [Chinese README](../../README.zh-CN.md)
- [Documentation Index](../README.md)
- [Architecture](../ARCHITECTURE.md)
- [API Migration Status](../API_MIGRATION_STATUS.md)
- [Security Policy](../../SECURITY.md)

## Archive Layout

- [`root/`](root/): dated root-level planning, development, testing, research, and engineering notes that used to live directly under `docs/`.
- [`implementation/`](implementation/): historical implementation summaries and PR/phase reports.
- [`testing/`](testing/): historical manual testing guides and checklists.
- [`security/`](security/): older security summaries. Use the root [Security Policy](../../SECURITY.md) for the current checklist.
- [`architecture/`](architecture/): older subsystem architecture notes superseded by the active [Architecture](../ARCHITECTURE.md).
- [`code_review/`](code_review/): historical review findings and progress notes.
- [`superpowers/`](superpowers/): older agent-generated plans.
- [`zh-cn/`](zh-cn/): older Chinese implementation/user notes.

If a historical doc becomes actively maintained again, move it out of `archive/`, update links, and remove stale phase/status language before referencing it from the active docs index.
