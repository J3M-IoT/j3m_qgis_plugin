# AGENTS.md — J3M QGIS Connector

## 1. Purpose and instruction priority

This file defines mandatory rules for any AI coding agent or contributor modifying the **J3M QGIS Connector** plugin. The plugin connects QGIS to the J3M API to retrieve sessions, indicators, and georeferenced observations, load map layers, and display geographic information. Preserve existing authentication, visualization, and operational limits.

**Priorities, in order:** security and data integrity; verified QGIS compatibility; stability and user experience; compliance with distribution requirements; simplicity and maintainability. Nothing in this file authorizes silent changes to requirements or removal of existing functionality.

Before changing code, inspect the actual repository structure, `metadata.txt`, `__init__.py`, dependencies, tests, and existing conventions. Never assume file names, class names, endpoints, or API contracts. Make focused, minimal changes; avoid unrelated refactoring without a demonstrated need.

## 2. Mandatory QGIS, Python, and Qt compatibility

1. **Primary target: the most recent officially released stable QGIS major version at the time of each change** (QGIS 4.x as of October 2026). Verify the currently supported release before selecting APIs or claiming compatibility. Do not mistake development, testing, or prerelease builds for the latest stable major version.
2. Use the Python version, Qt version, and PyQGIS APIs supplied by the target QGIS installation. **QGIS 4 uses Qt 6 / PyQt6**; do not introduce new Qt 5 / PyQt5 dependencies.
3. Import Qt through `qgis.PyQt` wherever possible (`QtCore`, `QtGui`, `QtWidgets`, etc.). Do not import `PyQt5`, `PyQt6`, `PySide2`, or `PySide6` directly in plugin runtime code unless a documented, tested technical requirement makes it necessary.
4. Use public, documented PyQGIS APIs, including `qgis.core` and `qgis.gui`. Do not rely on private internals or deprecated/removed APIs.
5. When adapting APIs between Qt 5 and Qt 6, use the correct classes, namespaces, and enum values for the target version. Review `QAction`, `QFileDialog`, `QDialog`, `QMessageBox`, `QSettings`, `QVariant`, signals/slots, `exec()`, flags, and scoped enums in particular. Never apply blind text substitutions.
6. Preserve QGIS 3.x compatibility **only when the project explicitly claims it and real tests verify it**. Never compromise the current stable QGIS major version merely to retain legacy support. If necessary, isolate differences in a small, tested compatibility layer.
7. Never set `qgisMaximumVersion` speculatively. Keep `qgisMinimumVersion` aligned with the oldest version actually supported and tested; review compatibility metadata before every release.
8. **Passing syntax checks or compilation is not evidence of runtime compatibility.** Verify plugin loading, primary user workflows, and unloading in the target QGIS installation. If QGIS is unavailable in the development environment, explicitly report **“Not runtime-tested in QGIS.”**
9. Do not automatically install, upgrade, or replace packages inside the Python environment managed by QGIS.

## 3. Plugin structure and lifecycle

- Keep `metadata.txt` UTF-8 encoded and `__init__.py` exposing a functioning `classFactory(iface)`. Follow the official QGIS Python plugin entry points and structure.
- Register actions, menus, toolbars, and UI components in `initGui()` or the appropriate entry point of the existing architecture; release them in `unload()`.
- `unload()` must disconnect signals, remove plugin-owned actions and UI entries, safely cancel or finish tasks, and free owned resources. Disabling or reloading the plugin must not duplicate actions, dialogs, or signal connections.
- Never retain invalid references to deleted `QObject` instances or removed layers. Respect Qt object ownership and lifetime, including when dialogs close.
- Use paths relative to the plugin directory (`pathlib` / `os.path`), not machine-specific absolute paths or assumptions about the working directory.
- Follow the project's existing organization. Separate API, authentication, presentation, transformation, and layer-creation concerns when doing so improves maintainability.
- Do not add external dependencies without considering their availability in QGIS, licenses, ZIP size, cross-platform installation, and user-facing setup requirements.

## 4. Qt UI and asynchronous operations

- All widget, map canvas, and other UI modifications must occur on the **Qt main thread**.
- Never block the UI with long-running HTTP requests, large response parsing, or expensive processing. Use appropriate mechanisms such as `QgsTask`, signals/slots, and/or `QNetworkAccessManager`.
- Worker threads must not touch widgets or QGIS UI objects. Respect PyQGIS thread-safety constraints around project/layer access; perform relevant mutations on the main thread.
- Provide clear feedback for loading, progress, cancellation, errors, empty results, and success. Cancellation must not leave the project in an inconsistent state.
- Respect localization, basic accessibility, high-DPI scaling, light/dark themes, and native QGIS interface conventions. Do not hardcode fonts, colors, or dimensions without a concrete reason.
- Prefer Qt layouts over fixed positioning. Never assume a specific screen resolution or operating system.
- Prevent duplicate signal connections, orphan dialogs, and persistent references that cause resource leaks.

## 5. J3M API, authentication, and geospatial data

- Preserve the actual J3M API contract, endpoints, headers, formats, pagination, filters, limits, and authentication process. Verify these in the code or documentation before modifying them.
- Continue using QGIS authentication facilities (`QgsAuthManager` and supported integration methods) where applicable. **Never** expose tokens, passwords, credentials, or authorization headers in logs, printed output, error messages, URLs, version-controlled files, or user-visible exceptions.
- Do not embed API secrets, invent insecure credential stores, or request sensitive credentials in diagnostic logs.
- Use HTTPS and handle HTTP errors, malformed responses, timeouts, connectivity failures, expired authentication, server limits, and partial responses. Avoid aggressive retries; add bounded retries and backoff only when appropriate.
- Do not impose a plugin-defined response/transfer size cap. Large responses must remain supported; use asynchronous processing, cancellation, and efficient memory handling.
- Explicitly handle CRS/EPSG identifiers, coordinate transformations, axis order, longitude/latitude, empty geometries, and null attributes. Do not assume source coordinates are already in the project CRS.
- Identify and document the source CRS before creating layers. Never silently reinterpret coordinates or transform them without the correct QGIS APIs.
- Validate GeoJSON/JSON, geometry types, properties, numeric and temporal formats. Do not assume every observation contains every indicator.
- Preserve proper field types, numeric precision, timestamps, and time zones; do not turn everything into strings.
- Prefer public QGIS layer, provider, and renderer APIs. Never add invalid layers or modify user data without explicit confirmation.
- J3M observations are **immutable**: treat the plugin as a read/visualization client unless a write workflow is expressly specified.
- Minimize local persistence of data, safeguard location privacy, and do not add unsolicited telemetry.

## 6. Security, resilience, and performance

- Never execute API-supplied data as code. Forbid `eval`, `exec`, unsafe deserialization, and shell-command construction from external inputs.
- Validate user input, URLs, and parameters. Do not render untrusted remote HTML without appropriate sanitization.
- Display understandable user errors while recording useful technical details without secrets. Never use `except: pass` or silently swallow failures.
- Account for large point collections, empty responses, and invalid geometries. Avoid rebuilding UI elements or recomputing data unnecessarily.
- Release network replies, timers, tasks, and temporary objects. Control memory usage and avoid redundant copies.
- Do not introduce tracking, additional third-party calls, paid services, or new infrastructure dependencies without explicit authorization.
- Do not change public interfaces, action names, or user-visible behavior without documenting the reason and updating relevant tests.

## 7. Metadata, licensing, and packaging

Before preparing a release, check the *current* official requirements at <https://plugins.qgis.org/docs/publish/>, <https://plugins.qgis.org/docs/approval/>, and in the PyQGIS documentation for the target major version.

- Maintain valid required fields in `metadata.txt`, including `name`, `description`, `about`, `version`, `qgisMinimumVersion`, `author`, and `email`, plus any other metadata required by the current plugin repository rules.
- Include a `LICENSE` file **without a filename extension** for official repository publication, using a license accepted by QGIS and complying with licenses of dependencies and third-party assets.
- Maintain a concise README describing setup, authentication, requirements, limitations, and usage. Provide an English short description where required by the official repository.
- The distributable ZIP must contain **one plugin root directory** with a valid ASCII name (letters, digits, `_`, or `-`; not starting with a digit), containing `metadata.txt`, `__init__.py`, `LICENSE`, and only required assets.
- Exclude prohibited binaries, secrets, `.git`, virtual environments, caches, logs, heavy test artifacts, and local-only files. Obey current repository size and upload requirements.
- Never compile Qt resources with tools targeting a different Qt major version from the QGIS target. Review `.qrc`, `.ui`, and the available tooling without assuming `pyrcc5` or `pyrcc6` is present.
- Increment release versions consistently. Never reuse a previously published version for changed release contents.
- Never publish or submit the plugin to the official repository without explicit maintainer instructions.

## 8. Tests and acceptance criteria

For each change, run all available relevant tests and add regression coverage where feasible. At minimum, verify:

1. The plugin loads and enables in a real installation of the **latest stable QGIS major**, without Python import or Qt errors.
2. Its UI opens, menus and icons display correctly, and dialogs close without exceptions.
3. Its intended authentication mechanism works, and sessions, indicators, and observations can be queried using real responses or representative fixtures.
4. Layers are correctly created and displayed with valid geometry, fields, CRS, and attributes; include empty, null, invalid, and near-size-limit responses.
5. Network failures, HTTP 401/403, 404, 429, 5xx, timeouts, malformed JSON, cancellation, and repeated actions are handled without freezing or crashing QGIS.
6. Disabling/re-enabling and reloading the plugin does not duplicate UI components or leave dangling tasks and signal connections.
7. Metadata and distributable ZIP structure satisfy repository rules whenever packaging is involved.
8. If QGIS 3.x compatibility is claimed, repeat the applicable tests on each supported legacy target; test Windows, Linux, and macOS when infrastructure permits.

Use unit tests for pure logic and data transformations, integration tests for PyQGIS/network behavior, and real QGIS runs for UI workflows. Never fabricate test results or claim a test passed without running it. If QGIS is unavailable, state this limitation and run the feasible static checks, including `python -m compileall` when useful.

## 9. Mandatory end-of-task cleanup — NO EXCEPTIONS

**At the end of every task**, before reporting completion, remove Python cache artifacts generated **within the plugin repository tree**:

- Every `__pycache__` directory, recursively.
- Every `*.pyc` and `*.pyo` file, recursively.
- Related local tool caches, such as `.pytest_cache`, `.mypy_cache`, and `.ruff_cache`, when present and not intentionally tracked project assets.

Never remove global QGIS caches, operating-system caches, caches belonging to other repositories, shared environments, or external dependencies. Confirm the working directory before running destructive commands. Example cleanup **from the plugin repository root** on Linux/macOS:

```bash
find . -type d \( -name '__pycache__' -o -name '.pytest_cache' -o -name '.mypy_cache' -o -name '.ruff_cache' \) -prune -exec rm -rf -- {} +
find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
```

Then verify there are no remaining bytecode artifacts:

```bash
find . \( -type d -name '__pycache__' -o -type f \( -name '*.pyc' -o -name '*.pyo' \) \) -print
```

This verification must produce **no output**. Perform cleanup **after** tests, compilation, resource generation, and any commands that might recreate cache files. If another Python command runs afterward, repeat cleanup. Exclude these artifacts from version control and release ZIPs. If cleanup fails, report the failure rather than claiming completion.

## 10. Required workflow for every change

1. Inspect relevant repository files and requirements; determine the current target QGIS/Qt versions and any declared backward compatibility.
2. Plan the smallest appropriate change and identify PyQGIS, Qt, UI, authentication, and geospatial risks.
3. Implement without regressions, unnecessary dependencies, or inconsistent metadata.
4. Run static validation, existing tests, and available integration tests; validate in an actual QGIS installation whenever possible.
5. For releases, check license, `metadata.txt`, version, ZIP contents, and current official publication requirements.
6. **Clean cache artifacts and verify cleanup as the final technical operation.**
7. Report changed files, changed behavior, QGIS/Qt versions actually tested, test commands/results, known limitations, and cache cleanup status.

## 11. Explicit prohibitions

- Do not claim compatibility with the newest QGIS without verifiable runtime testing.
- Do not guess at Qt API changes or fix compatibility by blind trial and error.
- Do not introduce direct PyQt5 imports or new Qt 5-dependent code.
- Do not block the main UI thread or manipulate UI widgets from workers.
- Do not log or publish credentials or private location observations.
- Do not automatically install dependencies into QGIS-managed Python.
- Do not overengineer the architecture, add unrequested features, or change the J3M API contract for convenience.
- Do not package caches, development artifacts, or secrets.
- **Do not finish a task while `__pycache__`, `.pyc`, or `.pyo` files remain in the repository.**

## 12. Authoritative references

If requirements are unclear or conflict, consult documentation for the actual target QGIS version first:

- PyQGIS plugin development: <https://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/plugins/index.html>
- Plugin structure: <https://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/plugins/plugins.html>
- Releasing plugins: <https://docs.qgis.org/4.2/en/docs/pyqgis_developer_cookbook/plugins/releasing.html>
- Official plugin repository publishing requirements: <https://plugins.qgis.org/docs/publish/>
- Official plugin approval criteria: <https://plugins.qgis.org/docs/approval/>
- QGIS API documentation: <https://api.qgis.org/api/>

**Final rule:** deliver changes only when they are technically justified, preserve established workflows, target the latest stable QGIS major, and leave the plugin repository free of Python caches.
