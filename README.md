# Blender Video Editing Workflow

Editable Blender VSE workflows for whitebox shot references, AI-video return editing and rendered animation. A shared extension core, SHA-bound CLI snapshot, portable agent skill and four declarative SDR templates are distributed together.

**Distribution 0.1.3 · CLI 0.63.0 · addon 0.1.1 · template library 0.1.0 · GPL-3.0-or-later**

[中文说明](README.zh-CN.md) · [Installation and usage](docs/VIDEO-EDITING.md) · [Validation](docs/VALIDATION.md) · [Templates](templates/video/README.md) · [Agent skill](skills/blender-video-editing/SKILL.md)

## Download and run

Download the source ZIP and optional addon/skill/template ZIPs from [Releases](https://github.com/tsist/blender-video-editing-workflow/releases). Python 3.12+ and Blender must already be installed; the tested native baseline is Windows with Blender 5.2.1 LTS. Run from the extracted source root:

```powershell
python -B tools/blenderctl/cli.py video describe
python -B templates/video/cli.py list
```

For a separately installed skill/template archive, set `BLENDERCTL_ROOT` to this source root. The template compiler validates the pinned runtime identity. Keep `tools/` intact. This repository carries supporting workflow modules as source dependencies; their presence does not expand this release's tested video scope.

## Included

- Stable shot IDs, multiple AI candidates and selected-version tracking.
- Reference and final-edit handoff, bounded retiming/freeze, known-project manual-edit continuation.
- Original-speed dialogue/BGM/SFX, fades, editable titles/Chinese subtitles and explicit outputs.
- `whitebox-board`, `ai-final`, `cg-clean`, `subtitle-readable`; custom JSON presets and explicit batch compilation.
- Small synthetic example, inventory verification and reproducible source-only ZIP builds.

Templates are SDR, sequential and hard-cut only. Technical PQ evidence is bounded; 4K HDR is unqualified. HLG, arbitrary foreign VSE continuation, audio time-stretch/nonzero pan and HDR-device viewing are outside scope. Complex performance and real long-form works remain future validation targets. See [usage and limits](docs/VIDEO-EDITING.md).

## Verify

```powershell
python -B scripts/verify_release.py
python -B templates/video/test_template_library.py
python -B scripts/build_release.py
```

Blender, FFmpeg, fonts and footage are not bundled. Install/download those separately under their licenses. Native tests are opt-in and do not operate the user's GUI session. The generic upstream CLI is maintained at [tsist/blenderctl](https://github.com/tsist/blenderctl); no Git submodules are needed.
