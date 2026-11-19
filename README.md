# Blender Video Editing Workflow

Release **0.1.4** adds Blender 5.3 support, ripple editing, and basic OpenTimelineIO exchange for hard cuts.

Editable Blender VSE workflows for whitebox shot references, AI-video return editing and rendered animation. A shared extension core, SHA-bound CLI snapshot, portable agent skill and four declarative SDR templates are distributed together.

**Distribution 0.1.4 · CLI 0.63.0 · addon 0.1.2 · template library 0.1.0 · GPL-3.0-or-later**

[中文说明](README.zh-CN.md) · [Installation and usage](docs/VIDEO-EDITING.md) · [Validation](docs/VALIDATION.md) · [Templates](templates/video/README.md) · [Agent skill](skills/blender-video-editing/SKILL.md)

## Download and run

Download the source ZIP and optional addon, skill and template ZIPs from [Releases](https://github.com/tsist/blender-video-editing-workflow/releases). On Windows use the `video-blenderctl.ps1` launcher with an explicit Blender executable. The release was tested on Blender 5.3.0 and 5.2.1 LTS. Run from the extracted source root:

```powershell
$Blender = (Get-Command blender.exe).Source
.\video-blenderctl.ps1 --blender $Blender video describe
python -B templates/video/cli.py list
```

For a separately installed skill/template archive, set `BLENDERCTL_ROOT` to this source root. The template compiler validates the pinned runtime identity. Keep `tools/` intact. This repository carries supporting workflow modules as source dependencies; their presence does not expand this release's tested video scope.

## Included

- Stable shot IDs, multiple AI candidates and selected-version tracking.
- Reference and final-edit handoff, bounded retiming/freeze, known-project manual-edit continuation.
- Original-speed dialogue/BGM/SFX, fades, editable titles/Chinese subtitles and explicit outputs.
- `whitebox-board`, `ai-final`, `cg-clean`, `subtitle-readable`; custom JSON presets and explicit batch compilation.
- Small synthetic example, inventory verification and reproducible source-only ZIP builds.
- `video ripple` lengthens or shortens a managed cut while shifting downstream video, audio and subtitles. `video otio export` and `video otio import` exchange cut-only timelines with video and audio on Blender 5.3.

Templates are SDR, sequential and hard-cut only. Technical PQ evidence is bounded; 4K HDR is unqualified. HLG, arbitrary foreign VSE continuation, audio time-stretch/nonzero pan and HDR-device viewing are outside scope. Complex performance and real long-form works remain future validation targets. See [usage and limits](docs/VIDEO-EDITING.md).

## Verify

```powershell
python -B scripts/verify_release.py
python -B templates/video/test_template_library.py
python -B scripts/build_release.py
```

Blender, FFmpeg, fonts and footage are not bundled. Install/download those separately under their licenses. Native tests are opt-in and do not operate the user's GUI session. The generic upstream CLI is maintained at [tsist/blenderctl](https://github.com/tsist/blenderctl); no Git submodules are needed.
