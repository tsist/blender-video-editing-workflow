# Managed batch editing on Blender 5.3

Use [blenderctl v0.64.0](https://github.com/tsist/blenderctl/releases/tag/v0.64.0) and its production package `1.0.0` with Windows Blender 5.3.0. Submit a saved, managed timeline through `production.run` with `domain` set to `video`. Existing `video` operations create and inspect managed timelines. See the [video workflow guide](VIDEO-EDITING.md).

## Locate each edit

| Position | Example | Resolution |
| --- | --- | --- |
| Absolute frame | `{"frame": 93}` | Frame in the source timeline. |
| Shot and edge | `{"shot_id": "S020", "edge": "start", "offset": 52}` | A shot boundary in the source timeline with an optional frame offset. |
| Named marker | `{"marker": "STATUS_LIGHT"}` | The frame of a unique marker in the source timeline. |
| Earlier result | `{"result_of": "remove_wait", "edge": "start"}` | An earlier operation's actual start or end. |

For the first three forms, the editor resolves the initial point before edits and applies intervening ripple shifts on the selected tracks. The earlier-result form starts from the actual boundary of that operation and applies later shifts. A deleted point or conflicting track mappings causes a conflict. Each operation names its tracks in `channels`. Editing ranges are half open, so frames 93 through 100 are `[93, 101)`.

## Submit a picture-only example

In this example, `source.blend` contains the managed scene `Editorial` with workflow `sequence_01`, a shot `S020` starting at frame 49 and spanning through frame 153 on track 4, and a unique `STATUS_LIGHT` marker at frame 153. The example uses color strips and has no external media. Substitute your scene, workflow, track, positions and saved file as needed. Run from the extracted **blenderctl** source root.

```powershell
$ctl = (Resolve-Path -LiteralPath './blenderctl.ps1').Path
$source = (Resolve-Path -LiteralPath './source.blend').Path
$sha = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
$request = @{
  schema_version = '1.0'
  command = 'production.run'
  params = @{
    domain = 'video'
    release = '1.0.0'
    file = $source
    expected_sha256 = $sha
    request = @{
      version = '1.0'
      scene = 'Editorial'
      workflow_id = 'sequence_01'
      atomicity = 'group'
      operations = @(
        @{
          id = 'cut_wait'; op = 'split'; channels = @(4)
          at = @{ frame = 93 }
        },
        @{
          id = 'remove_wait'; op = 'remove'; channels = @(4); ripple = $false
          start = @{ result_of = 'cut_wait'; edge = 'start' }
          end = @{ shot_id = 'S020'; edge = 'start'; offset = 52 }
        },
        @{
          id = 'insert_detail'; op = 'insert'; channels = @(4); duration = 8; ripple = $false
          at = @{ result_of = 'remove_wait'; edge = 'start' }
          clips = @(@{ id = 'detail'; kind = 'COLOR'; channel = 4; duration = 8; color = @(0.2, 0.4, 0.6, 1) })
        },
        @{
          id = 'cut_light'; op = 'split'; channels = @(4)
          at = @{ marker = 'STATUS_LIGHT' }
        }
      )
    }
  }
}
$request | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath './batch-edit.json' -Encoding utf8
& $ctl --compact request './batch-edit.json'
```

Use the default `atomicity=group` to let independent groups commit after a conflict. Operations with a shared ripple influence, explicit `group` or result dependency can be committed together. Use `atomicity=batch` when any conflict must restore the entire edit. A rejected batch produces no candidate. A partial group result can produce a candidate with its committed groups.

## Check external media and the result

If the input or an insertion refers to external files, add every file to `params.resources`, with its absolute `file` and lowercase `expected_sha256`. Include each image sequence frame, video, audio, font, linked library and independent proxy file. Movie operations also require `params.request.media_probe` and a matching resource row. The approved Windows executable is `tools/ffmpeg/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe` under the **blenderctl** source root. Verify its SHA-256 against `f0d36ecbbdd3bcfac3efa078c96c7271c2e68b3810595552ac3b7f17e9a65c52`. Get it separately under its license. The video stream must be stream 0, at the timeline frame rate, with constant frame timing, zero start and square pixels.

Read `production-report.json` for each requested and actual position, affected strips, source offsets, and rollback status. Independently reopen the saved candidate. Compare decoded frames across the cuts and confirm locked tracks, captions, markers and audio timing. The source file remains available as the starting point for another revision.
