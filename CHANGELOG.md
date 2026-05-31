# Changelog

All notable changes to TremorAssist are documented here. This project follows
[Semantic Versioning](https://semver.org/).

## [0.2.0]

### Added
- **Tremor frequency analysis** (`analysis.py`): a dependency-free DSP pipeline
  (detrend → uniform resample → Hann-windowed DFT → parabolic peak-pick) that
  estimates the dominant tremor frequency, amplitude, and a confidence score
  from the live cursor signal. Shown live in the control panel and headless mode.
- **Auto** comfort level / `auto_adapt` mode: continuously sizes the hold-steady
  dead-zone to the measured tremor amplitude (clamped, never below the manual
  setting).
- **Scroll stabilization** (`ScrollStabilizer`): suppresses tremor-induced stray
  reverse scroll-wheel ticks.
- Test suite expanded to 33 tests (`test_analysis.py`, `test_scroll.py`,
  `test_config.py`).
- GitHub Actions CI running ruff + pytest on Python 3.9–3.12.
- `ruff` lint configuration.

### Changed
- Session/all-time stats and the snapshot now include scroll suppressions and
  the latest tremor frequency/amplitude.
- README rewritten with a signal-processing overview, badges, and updated
  architecture map.

## [0.1.0]

### Added
- Initial release: system-wide One Euro Filter mouse smoothing, hold-steady
  dead-zone, click stabilization, keyboard/click debounce.
- Native macOS (Cocoa/AppKit) control panel with Mild/Moderate/Strong/Off
  comfort levels, menu-bar control, live tremor graph and session history.
- GUI and headless entry points; py2app standalone build.
