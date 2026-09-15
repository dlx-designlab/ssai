# Development Log

This document records the main work completed on SSAI, organized by date.

## 2026-09-15

- Reviewed all Python modules for syntax and consistency.
- Verified that every Python source file compiles successfully with
  `python3 -m compileall`.
- Fixed generation state cleanup so a communication or generation error cannot
  leave the application stuck with new questions blocked.
- Improved the terminal control dashboard so completed turns remain visible
  while the live hardware section is refreshed.
- Kept hardware sampling at 15-second intervals while allowing the control
  dashboard to refresh every 0.5 seconds.
- Updated the control-view documentation to describe the separate hardware
  sampling and dashboard refresh intervals.
- Ran a startup smoke test for `control.py` and verified the final diff with
  `git diff --check`.

Add a new dated section at the top of this file for future work days.
