"""Fresh Blender process: import an exported OTIO file and compare native cuts."""
import json
from pathlib import Path
import sys
import traceback

import bpy


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')


def _rows(scene):
    result = []
    for strip in scene.sequence_editor.strips:
        if strip.type not in ('MOVIE', 'SOUND'):
            raise RuntimeError('Imported OTIO contains unsupported strip type: ' + strip.type)
        if strip.type == 'MOVIE':
            filename, kind, source_in = strip.filepath, 'MOVIE', float(strip.left_handle - strip.content_start)
        else:
            filename, kind, source_in = strip.sound.filepath, 'SOUND', float(strip.left_handle - strip.content_start)
        if abs(source_in - round(source_in)) > 1e-6:
            raise RuntimeError('Imported OTIO source_in is not integral: ' + strip.name)
        result.append({'name': strip.name, 'kind': kind, 'channel': int(strip.channel),
                       'start': int(strip.left_handle), 'duration': int(strip.duration),
                       'source_in': int(round(source_in)), 'file': str(Path(filename).resolve()),
                       'mute': bool(strip.mute)})
    return sorted(result, key=lambda row: (row['channel'], row['start'], row['name']))


def main(request_path):
    config = _read(request_path)
    output = Path(config['output'])
    report = {'status': 'failed', 'version': list(bpy.app.version),
              'build': bpy.app.build_hash.decode() if isinstance(bpy.app.build_hash, bytes) else str(bpy.app.build_hash)}
    try:
        otio = Path(config['otio']['file'])
        if not otio.is_file():
            raise RuntimeError('OTIO file missing')
        bpy.ops.wm.read_factory_settings(use_empty=True)
        before = {scene.name for scene in bpy.data.scenes}
        if not bpy.ops.wm.otio_import.poll():
            raise RuntimeError('Native OTIO import is unavailable')
        result = bpy.ops.wm.otio_import(filepath=str(otio))
        if 'FINISHED' not in result:
            raise RuntimeError('Native OTIO import did not finish')
        created = [scene for scene in bpy.data.scenes if scene.name not in before]
        if len(created) != 1:
            raise RuntimeError('Native OTIO import created ' + str(len(created)) + ' scenes')
        scene = created[0]
        if scene.sequence_editor is None:
            raise RuntimeError('Native OTIO import created no sequence editor')
        expected = sorted(config['expected'], key=lambda row: (row['channel'], row['start'], row['name']))
        actual = _rows(scene)
        if actual != expected:
            report['expected'] = expected
            report['actual'] = actual
            raise RuntimeError('Native OTIO cut table differs from exported source')
        fps = scene.render.fps / scene.render.fps_base
        expected_fps = config['timeline']['fps'][0] / config['timeline']['fps'][1]
        if abs(fps - expected_fps) > 1e-5 * max(1.0, expected_fps):
            raise RuntimeError('Native OTIO fps differs')
        if (int(scene.frame_start) != int(config['timeline']['frame_start']) or
                int(scene.frame_end) != int(config['timeline']['frame_end_exclusive']) - 1):
            raise RuntimeError('Native OTIO frame range differs')
        report.update(status='passed', scene=scene.name, rows=actual,
                      timeline={'fps': [scene.render.fps, scene.render.fps_base],
                                'frame_start': int(scene.frame_start),
                                'frame_end_exclusive': int(scene.frame_end) + 1})
    except Exception as exc:
        report['error'] = str(exc)
        report['traceback'] = traceback.format_exc()
    _write(output, report)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    if '--' in sys.argv:
        arguments = sys.argv[sys.argv.index('--') + 1:]
    else:
        arguments = sys.argv[1:]
    if len(arguments) != 1:
        raise SystemExit('usage: otio_verifier.py -- REQUEST.json')
    raise SystemExit(main(arguments[0]))
