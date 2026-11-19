"""Cut-only OpenTimelineIO exchange built on Blender 5.3's bundled OTIO.

No host process imports this module: it needs Blender's ``opentimelineio``.
The wire format is a normal OTIO timeline with one track per VSE channel.
Blender-specific identity is stored in namespaced metadata, but the media,
cut points and source ranges remain readable by any OTIO consumer.
"""
from copy import deepcopy
from fractions import Fraction
import importlib.util
import math
from pathlib import Path
import re

from video_editing_workflow_addon.contract import WorkflowError, validate_clip
from video_editing_workflow_addon import core

TAG = 'blender_ai_video'
SCHEMA = '1.0'


def _error(code, message):
    raise WorkflowError(code, message)


def otio():
    if importlib.util.find_spec('opentimelineio') is None:
        _error('UNSUPPORTED', 'Cut-only OTIO requires Blender 5.3 or newer with bundled OpenTimelineIO')
    import opentimelineio as module
    return module


def _rate(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        _error('INVALID_REQUEST', 'OTIO time rate must be positive and finite')
    return Fraction(value).limit_denominator(1000000)


def _frames(time, fps):
    if time is None:
        _error('INVALID_REQUEST', 'OTIO time is missing')
    try:
        value = float(time.value) * (fps.numerator / fps.denominator) / float(time.rate)
    except (AttributeError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        _error('INVALID_REQUEST', 'OTIO time is malformed')
    if not math.isfinite(value):
        _error('INVALID_REQUEST', 'OTIO time is not finite')
    nearest = round(value)
    if abs(value - nearest) > 1e-6:
        _error('UNSUPPORTED', 'OTIO time is not on an integer frame boundary')
    return int(nearest)


def _fps_from_metadata(metadata, rate):
    timeline = metadata.get('timeline') if isinstance(metadata, dict) else None
    fps = timeline.get('fps') if isinstance(timeline, dict) else None
    if fps is None:
        return Fraction(rate).limit_denominator(1000000)
    if not isinstance(fps, (list, tuple)) or len(fps) != 2:
        _error('CONFLICT', 'OTIO metadata has an invalid timeline fps')
    try:
        fps = [int(v) for v in fps]
    except (TypeError, ValueError, OverflowError):
        _error('CONFLICT', 'OTIO metadata has an invalid timeline fps')
    if any(isinstance(v, bool) or v <= 0 or v != float(value) for v, value in zip(fps, timeline['fps'])):
        _error('CONFLICT', 'OTIO metadata has an invalid timeline fps')
    result = Fraction(fps[0], fps[1])
    if abs(float(result) - rate) > 1e-9 * max(1.0, rate):
        _error('CONFLICT', 'OTIO metadata fps differs from its time rate')
    return result


def _url_file(url):
    if not isinstance(url, str) or not url:
        _error('INVALID_REQUEST', 'OTIO media reference has no target URL')
    if url.startswith('file:'):
        module = otio()
        url = module.url_utils.url_to_filepath(url)
    path = Path(url)
    if not path.is_absolute():
        _error('UNSUPPORTED', 'OTIO media target must be an absolute local path: ' + url)
    return str(path.resolve())


def _clip_id(name, used):
    value = re.sub(r'[^A-Za-z0-9_-]', '_', str(name or 'clip'))
    if not value or not value[0].isalpha():
        value = 'clip_' + value
    value = value[:64].rstrip('_-') or 'clip'
    candidate, index = value, 2
    while candidate in used:
        suffix = '_' + str(index)
        candidate = value[:64 - len(suffix)].rstrip('_-') + suffix
        index += 1
    used.add(candidate)
    return candidate


def _metadata(row):
    value = deepcopy(row)
    value.pop('full_length', None)
    return value


def timeline_from_specs(specs):
    module = otio()
    timeline_spec = specs['timeline']
    rate = Fraction(*timeline_spec['fps'])
    rate_float = float(rate)
    start = timeline_spec['frame_start']
    timeline = module.schema.Timeline(name=specs['scene'])
    timeline.global_start_time = module.opentime.RationalTime(start, rate_float)
    timeline.metadata[TAG] = {'schema_version': SCHEMA, 'workflow_id': specs['workflow_id'],
                              'timeline': deepcopy(timeline_spec), 'channels': specs['channels'],
                              'scope': deepcopy(specs.get('scope', {}))}
    by_channel = {}
    for row in specs['clips']:
        by_channel.setdefault(row['channel'], []).append(row)
    for channel in range(1, specs['channels'] + 1):
        rows = sorted(by_channel.get(channel, []), key=lambda row: (row['start'], row['id']))
        kinds = {row['kind'] for row in rows}
        if kinds - {'MOVIE', 'SOUND'} or len(kinds) > 1:
            _error('UNSUPPORTED', 'One OTIO track cannot mix clip kinds')
        kind = (module.schema.TrackKind.Audio if kinds == {'SOUND'}
                else module.schema.TrackKind.Video)
        track = module.schema.Track(name=('A' if kind == module.schema.TrackKind.Audio else 'V') + str(channel),
                                    kind=kind)
        track.metadata[TAG] = {'schema_version': SCHEMA, 'channel': channel}
        cursor = 0
        for row in rows:
            offset = row['start'] - start
            if offset < cursor:
                _error('CONFLICT', 'Overlapping cuts on channel ' + str(channel))
            if offset > cursor:
                track.append(module.schema.Gap(source_range=module.opentime.TimeRange(
                    module.opentime.RationalTime(0, rate_float),
                    module.opentime.RationalTime(offset - cursor, rate_float))))
            source = row['source']
            reference = module.schema.ExternalReference(
                target_url=source['files'][0]['file'],
                available_range=module.opentime.TimeRange(
                    module.opentime.RationalTime(0, rate_float),
                    module.opentime.RationalTime(row['full_length'], rate_float)))
            clip = module.schema.Clip(
                name=row['name'],
                media_reference=reference,
                source_range=module.opentime.TimeRange(
                    module.opentime.RationalTime(source['source_in'], rate_float),
                    module.opentime.RationalTime(row['duration'], rate_float)))
            clip.enabled = not row['mute']
            clip.metadata[TAG] = {'schema_version': SCHEMA, 'kind': row['kind'],
                                  'spec': _metadata(row), 'full_length': row['full_length']}
            track.append(clip)
            cursor = offset + row['duration']
        total = timeline_spec['frame_end_exclusive'] - start
        if cursor > total:
            _error('CONFLICT', 'OTIO cut exceeds the authored timeline')
        if cursor < total:
            track.append(module.schema.Gap(source_range=module.opentime.TimeRange(
                module.opentime.RationalTime(0, rate_float),
                module.opentime.RationalTime(total - cursor, rate_float))))
        timeline.tracks.append(track)
    return timeline


def write_timeline(timeline, path):
    module = otio()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    module.adapters.write_to_file(timeline, str(path))
    return path


def read_timeline(path):
    module = otio()
    try:
        return module.adapters.read_from_file(str(path))
    except Exception as exc:
        _error('INVALID_REQUEST', 'Cannot read OTIO timeline: ' + str(exc))


def _timeline_metadata(timeline):
    value = timeline.metadata.get(TAG) if timeline.metadata is not None else None
    if value is None:
        return {}
    value = _plain(value)
    if not isinstance(value, dict):
        _error('CONFLICT', 'OTIO metadata namespace is malformed')
    if value.get('schema_version') != SCHEMA:
        _error('UNSUPPORTED', 'Unknown Blender OTIO metadata version')
    return value


def _plain(value):
    if value is None or isinstance(value, (str, bytes, bool, int, float)):
        return value
    if hasattr(value, 'items'):
        return {str(key): _plain(item) for key, item in value.items()}
    try:
        return [_plain(item) for item in value]
    except TypeError:
        pass
    return value


def _one_external(clip):
    module = otio()
    if getattr(clip, 'effects', None) or getattr(clip, 'markers', None):
        _error('UNSUPPORTED', 'OTIO clip effects/markers are outside cut-only scope')
    references = clip.media_references() if callable(clip.media_references) else clip.media_references
    references = list(references.values())
    if len(references) != 1:
        _error('UNSUPPORTED', 'OTIO clip must have exactly one media reference')
    reference = references[0]
    if not isinstance(reference, module.schema.ExternalReference):
        _error('UNSUPPORTED', 'OTIO cut-only clips require ExternalReference media')
    return reference


def _descriptor(path, resources):
    row = resources.get(path.casefold())
    if row is None:
        _error('CONFLICT', 'OTIO media is not declared in resources: ' + path)
    return {'file': path, 'expected_sha256': row['expected_sha256']}


def specs_from_timeline(timeline, scene, workflow_id, resources):
    """Convert one cut-only OTIO timeline into a managed create manifest."""
    module = otio()
    if not isinstance(timeline, module.schema.Timeline):
        _error('INVALID_REQUEST', 'Expected an OTIO Timeline')
    if timeline.tracks is None:
        _error('INVALID_REQUEST', 'OTIO timeline has no tracks')
    metadata = _timeline_metadata(timeline)
    global_start = timeline.global_start_time
    rate = _rate(global_start.rate if global_start is not None else 24.0)
    fps = _fps_from_metadata(metadata, float(rate))
    timeline_meta = metadata.get('timeline') if isinstance(metadata.get('timeline'), dict) else {}
    frame_start = timeline_meta.get('frame_start', _frames(global_start, fps) if global_start else 0)
    if isinstance(frame_start, bool) or not isinstance(frame_start, int):
        _error('CONFLICT', 'OTIO timeline start must be an integer frame')
    width = timeline_meta.get('width', 1920)
    height = timeline_meta.get('height', 1080)
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in (width, height)):
        _error('CONFLICT', 'OTIO timeline canvas metadata is invalid')
    if len(timeline.tracks) > 128:
        _error('UNSUPPORTED', 'OTIO timeline exceeds 128 native channels')
    clips, used, used_names, max_end, max_cursor = [], set(), set(), frame_start, 0
    for channel, track in enumerate(timeline.tracks, 1):
        if not isinstance(track, module.schema.Track):
            _error('UNSUPPORTED', 'OTIO nested stacks/tracks are outside cut-only scope')
        if track.kind not in (module.schema.TrackKind.Video, module.schema.TrackKind.Audio):
            _error('UNSUPPORTED', 'OTIO track kind must be Video or Audio')
        if track.effects or track.markers or track.source_range is not None:
            _error('UNSUPPORTED', 'OTIO track effects/markers/source_range are outside cut-only scope')
        kind = 'SOUND' if track.kind == module.schema.TrackKind.Audio else 'MOVIE'
        track_enabled = bool(track.enabled)
        cursor = 0
        for item in track:
            if isinstance(item, module.schema.Gap):
                cursor += _frames(item.source_range.duration, fps)
                continue
            if not isinstance(item, module.schema.Clip):
                _error('UNSUPPORTED', 'OTIO transitions/compositions are outside cut-only scope')
            if item.source_range is None:
                _error('UNSUPPORTED', 'OTIO clip without source_range has no cut boundary')
            duration = _frames(item.source_range.duration, fps)
            if duration < 1:
                _error('INVALID_REQUEST', 'OTIO clip duration must be positive')
            reference = _one_external(item)
            path = _url_file(reference.target_url)
            descriptor = _descriptor(path, resources)
            available = reference.available_range
            available_start = _frames(available.start_time, fps) if available is not None else 0
            source_in = _frames(item.source_range.start_time, fps) - available_start
            if source_in < 0:
                _error('INVALID_REQUEST', 'OTIO source_range begins before available_range')
            if available is not None:
                available_duration = _frames(available.duration, fps)
                if source_in + duration > available_duration:
                    _error('INVALID_REQUEST', 'OTIO source_range exceeds available_range: ' + str(item.name))
            start = frame_start + cursor
            cursor += duration
            max_end = max(max_end, start + duration)
            meta = _plain(item.metadata.get(TAG)) if item.metadata is not None else None
            spec = meta.get('spec') if isinstance(meta, dict) else None
            if spec is not None:
                if not isinstance(spec, dict):
                    _error('CONFLICT', 'OTIO clip metadata spec is malformed')
                spec = deepcopy(spec)
                if (spec.get('kind') != kind or spec.get('channel') != channel or
                        spec.get('start') != start or spec.get('duration') != duration or
                        spec.get('name') != item.name or
                        spec.get('mute', False) != (not (track_enabled and item.enabled))):
                    _error('CONFLICT', 'OTIO clip metadata differs from native cut: ' + str(item.name))
                if spec.get('id') in used:
                    _error('CONFLICT', 'Duplicate OTIO managed clip identity: ' + str(spec.get('id')))
                used.add(spec.get('id'))
                if spec.get('name') in used_names:
                    _error('CONFLICT', 'Duplicate OTIO managed clip name: ' + str(spec.get('name')))
                used_names.add(spec.get('name'))
                source = spec.get('source', {})
                files = source.get('files', [])
                if (len(files) != 1 or source.get('source_in') != source_in or
                        str(Path(files[0].get('file', '')).resolve()) != path):
                    _error('CONFLICT', 'OTIO clip source metadata differs from its media: ' + str(item.name))
                source['files'] = [descriptor]
                spec['source'] = source
            else:
                cid = _clip_id(item.name, used)
                name = item.name or cid
                index = 2
                while name in used_names:
                    name = (item.name or cid)[:60].rstrip('_-') + '_' + str(index)
                    index += 1
                used_names.add(name)
                spec = {'id': cid, 'kind': kind, 'channel': channel, 'start': start,
                        'duration': duration, 'name': name, 'shot_id': cid,
                        'candidate_id': 'original', 'lock': False,
                        'mute': not (track_enabled and item.enabled),
                        'fade_in': 0, 'fade_out': 0,
                        'source': {'files': [descriptor], 'source_in': source_in, 'speed': 1,
                                   'freeze': False, 'stream': 0}}
                if kind == 'MOVIE':
                    spec.update({'fit': 'FIT', 'opacity': 1,
                                 'crop': {'left': 0, 'right': 0, 'top': 0, 'bottom': 0},
                                 'grade': {'multiply': 1, 'saturation': 1}})
                    spec['source']['color_space'] = 'sRGB'
                else:
                    spec.update({'volume': 1, 'pan': 0})
            clips.append(spec)
        max_cursor = max(max_cursor, cursor)
    if not clips:
        _error('INVALID_REQUEST', 'OTIO timeline has no cut clips')
    meta_end = timeline_meta.get('frame_end_exclusive')
    frame_end = max(max_end, frame_start + max_cursor,
                    meta_end if isinstance(meta_end, int) and not isinstance(meta_end, bool) else max_end)
    timeline_spec = {'fps': [fps.numerator, fps.denominator], 'width': width, 'height': height,
                     'frame_start': frame_start, 'frame_end_exclusive': frame_end}
    manifest = {'version': '1.0', 'action': 'create', 'workflow_id': workflow_id,
                'scene': scene, 'timeline': timeline_spec, 'clips': clips}
    for clip in clips:
        validate_clip(clip, timeline_spec)
    return manifest


def cut_projection(clip):
    source = clip['source']
    return {'id': clip['id'], 'kind': clip['kind'], 'channel': clip['channel'],
            'start': clip['start'], 'duration': clip['duration'], 'name': clip['name'],
            'shot_id': clip.get('shot_id', clip['id']), 'lock': clip.get('lock', False),
            'mute': clip.get('mute', False),
            'source': {'file': source['files'][0]['file'],
                       'sha256': source['files'][0]['expected_sha256'],
                       'source_in': source['source_in'], 'speed': source.get('speed', 1),
                       'freeze': source.get('freeze', False), 'stream': source.get('stream', 0),
                       'color_space': source.get('color_space')}}


def diff_specs(expected, actual):
    left = {row['id']: cut_projection(row) for row in expected}
    right = {row['id']: cut_projection(row) for row in actual}
    differences = []
    for key in sorted(set(left) | set(right)):
        if left.get(key) != right.get(key):
            differences.append({'id': key, 'expected': left.get(key), 'actual': right.get(key)})
    return differences


def native_rows(clips):
    return [{'name': row['name'], 'kind': row['kind'], 'channel': row['channel'],
             'start': row['start'], 'duration': row['duration'],
             'source_in': row['source']['source_in'],
             'file': row['source']['files'][0]['file'], 'mute': row.get('mute', False)}
            for row in sorted(clips, key=lambda value: (value['channel'], value['start'], value['id']))]
