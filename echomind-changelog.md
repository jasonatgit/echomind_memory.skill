# EchoMind Memory — Changelog

## v1.1.1 (2026-05-29)

### MemoryProvider Integration Fix
- `EchomindMemoryProvider` now inherits from `MemoryProvider` ABC (safe import with fallback)
- Added `register(ctx)` plugin registration entry point
- Added `get_config_schema()` and `save_config()` methods for Hermes v0.13.0+ compatibility
- All 18 MemoryProvider methods verified present

### Install Script Improvements
- `install.sh` / `install.ps1`: Auto-detect Hermes installation directory
  - Priority: `$HERMES_HOME` → platform default (`~/.hermes` / `%LOCALAPPDATA%\hermes`)
- `install.sh` / `install.ps1`: HTTP service auto-start now conditional (`ECHOMIND_HTTP_SERVICE=1`)
  - Default: no auto-start (Hermes MemoryProvider runs in-process)
  - Rationale: standalone HTTP API only needed for OpenCode/OpenClaw integration

### README Overhaul
- Installation section rewritten with clear prerequisites table
- Step-by-step flow: git clone → pip install → run install script → verify
- Documented path auto-detection behavior for both Linux and Windows
- Chinese version (README.zh-CN.md) aligned

### Compliance
- Removed `_get_pro_seeds` function references from OSS code
- Added `*.pyd` to `.gitignore` (Windows compiled extensions)
- Verified zero Pro-version references in tracked source files

## v1.1.0 (2026-05-22)

Initial structured release with Self-Reflective Agent, 6 memory types, RL self-optimization,
ConfigManager, and Hermes MemoryProvider integration.
