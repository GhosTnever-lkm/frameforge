# FrameForge — project state

Updated: 2026-10-09

## Current version

- Published: [v1.14.0](https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.14.0) adds a button to copy the full pair/group report as text. It is disabled when the report is absent/stale; copied content includes CSV run names and user-entered notes, with no file or network operation.
- Checks: 136 tests passed, 4 platform-dependent symlink tests skipped; compileall, diff check, local Windows build and extracted-app launch passed. Main CI `37878819637` and tag/release CI `37878822771` passed. Downloaded ZIP: 44,607,355 bytes; SHA-256 matches sidecar `9e102125e1b0f69088d35c2f5f8e2391719d3a1a7b2714a55584274c8f4c31eb`. DeepSeek reviewed the implementation and follow-up fixes; no concrete blocker remains.
- Portfolio commit `7f8e4ee` points to v1.14.0 and describes complete report copying. Pages run `37878851172` passed; live page verified release/download links and text. FrameForge commit `328c44c`.
- Published: [v1.13.1](https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.13.1) updates the focusable Baseline/Variant selectors' accessible name and description with each selected run, including after swaps.
- Checks: 135 tests passed, 4 platform-dependent symlink tests skipped; compileall, diff check, Windows build and extracted app launch passed. Main CI `37878411756` and tag/release CI `37878414883` passed. Downloaded ZIP: 44,607,024 bytes; SHA-256 matches sidecar `0dc3668863827503aa7cec063163c8d7f4d6bf1c5058db7af1f8f98be6968eb2`. DeepSeek confirmed the focused widget now carries the screen-reader value and the test checks it.
- Portfolio commit `b8bd0a8` points to the v1.13.1 release and Windows ZIP and describes the accessibility improvement. Pages run `37878423288` passed; live page verified release/download links and text. FrameForge commit `8080e44`.
- Published: [v1.13.0](https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.13.0), adds an accessible A/B role-swap action. It validates both selected history indices (rejecting bool, missing, identical and stale values), blocks both Qt selector signals during the swap, clears any existing report/chart/export, and requires an explicit Compare. Swapping alone does not change recent pairs; comparing in the reversed order records a distinct pair.
- Local checks: 135 tests passed, 4 platform-dependent symlink tests skipped; compileall and diff check passed. Extracted Windows ZIP started with title `FrameForge — Game Tuning Studio`. GitHub main CI `37878059642` and tag/release CI `37877963505` passed. Published ZIP is 44,607,549 bytes; downloaded checksum matches sidecar: `25a03c3e8ba72c3af015c291701c42e5fcc28e74a962a4a721413c4e94b17d31`. DeepSeek found no confirmed blockers; its follow-up noted that the visible run identity was not included in the labels' accessible names, now addressed in v1.13.1.
- Portfolio commit `45f3d3c` updates the FrameForge card, `A/B Role Swap` tag and v1.13.0 release/download links. Pages run `37878126363` passed; live fetch confirms the release link, ZIP link and new tag. FrameForge commit `1fc5c3c` (feature), `2896081` (atomic signal assertion).
- Prepared: v1.13.0 adds an accessible A/B role-swap action. It validates both selected history indices (rejecting bool, missing, identical and stale values), blocks both Qt selector signals during the swap, clears any existing report/chart/export, and requires an explicit Compare. Swapping alone does not change recent pairs; comparing in the reversed order records a distinct pair.
- Local checks: 135 tests passed, 4 platform-dependent symlink tests skipped; compileall and diff check passed. The Windows ZIP was extracted and launched; its main window title was `FrameForge — Game Tuning Studio`. Archive SHA-256: `2b59d99f62eb5ae02ad98856176aa64122e2c4120c493a5582e3cf04b86b44cc`. DeepSeek review informed additional no-selection, bool, stale-index, group-report clearing, recents and screen-reader checks; no confirmed design blocker remains. GitHub release CI and portfolio update are pending.
- Published: [v1.12.0](https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.12.0), a collapsed, session-only list of the ten most recent distinct manual A/B comparisons. Re-selecting a pair assigns its runs and invalidates any old report; Compare remains a separate action. Auto-comparisons caused by CSV import are excluded. Evicted runs disable their entries; pin/unpin replaces are relinked by identity. The recent list is not persisted or exported.
- Main CI [37877339730](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37877339730) and tag/release CI [37877342736](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37877342736) passed tests, compilation, Windows build and extracted archive startup smoke. Local suite: 132 tests passed, 4 symlink tests skipped; compileall, diff check and Windows build passed. DeepSeek found three issues during review; auto-import pairs are excluded, stale rows carry visible unavailable text and keyboard activation, and stale/same-index pairs are checked before selectors change. Its follow-up found no confirmed defects.
- Downloaded published Windows ZIP (44,606,066 bytes); SHA-256 matches its sidecar: `d4f17ec3dca3ca730875069539d5132a299051279106e0b5159d7d4fe3e82635`.
- Portfolio commit `36a51bf` updates the FrameForge card, tags and v1.12.0 release/download links. Pages run [37877363857](https://github.com/GhosTnever-lkm/GhosTnever-lkm.github.io/actions/runs/37877363857) passed; live fetch confirms the description and links. FrameForge commit `655326e`.

- Published: [v1.11.0](https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.11.0), active baseline shortcut for repeated A/B work. Choose a pinned reference as the session-only baseline; selecting one ordinary run and using the shortcut assigns A/B but still requires explicit Compare. Unpinning the active baseline clears it. No history schema/export changes.
- Main CI [37876719711](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37876719711) and tag/release CI [37876722583](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37876722583) passed tests, compilation, Windows build and extracted archive startup smoke. Local suite: 130 tests passed, 4 symlink tests skipped; compileall, diff check and Windows build passed. DeepSeek review identified only checks to verify; source uses object identity for row lookup, batch retention preserves object references, and tests now cover import survival and disk-write failure. No confirmed blockers remain.
- Published Windows ZIP is 44,602,192 bytes; downloaded copy SHA-256 matches sidecar: `e8a9e38b9752218f9e4519ab90749b235670d8b0a85626c4e2acd001fed7ec6f`.
- Portfolio commit `c677eca` updates the card, tags, release and download links. Pages run [37876744594](https://github.com/GhosTnever-lkm/GhosTnever-lkm.github.io/actions/runs/37876744594) passed; live fetch confirmed v1.11.0 links and feature text. FrameForge commit `5302ff1`.

- Published: [v1.10.0](https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.10.0), read-only view of every benchmark run with the same explicitly labeled game, scene and metric kind. Includes pinned references and current frame-budget summaries; labels row order as local history position, never capture chronology. No history schema or export changes.
- Main CI [37876181534](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37876181534) and tag/release CI [37876184340](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37876184340) passed tests, compilation, Windows build and extracted archive startup smoke. Local suite: 126 tests passed, 4 symlink tests skipped due to environment privileges; compileall, diff check and Windows build passed. DeepSeek independently reviewed the feature; after checking empty labels, wrong metric exclusion, pinned references, dialog screen sizing and stale indices, it reported no confirmed problems or blockers.
- Downloaded published Windows ZIP (44,598,502 bytes); SHA-256 matches sidecar: `eea93c2ff3f28d41bb1de7e9463835312fced2a3b83a547ceebb5d258864f18b`.
- Portfolio commit `cec13c3` updates the card, search tags, release/download links and history-view description. Pages run [37876289236](https://github.com/GhosTnever-lkm/GhosTnever-lkm.github.io/actions/runs/37876289236) passed; live fetch confirms v1.10.0 and ZIP links.

- Published: [v1.9.1](https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.9.1), screen-aware probable-duplicate CSV dialog. It shows the selected CSV number with basename, keeps actions outside a bounded scroll list, and sizes the dialog for its parent window's monitor. No history schema or export change.
- Main CI [37875575797](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37875575797) and tag/release CI [37875578513](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37875578513) passed tests, compilation, Windows build and extracted archive startup smoke. Local suite: 123 tests passed, 4 symlink tests skipped due to environment privileges; compileall, diff check and Windows build passed. DeepSeek review found no confirmed defects in the dialog geometry; it noted only that Qt's final window placement can vary if the parent moves across monitors between sizing and display.
- Downloaded the published Windows ZIP (44,597,468 bytes); SHA-256 matches its sidecar: `9578c1f630895b1c793b5f6ed3e6e8878d2f9b4a2318dfe83400b2dba1e73934`.
- Portfolio commit `e19a98c` updates the FrameForge card, v1.9.1 release/download links and the disambiguated scrollable import UI. Pages run [37875772515](https://github.com/GhosTnever-lkm/GhosTnever-lkm.github.io/actions/runs/37875772515) passed; a live fetch confirms the release and download links and feature text.

- Published: [v1.9.0](https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.9.0), probable duplicate warning during CSV import. The fingerprint compares game, scene, metric kind, all stored aggregate values and user-entered run context, excluding source filename; matching is only a hint, users can keep any candidate, and captures under 30 frames bypass the check. No history schema or export changes.
- GitHub main CI [37874804030](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37874804030) and tag CI [37874806638](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37874806638) passed tests, compilation, Windows build and extracted archive startup smoke. Local suite: 121 tests passed, 4 symlink tests skipped due to environment privileges; compileall, diff check and Windows build passed.
- Downloaded the published Windows ZIP (44,597,197 bytes); SHA-256 matches its published sidecar: `30591e18e946ca89d5c4bdffdd68fcf97d4c24b875af014e15427dd5a4afb278`.
- DeepSeek review found no confirmed blockers after the dialog was changed to distinguish “import unique and skip matches”, “continue selected” and “cancel entire import”. Remaining limitation: exact-float fingerprints may miss a re-serialized/reordered capture if aggregation differs by floating-point rounding; it does not discard such data automatically.
- Portfolio commit `19c7c2d` updates the FrameForge card, tags and v1.9.0 release/download links. Pages run [37875107658](https://github.com/GhosTnever-lkm/GhosTnever-lkm.github.io/actions/runs/37875107658) passed; live page fetch confirms the v1.9.0 link and feature description.

- Published: [v1.8.0](https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.8.0), quick selection of the nearest earlier run with identical game, scene and metric labels. Tag workflow [37873975175](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37873975175) passed unit tests, compilation, Windows build, and archive startup smoke. Main workflow [37873971809](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37873971809) also passed.
- Release ZIP is 44,591,384 bytes; downloaded it from GitHub and verified its published SHA-256: `244cd90f077b83aef227fa886ba52fe605522c77348c3c4da5bcd1f07f89562e`.
- Local v1.8.0 checks: 110 tests pass, 4 symlink tests skip due to environment privileges; compileall, diff check, Windows build, and extracted archive startup pass. DeepSeek's adversarial review found no confirmed blockers; its residual stale-export risk is covered by explicit invalidation of the last comparison and disabling export, including after a prior group comparison.
- Portfolio commit `953135dc48457282ee0aaee19e5598e3fc316d67` updates the FrameForge card and v1.8.0 links. Pages run [37874178067](https://github.com/GhosTnever-lkm/GhosTnever-lkm.github.io/actions/runs/37874178067) passed; a fresh fetch of the live page confirms the v1.8.0 description, release link and Windows ZIP link.
- Published: [v1.7.0](https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.7.0), pinned benchmark reference runs. Tagged CI [37873290878](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37873290878) passed tests, compilation, Windows build and archive startup smoke. Downloaded release ZIP (44,589,762 bytes) and matched its published SHA-256: `92c945b3e1e9b346ba961cbe0e10e4c534491e66321779e87db0704de80e1232`.
- Portfolio commit `a7f493aef53ba0afa79255ca64d30b4a110da045` updates the FrameForge card, tags and Windows links; Pages run [37873330736](https://github.com/GhosTnever-lkm/GhosTnever-lkm.github.io/actions/runs/37873330736) passed and the live page shows v1.7.0 and pinned benchmarks.
- Local v1.7.0 checks: 103 tests pass, 4 symlink tests skip due to environment privileges; compileall, diff check and extracted Windows archive startup pass. DeepSeek adversarial review found no confirmed blockers; an additional warning test covers the edge where unpinning the oldest reference at a full ordinary-history cap removes that same run.

- Published: v1.6.0, descriptive per-run frametime tail spread. Release workflow [37871967572](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37871967572) passed; archive SHA-256 `fe606643804cedae66a3a456ab46cf2625de6b74576c1806a4fa106a63b021c7`.
- Portfolio commit `90ba35b3e6dc4427ed6e9d88cd7740faa3a1f5f6` updates the FrameForge card to v1.6.0; Pages run [37872052967](https://github.com/GhosTnever-lkm/GhosTnever-lkm.github.io/actions/runs/37872052967) passed and the live page was verified.
- Local v1.6.0 release checks: 99 tests passed; 4 symlink tests skipped due to environment privileges; compile, package and release smoke passed.

- Published: v1.4.0, searchable benchmark history list and explicit group-filter scope.
- GitHub Actions release run [37869978554](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37869978554) passed tests, compilation, Windows build and release publication.
- Published archive: [FrameForge v1.4.0](https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.4.0), `FrameForge-1.4.0-windows-x64.zip`; SHA-256 `e0d814e9f7c9bccb8e421a53b518a8695f3ea1a4db3469b9471913e3b831d604`.
- Downloaded the published archive, verified its SHA-256 and launched its EXE; the app window responded with title `FrameForge — Game Tuning Studio`.
- Portfolio updated in commit `d4798a94dd1f181a5b2c5987e59692bedff0dcbc`; Pages deployment [37870291926](https://github.com/GhosTnever-lkm/GhosTnever-lkm.github.io/actions/runs/37870291926) succeeded. Reloaded the live page and confirmed its FrameForge description, release link and Windows ZIP link show v1.4.0.
- Local v1.4.0 baseline: 88 unit tests pass; 4 platform-dependent symlink tests are skipped; compileall, diff check and GUI smoke pass.

- Published: v1.3.0, batch benchmark CSV import.
- Local checks for v1.3.0: 88 unit tests pass; 4 platform-dependent symlink tests are skipped; compileall, diff check and GUI smokes pass.
- GitHub Actions run [37869482152](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37869482152) passed tests, Windows portable build and startup smoke.
- Published archive: [FrameForge v1.3.0](https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.3.0), `FrameForge-1.3.0-windows-x64.zip`; SHA-256 `a3b1dee165cbd38beebffa69dd7f5e1ccc597f794e8a38217f870c215e07830b`.
- Downloaded the v1.3.0 archive, verified its SHA-256, extracted it and launched the EXE; the window title was `FrameForge — Game Tuning Studio` and the process responded.
- DeepSeek reviewed the batch import; after retracting a false positive, it found no confirmed blockers. The review scope clarified per-file error handling, history truncation, group minima, filter behavior, and auto-pair visibility.
- Portfolio card: [live site](https://ghostnever-lkm.github.io/) now links to v1.3.0 and describes frame budgets and batch CSV import. Deployment run [37869842446](https://github.com/GhosTnever-lkm/GhosTnever-lkm.github.io/actions/runs/37869842446) succeeded and the refreshed page shows the new copy and links.

- Published: v1.2.0, cross-game frame-budget reporting.
- Local v1.2.0 checks: 88 unit tests pass; 4 platform-dependent symlink tests are skipped; compileall, diff check and offscreen GUI smoke pass.
- GitHub Actions run [37869046502](https://github.com/GhosTnever-lkm/frameforge/actions/runs/37869046502) passed tests, Windows portable build and startup smoke.
- Published archive: [FrameForge v1.2.0](https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.2.0), `FrameForge-1.2.0-windows-x64.zip`; SHA-256 `66fbef54b64881b252890330a24f3a886d7d02a9a04b837002b6b6e2a9c57ac4`.
- Downloaded release archive, verified its SHA-256, extracted it and launched `FrameForge.exe`; the window title was `FrameForge — Game Tuning Studio` and the process responded.
- DeepSeek reviewed v1.2.0 and found no blockers in the described scope.

## v1.2.0 behavior

- Stores seven overlapping aggregate frame-budget counts at CSV import for the supported FPS presets; raw frame samples remain discarded.
- Shows the selected threshold in A/B and repeated-run reports; old history migrates to schema v8 with an explicit unavailable value.
- Keeps single and group exports aggregate-only and includes the selected target.

## v1.3.0 behavior

- Multi-select benchmark CSV import applies one shared game/scene/checklist context, saves valid selections as a single bounded batch, and reports per-file failures.
- Keeps history aligned with the newest 100 runs in memory and on disk; removes group references to evicted runs and validates minimum group size on compare.
- Adds numbered error/warning rows and counts omitted messages; README documents automatic comparison of the newest retained pair.
- Offscreen GUI smokes pass for mixed valid/invalid imports, 100-run truncation, group cleanup, and 13-file error summaries.

## v1.4.0 behavior

- Adds a case-insensitive history-list filter across CSV name, game, scene, metric type, local note, setting snapshot and checklist labels. It does not alter the saved history.
- Clears list selection when the filter changes; existing A/B group membership persists and status reports how many group members are hidden.
- Makes the scope explicit: Baseline/Variant selectors and exports use full history; group reports use every assigned member. A successful batch import clears the active filter before showing the newest pair.
- Local checks: 88 unit tests pass (4 symlink skips); compileall and diff check pass. GUI smokes cover case-insensitive/literal search, zero matches, reset, selection/group behavior, full combo options, hidden group counts, and import resetting the filter.
- DeepSeek review found no confirmed blockers. Remaining design choice: the filter is only for the group-assignment list; Baseline/Variant selectors remain full-history.

## v1.5.0 behavior

- Adds a case-insensitive literal search across the full benchmark history to locate entries for Baseline/Variant. Search results keep the source history index in `UserRole`; duplicate filenames have distinct numbered rows.
- Typing, clearing or getting no matches never changes the selected pair. Users explicitly assign one selected result to A or B. Changing a selected pair clears its old pair report/export until a fresh comparison is run; group reports remain unaffected.
- Adds selected-index bounds validation and five unit tests for empty query, literal/case-insensitive matching, duplicate labels/original indices, checklist labels and setting snapshots.
- Local test suite currently: 94 passed, 4 platform-dependent symlink skips. `compileall` and `git diff --check` pass; the UI version matches `VERSION`. Qt offscreen smokes verify duplicate-name identities, a filtered row 0 assigning original history index 47, no-result behavior, invalid pair rejection, and pair-report/group-export state.
- DeepSeek recommended this separate search/list/explicit-assignment design. Its first code-review concern about `itemData(index)` was resolved by an exact Qt smoke where result row 0 stores history index 47 and correctly assigns combo item 47; DeepSeek withdrew the concern and confirmed no blockers. The concern about batch truncation is addressed by the import flow synchronously selecting and comparing the newest retained pair before returning.

## Next

1. Continue the next focused FrameForge improvement, then update this record with verified evidence.

## Последняя итерация — FrameForge v1.16.0, CS:GO Legacy profiles (validation pending)

- Added Steam manifest detection for CS:GO Legacy app 4465480, an in-app tuning page with refresh-oriented presets/FPS limits/graphics toggles and a CFG preview, generated `frameforge_menu.cfg` and FPS profile, and a managed `autoexec.cfg` section with timestamped backups. Launch uses Steam `-applaunch` arguments to load the in-game console profile; the former separate companion panel is no longer launched.
- Live Windows build `dist/FrameForge/FrameForge.exe` opened. UI Automation confirmed the detected path `D:\SteamLibrary\steamapps\common\csgo legacy\csgo\cfg`; the tuning screen selected `Максимальный FPS` and saved `fps_max 0` plus `r_dynamic 0` to the actual game folder. Existing autoexec backups are present.
- Local PyInstaller archive `FrameForge-1.16.0-windows-x64.zip`, SHA-256 `ddae34d5f8a84b9028f2f6ee06cca3a646ac042905a21f105f503ad7d83d93d5`. `compileall` and `git diff --check` pass. One normal unittest run failed to load Qt due DLL search path; a second run with explicit DLL directories/offscreen progressed through tests but hung in the GUI suite and was interrupted. CI quality run is required before release.
- CS:GO was already running before the generated launch options were applied and did not close through the normal window-close request. The in-game console startup path and any FPS change are therefore not confirmed in the live game. Baseline reported by the user is about 240 FPS; +20% (about 288 FPS) has not been measured and is not guaranteed. Do not advertise a minimum FPS gain.
- Release/push, portfolio update, and announcement are pending successful CI and a clean in-game startup verification. The full mouse-driven HUD overlay is not implemented; the current in-game menu is a Source console text menu, with tuning performed in FrameForge.
- GitHub CI run 37902424700: all 106 unit tests and compileall succeeded; packaging failed because the generated icon assets were untracked and absent from the checkout. Adding both PNG/ICO assets in follow-up commit before release.

## Опубликовано — FrameForge v1.16.0

- GitHub release: https://github.com/GhosTnever-lkm/frameforge/releases/tag/v1.16.0. В релизе есть Windows ZIP и SHA-256 sidecar; checksum проверенной публикации: `065a1765b47e5bc98400dcc621dfe40c4f9b919f649f4c67c99c4c2015797269`.
- GitHub Actions main `37902668063` и tag/release `37902886450` прошли 106 тестов, compileall, Windows build и archive smoke. Первый запуск публикации выявил отсутствующие иконки; добавление ресурсов исправило packaging, tag workflow прошёл.
- Профиль CS:GO Legacy использует обнаружение Steam appmanifest, настройки и CFG в папке игры, создание резервных копий и запуск через Steam с открытием консоли. В живом FrameForge подтверждено обнаружение `D:\SteamLibrary\steamapps\common\csgo legacy\csgo\cfg` и сохранение профиля. Опубликованный SHA-256 сверялся со sidecar.
- Важно: интерфейс внутри игры пока Source console text menu; отдельный mouse-driven HUD не сделан. CS:GO уже был запущен до установки параметров, свежий запуск через FrameForge и появление меню в новой сессии не подтверждены. FPS до/после не замерен: целевые 288 FPS (+20% от сообщённых пользователем ~240) не достигнуты/не доказаны и не обещаются.
- Профиль README обновлён коммитом `d9c9430`. Портфолио обновлено коммитом `1d8f127`, Pages run `37903415412` прошёл, публичная страница проверена; опубликован release `Portfolio v1.3.11`: https://github.com/GhosTnever-lkm/GhosTnever-lkm.github.io/releases/tag/v1.3.11.
- Публичный Boosty-пост: https://boosty.to/azizazimov/posts/b1d94fbd-e449-43d5-84ec-ec6d42bee85f; теги: frameforge, оптимизация игр, cs:go legacy, бенчмарк. Рекламный и AI-content переключатели оставлены выключенными. Пост не утверждает гарантированный прирост FPS.

## Подготовка — FrameForge v1.16.1 (2026-10-09)

- Исправлена действующая страница «Игры»: красный контрастный прицел и автозагрузка игрового console-menu доступны переключателями в профиле CS:GO Legacy. Красный цвет прицела явно не назван перекраской моделей противников; поиск не подтвердил штатный CFG-переключатель для этого.
- Перед записью CFG при запуске появляется подтверждение; заменяемые файлы сохраняются в backup. Переключатель автозагрузки убирает только помеченный FrameForge-блок autoexec и сохраняет пользовательские строки. Ошибки записи показываются и останавливают запуск; Steam можно запускать и при выключенной автозагрузке.
- При включённой автозагрузке autoexec открывает игровую консоль для текстового меню. Это не мышиный HUD. Три новых теста autoexec проходят; core suite: 98 тестов, 4 symlink-теста пропущены по окружению. Полный GUI suite локально завершился Windows process abort после прохождения тестовых строк; нужен CI.
- Версия 1.16.1 ещё не собрана и не опубликована. Нужны успешные CI/build, commit/tag/release. Свежий запуск CS:GO и FPS до/после не проверены; цель 288 FPS / +20% остаётся недоказанной.

## Подготовка — FrameForge v1.16.1 (CI pending)

- Добавлен практический red high-contrast crosshair preset (не перекраска врагов) и управляемая авто-загрузка текстового console-menu на текущей странице Games. Autoexec managed-block включает `toggleconsole` при включённом меню, чтобы его показать.
- Исправлены write/launch ошибки CS:GO: подтверждение записи перед запуском, корректная установка/снятие только своего autoexec-блока, startup через appid, продолжение Steam launch при отключённом меню, статус фактического делегирования запуска. README и changelog обновлены.
- Тесты: новые 3 autoexec unit tests pass; core 98 pass/4 symlink skip. Полный unittest discover завершился кодом `-1073740791` (Windows process abort после вывода успешных тестов), CI требуется для полного подтверждения.
- Portable build собран отдельно `dist-v1.16.1/FrameForge-1.16.1-windows-x64.zip`, SHA-256 `3d46363a82016f29d2bf670e89308870c0fe3599d3b4659ffb968da829d7fbbd`; распакованный EXE стартовал с окном `FrameForge — Game Tuning Studio`. Windows UI Automation подтвердил оба новых чекбокса на странице «Игры».
- В игровых бинарниках локальной CS:GO Legacy найдены `mat_disable_bloom`, `mat_disable_fancy_blending`, `r_dynamic`, sky toggles и RGB crosshair cvars. Цвет вражеских player models обычным CFG не подтверждён. Свежий запуск игры и FPS до/после не проведены; +20% / 288 FPS не подтверждены.
- Версия ещё не запушена и не релизнута. Следующий шаг: коммит и GitHub CI; после зелёного CI — tag/release, портфолио и публикационный пост.
