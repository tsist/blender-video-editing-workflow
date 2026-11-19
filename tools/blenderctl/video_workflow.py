"""Saved-file native VSE work unit, guarded candidate and fresh-reader evidence."""
import copy
import json
import subprocess
import time
from contextlib import ExitStack
from pathlib import Path

import bpy
from protocol import Failure, atomic_json, digest, read_json
from video_identity import implementation_sha256
from video_workflow_contract import (_call, input_documents, normalize_params,
                                     normalize_inspect_params, normalize_ripple_params,
                                     normalize_otio_export_params, normalize_otio_import_params,
                                     signature)
from video_verifier import mismatch, runtime_identity
from video_editing_workflow_addon import core, contract


def _json(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _descriptor(path):
    return {'file': str(path), 'sha256': digest(path)}


def _check_inputs(params):
    for row in input_documents(params):
        if digest(row['file']) != row['expected_sha256']:
            raise Failure('CONFLICT', 'Video source/resource/implementation SHA mismatch: ' + row['file'])
    if implementation_sha256() != params['implementation_sha256']:
        raise Failure('CONFLICT', 'Video implementation differs')


def _resource_closure(params):
    declared = {row['file'].casefold(): row for row in input_documents(params)}
    paths = []
    for value in _call(core.resource_paths):
        raw = value if isinstance(value, str) else value.get('file', value.get('path')) if isinstance(value, dict) else None
        if not isinstance(raw, str) or not Path(raw).is_absolute():
            raise Failure('UNSUPPORTED', 'Core returned unresolved external resource')
        path = str(Path(raw).resolve())
        row = declared.get(path.casefold())
        if row is None:
            raise Failure('CONFLICT', 'Actual external resource was not declared: ' + path)
        if digest(path) != row['expected_sha256']:
            raise Failure('CONFLICT', 'Actual external resource differs: ' + path)
        paths.append(path)
    return sorted(set(paths), key=str.casefold)


def _saved_expectation(params):
    manifest = params.get('manifest', {})
    scene = manifest.get('scene', params.get('scene'))
    workflow_id = manifest.get('workflow_id', params.get('workflow_id'))
    return {'inspection': _json(_call(core.inspect, scene, workflow_id)),
            'protection': _json(_call(core.snapshot_protection, scene)),
            'resource_paths': _resource_closure(params)}


def _reopen(candidate, params, report, job, progress, scene=None, workflow_id=None):
    request = job / 'video-verification-request.json'
    output = job / 'video-reopen.json'
    if request.exists() or output.exists():
        raise Failure('CONFLICT', 'Owned video verification phase already exists')
    manifest = params.get('manifest', {})
    scene = scene or manifest.get('scene', params.get('scene'))
    workflow_id = workflow_id or manifest.get('workflow_id', params.get('workflow_id'))
    config = {'candidate': candidate, 'implementation_sha256': params['implementation_sha256'],
              'runtime': report['runtime'], 'scene': scene, 'workflow_id': workflow_id,
              'saved_expectation': report['saved_expectation'],
              'resources': input_documents(params), 'output': str(output)}
    atomic_json(request, config)
    command = [bpy.app.binary_path, '--background', '--factory-startup', '--disable-autoexec',
               '--offline-mode', '--python-exit-code', '23', '--python',
               str(Path(__file__).with_name('video_verifier.py')), '--', str(request)]
    deadline = time.monotonic() + 120
    with (job / 'video-reopen.stdout.log').open('wb') as stdout, (job / 'video-reopen.stderr.log').open('wb') as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        try:
            while process.poll() is None:
                progress('independent_reopen', candidate=candidate)
                if time.monotonic() > deadline:
                    raise Failure('TIMEOUT', 'Independent VSE reader exceeded 120 seconds')
                time.sleep(.2)
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)
            raise
    # Blender may exit successfully after exhausting its global font slots,
    # leaving valid TEXT strips that render without glyphs. Reject that reader.
    for name in ('video-reopen.stdout.log', 'video-reopen.stderr.log'):
        if 'Too many fonts!!!' in (job / name).read_text(encoding='utf-8', errors='replace'):
            raise Failure('VALIDATION_FAILED', 'Independent VSE reader exhausted font capacity; see ' + name)
    result = read_json(output) if output.is_file() else {}
    if process.returncode != 0 or result.get('status') != 'passed':
        raise Failure('VALIDATION_FAILED', 'Independent VSE reader failed: ' + str(result.get('error', process.returncode)))
    return result


def _shots(inspection):
    clips = inspection.get('clips', [])
    if isinstance(clips, dict):
        clips = list(clips.values())
    if not isinstance(clips, list):
        raise Failure('VALIDATION_FAILED', 'Core inspection clips must be a list or mapping')
    rows = []
    for clip in clips:
        if not isinstance(clip, dict):
            continue
        rows.append({key: copy.deepcopy(clip[key]) for key in ('id', 'shot_id', 'candidate_id', 'kind', 'name', 'channel', 'start', 'duration', 'source', 'alternatives', 'lock', 'mute') if key in clip})
    return {'shot_table_version': '1.0', 'scene': inspection.get('scene'), 'workflow_id': inspection.get('workflow_id'),
            'timeline': inspection.get('timeline'), 'clips': rows,
            'scope': 'Current technical timeline; editorial or aesthetic approval is separate'}


def _output_files(value):
    result = []
    if isinstance(value, dict):
        if isinstance(value.get('file'), str) and isinstance(value.get('sha256'), str):
            result.append({'file': value['file'], 'sha256': value['sha256']})
        for child in value.values():
            result.extend(_output_files(child))
    elif isinstance(value, list):
        for child in value:
            result.extend(_output_files(child))
    return result


def run(params, job, *, cancel_parent=None):
    params = normalize_params(params)
    job = Path(job)
    started = time.monotonic()
    report = {'video_report_version': '1.0', 'addon_version': '0.1.2', 'status': 'running',
              'source': {'file': params['file'], 'sha256': params['expected_sha256']},
              'runtime': runtime_identity(bpy), 'implementation_sha256': params['implementation_sha256'],
              'signature': signature(params), 'recovery': {'available': False}, 'output_files': [],
              'checks': {'visual_quality': 'not_run', 'audio_listening': 'not_run', 'HDR_device_viewing': 'not_run'},
              'support': {'stage': 'technical_A_development', 'HDR10_PQ': 'not_requested_in_this_job',
                          'real_AI_film': 'not_run', 'five_minute_real_film': 'not_run'}}
    last_progress = [None, 0.0]

    def progress(stage, **extra):
        if (job / 'cancel.request').exists() or (cancel_parent and (Path(cancel_parent) / 'cancel.request').exists()):
            raise Failure('CANCELLED', 'Video cancelled at ' + stage)
        now = time.monotonic()
        stage_changed = stage != last_progress[0]
        # Recovery state changes at phase boundaries, not on every rendered frame.
        # Keep the large durable checkpoint separate from the bounded heartbeat.
        if stage_changed:
            atomic_json(job / 'video-report.json', report)
        if stage_changed or now - last_progress[1] >= .5:
            atomic_json(job / 'video-progress.json', {'stage': stage, 'status': 'running', 'seconds': now - started, **extra})
            last_progress[:] = [stage, now]

    try:
        progress('source_open')
        _check_inputs(params)
        bpy.ops.wm.open_mainfile(filepath=params['file'], load_ui=False, use_scripts=False)
        if tuple(bpy.data.version[:2]) != tuple(bpy.app.version[:2]):
            raise Failure('UNSUPPORTED', 'Video requires matching Blender major/minor')
        report['source_resource_paths'] = _resource_closure(params)
        manifest = params['manifest']
        if params.get('resume'):
            old = read_json(params['resume']['file'])
            if old.get('signature') != report['signature'] or old.get('runtime') != report['runtime'] or old.get('implementation_sha256') != params['implementation_sha256']:
                raise Failure('CONFLICT', 'Resume request/resources/runtime/implementation differ')
            if not old.get('saved_expectation') or old.get('verification', {}).get('status') != 'passed' or not old.get('recovery', {}).get('available'):
                raise Failure('CONFLICT', 'Resume requires an independently verified checkpoint')
            previous = old['candidate']
            if digest(previous['file']) != previous['sha256']:
                raise Failure('CONFLICT', 'Resume checkpoint changed')
            bpy.ops.wm.open_mainfile(filepath=previous['file'], load_ui=False, use_scripts=False)
            report['saved_expectation'] = copy.deepcopy(old['saved_expectation'])
            difference = mismatch(report['saved_expectation'], _saved_expectation(params))
            if difference:
                raise Failure('CONFLICT', 'Resume saved expectation differs: ' + difference)
            for key in ('operation', 'protection', 'media_timing'):
                report[key] = copy.deepcopy(old.get(key))
            report['resumed_from'] = params['resume']
            # Reuse immutable old bytes, not resave or overwrite a user-edited checkpoint.
            candidate = previous
        else:
            progress('apply')
            operation = _call(core.apply, manifest)
            if not isinstance(operation, dict) or operation.get('protection', {}).get('status') != 'passed':
                raise Failure('VALIDATION_FAILED', 'Core must prove scoped non-target protection')
            report['operation'] = operation
            report['protection'] = operation['protection']
            from video_media import verify_movie_timing
            report['media_timing'] = verify_movie_timing(params, job, progress)
            # Capture expectations before save. Reopen must never redefine expected state.
            report['saved_expectation'] = _saved_expectation(params)
            if 'output' in params:
                inspected = report['saved_expectation']['inspection']
                _call(contract.validate_output_budget, params['output'], inspected['timeline'], inspected.get('clips', []))
            progress('save_checkpoint')
            destination = job / 'video-candidate.blend'
            if destination.exists():
                raise Failure('CONFLICT', 'Owned candidate already exists')
            bpy.ops.wm.save_as_mainfile(filepath=str(destination), check_existing=False, relative_remap=True)
            candidate = _descriptor(destination)
        report['candidate'] = candidate
        report['inspection'] = copy.deepcopy(report['saved_expectation']['inspection'])
        atomic_json(job / 'video-manifest.json', manifest)
        atomic_json(job / 'video-shots.json', _shots(report['inspection']))
        from filesystem import FileGuard
        with ExitStack() as guards:
            candidate_guard = guards.enter_context(FileGuard(candidate['file']))
            if candidate_guard.sha256() != candidate['sha256']:
                raise Failure('CONFLICT', 'Candidate changed before independent verification')
            progress('independent_reopen')
            report['verification'] = _reopen(candidate, params, report, job, progress)
            report['recovery'] = {'available': True, 'checkpoint': candidate, 'resume_report': str(job / 'video-report.json'),
                                  'binding': 'Original request, source/resources/implementation/runtime SHA and original saved expectation; new job only'}
            if 'output' in params:
                inspected = report['inspection']
                _call(contract.validate_output_budget, params['output'], inspected['timeline'], inspected.get('clips', []))
                progress('output')
                if params['output'].get('color_mode') == 'HDR10_PQ':
                    from video_hdr import render_hdr_outputs
                    report['outputs'] = render_hdr_outputs(params, job, report, progress)
                    report['support']['HDR10_PQ'] = 'technical_STANDARD_100; virtual mastering; device viewing not_run'
                elif params['output'].get('preview'):
                    from video_proxy import render_proxy_outputs
                    report['outputs'] = render_proxy_outputs(params, job, report, progress)
                    report['support']['preview'] = 'derived proxy pixels; original candidate unchanged; not final image quality'
                else:
                    from video_outputs import render_outputs
                    report['outputs'] = render_outputs(params, job, report, progress)
                if not isinstance(report['outputs'], dict) or report['outputs'].get('status') != 'passed':
                    raise Failure('VALIDATION_FAILED', 'Output module did not return passed evidence')
                files = {row['file']: row for row in _output_files(report['outputs'])}
                for row in files.values():
                    path = Path(row['file']).resolve()
                    if not path.is_relative_to(job.resolve()) or digest(path) != row['sha256']:
                        raise Failure('VALIDATION_FAILED', 'Output descriptor is outside owned job or differs')
                report['output_files'] = list(files.values())
            difference = mismatch(report['saved_expectation'], _saved_expectation(params))
            if difference:
                raise Failure('VALIDATION_FAILED', 'Candidate state changed during output: ' + difference)
            if candidate_guard.sha256() != candidate['sha256']:
                raise Failure('CONFLICT', 'Candidate bytes changed during output')
            _check_inputs(params)
        report['checks'].update(source_resources_implementation_sha='passed', candidate_bytes_unchanged='passed', independent_reopen='passed')
        report['status'] = 'passed'
        report['metrics'] = {'wall_seconds': time.monotonic() - started, 'clip_count': len(report['inspection'].get('clips', []))}
        atomic_json(job / 'video-report.json', report)
        atomic_json(job / 'video-progress.json', {'stage': 'complete', 'status': 'passed', 'seconds': report['metrics']['wall_seconds']})
        return report
    except Exception as exc:
        code = getattr(exc, 'code', 'WORKER_FAILED')
        report.update(status='cancelled' if code == 'CANCELLED' else 'failed', error={'code': code, 'message': str(exc)})
        atomic_json(job / 'video-report.json', report)
        atomic_json(job / 'video-progress.json', {'stage': last_progress[0], 'status': report['status'], 'error': report['error'], 'recovery': report['recovery']})
        if isinstance(exc, contract.WorkflowError):
            raise Failure(exc.code, str(exc)) from exc
        raise


def _progress(job, report, started, cancel_parent=None):
    last = [None, 0.0]

    def progress(stage, **extra):
        if (job / 'cancel.request').exists() or (cancel_parent and (Path(cancel_parent) / 'cancel.request').exists()):
            raise Failure('CANCELLED', 'Video cancelled at ' + stage)
        now = time.monotonic()
        report['stage'] = stage
        if stage != last[0]:
            atomic_json(job / 'video-report.json', report)
        if stage != last[0] or now - last[1] >= .5:
            atomic_json(job / 'video-progress.json',
                        {'stage': stage, 'status': 'running', 'seconds': now - started, **extra})
            last[:] = [stage, now]

    return progress


def _failure(report, job, exc):
    code = getattr(exc, 'code', 'WORKER_FAILED')
    report.update(status='cancelled' if code == 'CANCELLED' else 'failed',
                  error={'code': code, 'message': str(exc)})
    atomic_json(job / 'video-report.json', report)
    atomic_json(job / 'video-progress.json',
                {'stage': report.get('stage', 'worker'), 'status': report['status'],
                 'error': report['error'], 'recovery': report.get('recovery', {})})
    if isinstance(exc, contract.WorkflowError):
        raise Failure(exc.code, str(exc)) from exc
    raise


def _save_candidate(job, progress):
    destination = job / 'video-candidate.blend'
    if destination.exists():
        raise Failure('CONFLICT', 'Owned candidate already exists')
    progress('save_checkpoint')
    bpy.ops.wm.save_as_mainfile(filepath=str(destination), check_existing=False, relative_remap=True)
    return _descriptor(destination)


def _finish_candidate(params, job, report, candidate, scene, workflow_id, progress, started):
    report['candidate'] = candidate
    report['inspection'] = copy.deepcopy(report['saved_expectation']['inspection'])
    atomic_json(job / 'video-shots.json', _shots(report['inspection']))
    from filesystem import FileGuard
    with FileGuard(candidate['file']) as guard:
        if guard.sha256() != candidate['sha256']:
            raise Failure('CONFLICT', 'Candidate changed before independent verification')
        progress('independent_reopen')
        report['verification'] = _reopen(candidate, params, report, job, progress, scene, workflow_id)
        report['recovery'] = {'available': True, 'checkpoint': candidate,
                              'resume_report': str(job / 'video-report.json'),
                              'binding': 'Original request, source/resources/implementation/runtime SHA and original saved expectation; new job only'}
        difference = mismatch(report['saved_expectation'], _saved_expectation(params))
        if difference:
            raise Failure('VALIDATION_FAILED', 'Candidate state changed during verification: ' + difference)
        if guard.sha256() != candidate['sha256']:
            raise Failure('CONFLICT', 'Candidate bytes changed during verification')
    _check_inputs(params)
    report['checks'].update(source_resources_implementation_sha='passed',
                            candidate_bytes_unchanged='passed', independent_reopen='passed')
    report['status'] = 'passed'
    report['metrics'] = {'wall_seconds': time.monotonic() - started,
                         'clip_count': len(report['inspection'].get('clips', []))}
    atomic_json(job / 'video-report.json', report)
    atomic_json(job / 'video-progress.json',
                {'stage': 'complete', 'status': 'passed', 'seconds': report['metrics']['wall_seconds']})
    return report


def ripple(params, job):
    params = normalize_ripple_params(params)
    job = Path(job)
    started = time.monotonic()
    report = {'video_report_version': '1.0', 'addon_version': '0.1.2', 'status': 'running',
              'source': {'file': params['file'], 'sha256': params['expected_sha256']},
              'runtime': runtime_identity(bpy), 'implementation_sha256': params['implementation_sha256'],
              'signature': signature(params), 'recovery': {'available': False}, 'output_files': [],
              'checks': {'source_resources_implementation_sha': 'not_run',
                         'independent_reopen': 'not_run', 'render': 'not_run',
                         'visual_quality': 'not_run', 'audio_listening': 'not_run'},
              'support': {'stage': 'technical_A_development',
                          'scope': 'short SDR managed ripple; no render/output',
                          'HDR10_PQ': 'not_requested_in_this_job', 'real_AI_film': 'not_run'}}
    progress = _progress(job, report, started)
    try:
        progress('source_open')
        _check_inputs(params)
        bpy.ops.wm.open_mainfile(filepath=params['file'], load_ui=False, use_scripts=False)
        if tuple(bpy.data.version[:2]) != tuple(bpy.app.version[:2]):
            raise Failure('UNSUPPORTED', 'Video requires matching Blender major/minor')
        report['source_resource_paths'] = _resource_closure(params)
        progress('apply')
        operation = _call(core.ripple, params['scene'], params['workflow_id'],
                          params['clip_id'], params['duration'], params.get('edge', 'END'))
        if not isinstance(operation, dict) or operation.get('protection', {}).get('status') != 'passed':
            raise Failure('VALIDATION_FAILED', 'Core must prove scoped non-target protection')
        report['operation'] = operation
        report['protection'] = operation['protection']
        report['ripple'] = operation['ripple']
        report['saved_expectation'] = _saved_expectation(params)
        atomic_json(job / 'video-ripple.json', {'ripple': operation['ripple'],
                                                'operation_log': operation['operation_log']})
        candidate = _save_candidate(job, progress)
        return _finish_candidate(params, job, report, candidate, params['scene'],
                                 params['workflow_id'], progress, started)
    except Exception as exc:
        _failure(report, job, exc)


def _native_otio_check(otio_descriptor, specs, job, progress):
    from otio_exchange import native_rows
    request = job / 'video-otio-verification-request.json'
    output = job / 'video-otio-verification.json'
    if request.exists() or output.exists():
        raise Failure('CONFLICT', 'Owned OTIO verification phase already exists')
    config = {'otio': otio_descriptor, 'expected': native_rows(specs['clips']),
              'timeline': specs['timeline'], 'output': str(output)}
    atomic_json(request, config)
    command = [bpy.app.binary_path, '--background', '--factory-startup', '--disable-autoexec',
               '--offline-mode', '--python-exit-code', '23', '--python',
               str(Path(__file__).with_name('otio_verifier.py')), '--', str(request)]
    deadline = time.monotonic() + 120
    with (job / 'video-otio-verification.stdout.log').open('wb') as stdout, \
            (job / 'video-otio-verification.stderr.log').open('wb') as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        try:
            while process.poll() is None:
                progress('otio_native_import')
                if time.monotonic() > deadline:
                    raise Failure('TIMEOUT', 'Native OTIO verifier exceeded 120 seconds')
                time.sleep(.2)
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            raise
    result = read_json(output) if output.is_file() else {}
    if process.returncode != 0 or result.get('status') != 'passed':
        raise Failure('VALIDATION_FAILED', 'Native OTIO verification failed: ' +
                      str(result.get('error', process.returncode)))
    return result


def otio_export(params, job):
    params = normalize_otio_export_params(params)
    job = Path(job)
    started = time.monotonic()
    report = {'video_report_version': '1.0', 'addon_version': '0.1.2', 'status': 'running',
              'source': {'file': params['file'], 'sha256': params['expected_sha256']},
              'runtime': runtime_identity(bpy), 'implementation_sha256': params['implementation_sha256'],
              'signature': signature(params), 'recovery': {'available': False}, 'output_files': [],
              'checks': {'source_resources_implementation_sha': 'not_run',
                         'otio_readback': 'not_run', 'native_import': 'not_run',
                         'visual_quality': 'not_run', 'audio_listening': 'not_run'},
              'support': {'stage': 'technical_A_development',
                          'scope': 'short SDR cut-only OTIO export; no render',
                          'HDR10_PQ': 'not_requested_in_this_job', 'real_AI_film': 'not_run'}}
    progress = _progress(job, report, started)
    try:
        progress('source_open')
        _check_inputs(params)
        bpy.ops.wm.open_mainfile(filepath=params['file'], load_ui=False, use_scripts=False)
        if tuple(bpy.data.version[:2]) != tuple(bpy.app.version[:2]):
            raise Failure('UNSUPPORTED', 'Video requires matching Blender major/minor')
        report['source_resource_paths'] = _resource_closure(params)
        progress('otio_export')
        specs = _call(core.export_cut_specs, params['scene'], params['workflow_id'])
        import otio_exchange
        timeline = otio_exchange.timeline_from_specs(specs)
        destination = job / 'video-otio.otio'
        if destination.exists():
            raise Failure('CONFLICT', 'Owned OTIO output already exists')
        otio_exchange.write_timeline(timeline, destination)
        descriptor = _descriptor(destination)
        resources = {row['file'].casefold(): row for row in params['resources']}
        progress('otio_readback')
        readback = otio_exchange.read_timeline(destination)
        manifest = otio_exchange.specs_from_timeline(
            readback, params['scene'] + '_otio_readback', params['workflow_id'], resources)
        differences = otio_exchange.diff_specs(specs['clips'], manifest['clips'])
        if differences:
            raise Failure('VALIDATION_FAILED', 'OTIO readback differs: ' +
                          json.dumps(differences[:4], ensure_ascii=False))
        report['otio'] = {'status': 'pending', 'file': descriptor,
                          'cut_count': len(specs['clips']),
                          'tracks': specs['channels'],
                          'timeline': specs['timeline'], 'scope': specs['scope']}
        report['verification'] = {'status': 'pending', 'readback': 'passed',
                                  'native_import': 'pending'}
        report['verification']['native_import'] = _native_otio_check(descriptor, specs, job, progress)
        report['otio']['status'] = 'passed'
        report['verification']['status'] = 'passed'
        _resource_closure(params)
        _check_inputs(params)
        report['outputs'] = {'status': 'passed', 'format': 'OTIO', 'otio': descriptor,
                             'cut_count': len(specs['clips']),
                             'verification': report['verification']}
        report['output_files'] = [descriptor]
        report['inspection'] = _json(_call(core.inspect, params['scene'], params['workflow_id']))
        report['checks'].update(source_resources_implementation_sha='passed',
                                otio_readback='passed', native_import='passed',
                                source_unchanged='passed')
        report['status'] = 'passed'
        report['metrics'] = {'wall_seconds': time.monotonic() - started,
                             'clip_count': len(specs['clips'])}
        atomic_json(job / 'video-report.json', report)
        atomic_json(job / 'video-progress.json',
                    {'stage': 'complete', 'status': 'passed',
                     'seconds': report['metrics']['wall_seconds']})
        return report
    except Exception as exc:
        _failure(report, job, exc)


def otio_import(params, job):
    params = normalize_otio_import_params(params)
    job = Path(job)
    started = time.monotonic()
    report = {'video_report_version': '1.0', 'addon_version': '0.1.2', 'status': 'running',
              'source': {'file': params['file'], 'sha256': params['expected_sha256']},
              'otio': params['otio'],
              'runtime': runtime_identity(bpy), 'implementation_sha256': params['implementation_sha256'],
              'signature': signature(params), 'recovery': {'available': False}, 'output_files': [],
              'checks': {'source_resources_implementation_sha': 'not_run',
                         'otio_structure': 'not_run', 'independent_reopen': 'not_run',
                         'visual_quality': 'not_run', 'audio_listening': 'not_run'},
              'support': {'stage': 'technical_A_development',
                          'scope': 'short SDR cut-only OTIO import; no render',
                          'HDR10_PQ': 'not_requested_in_this_job', 'real_AI_film': 'not_run'}}
    progress = _progress(job, report, started)
    try:
        progress('source_open')
        _check_inputs(params)
        bpy.ops.wm.open_mainfile(filepath=params['file'], load_ui=False, use_scripts=False)
        if tuple(bpy.data.version[:2]) != tuple(bpy.app.version[:2]):
            raise Failure('UNSUPPORTED', 'Video requires matching Blender major/minor')
        if bpy.data.scenes.get(params['scene']) is not None:
            raise Failure('CONFLICT', 'Import target scene already exists')
        report['source_resource_paths'] = _resource_closure(params)
        progress('otio_import')
        import otio_exchange
        timeline = otio_exchange.read_timeline(params['otio']['file'])
        resources = {row['file'].casefold(): row for row in params['resources']}
        manifest = otio_exchange.specs_from_timeline(
            timeline, params['scene'], params['workflow_id'], resources)
        _call(core._scope, manifest['timeline'], 'Cut-only OTIO import')
        operation = _call(core.apply, manifest)
        if not isinstance(operation, dict) or operation.get('protection', {}).get('status') != 'passed':
            raise Failure('VALIDATION_FAILED', 'Core must prove scoped non-target protection')
        report['operation'] = operation
        report['protection'] = operation['protection']
        report['otio'] = {**params['otio'],
                          'manifest': {'timeline': manifest['timeline'],
                                       'clip_count': len(manifest['clips'])}}
        report['saved_expectation'] = _saved_expectation(params)
        report['checks']['otio_structure'] = 'passed'
        candidate = _save_candidate(job, progress)
        return _finish_candidate(params, job, report, candidate, params['scene'],
                                 params['workflow_id'], progress, started)
    except Exception as exc:
        _failure(report, job, exc)


def inspect(params, job):
    params = normalize_inspect_params(params)
    _check_inputs(params)
    bpy.ops.wm.open_mainfile(filepath=params['file'], load_ui=False, use_scripts=False)
    paths = _resource_closure(params)
    inspection = _json(_call(core.inspect, params['scene'], params.get('workflow_id')))
    report = {'video_report_version': '1.0', 'addon_version': '0.1.2', 'status': 'passed',
              'source': {'file': params['file'], 'sha256': params['expected_sha256']},
              'implementation_sha256': params['implementation_sha256'], 'runtime': runtime_identity(bpy),
              'inspection': inspection, 'resource_paths': paths, 'source_saved': False,
              'checks': {'source_resources_implementation_sha': 'passed', 'render': 'not_run', 'visual_quality': 'not_run', 'audio_listening': 'not_run'}}
    _check_inputs(params)
    atomic_json(Path(job) / 'video-report.json', report)
    return report

