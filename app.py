"""
pdfer — locally-hosted PDF toolkit
"""
import base64
import io
import os
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path

import fitz  # PyMuPDF — used for thumbnail generation

from flask import Flask, jsonify, request, send_file
from werkzeug.utils import secure_filename

from tools import TOOLS
from auth import auth_bp, init_db, close_db

# ── Config ────────────────────────────────────────────────────────────────────
WORK_ROOT   = Path(os.environ.get('PDFER_WORK_DIR', '/tmp/pdfer'))
SESSION_TTL = int(os.environ.get('PDFER_SESSION_TTL', 3600))   # seconds
PORT        = int(os.environ.get('PORT', 7265))

WORK_ROOT.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {
    'pdf', 'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'tif', 'webp',
    'pptx', 'ppt', 'docx', 'doc', 'xlsx', 'xls', 'odp', 'odt', 'ods',
}

# ── App ───────────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder='static', static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 512 * 1024 * 1024  # 512 MB

# ── Auth blueprint + DB ───────────────────────────────────────────────────────
app.register_blueprint(auth_bp)
app.teardown_appcontext(close_db)
init_db()

_sessions: dict = {}
_lock = threading.Lock()


# ── Background cleanup ────────────────────────────────────────────────────────
def _cleanup_loop():
    while True:
        time.sleep(300)
        cutoff = time.time() - SESSION_TTL
        with _lock:
            expired = [sid for sid, s in _sessions.items() if s['created'] < cutoff]
        for sid in expired:
            with _lock:
                sess = _sessions.pop(sid, None)
            if sess:
                shutil.rmtree(sess['work_dir'], ignore_errors=True)


threading.Thread(target=_cleanup_loop, daemon=True).start()


# ── Helpers ───────────────────────────────────────────────────────────────────
def _allowed(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_session(session_id: str):
    with _lock:
        return _sessions.get(session_id)


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return app.send_static_file('index.html')


@app.route('/api/tools')
def get_tools():
    return jsonify([
        {
            'id':          tid,
            'name':        t['name'],
            'description': t['description'],
            'accepts':     t['accepts'],
            'icon':        t.get('icon', ''),
            'interactive': t.get('interactive', False),
            'params':      t.get('params', []),
        }
        for tid, t in TOOLS.items()
    ])


@app.route('/api/upload', methods=['POST'])
def upload():
    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'error': 'No files provided'}), 400

    session_id = str(uuid.uuid4())
    inp_dir    = WORK_ROOT / session_id / 'input'
    inp_dir.mkdir(parents=True)

    uploaded = []
    for f in files:
        if not f.filename or not _allowed(f.filename):
            continue
        safe = secure_filename(f.filename)
        dest = inp_dir / safe
        # Avoid overwriting if names collide
        stem, ext, n = dest.stem, dest.suffix, 1
        while dest.exists():
            dest = inp_dir / f"{stem}_{n}{ext}"
            n += 1
        f.save(dest)
        uploaded.append({
            'name':      f.filename,
            'safe_name': dest.name,
            'size':      dest.stat().st_size,
            'path':      str(dest),
            'ext':       dest.suffix.lstrip('.').lower(),
        })

    if not uploaded:
        shutil.rmtree(WORK_ROOT / session_id, ignore_errors=True)
        return jsonify({'error': 'No valid files (check allowed types)'}), 400

    with _lock:
        _sessions[session_id] = {
            'created':  time.time(),
            'work_dir': WORK_ROOT / session_id,
            'inputs':   uploaded,
            'outputs':  [],
        }

    return jsonify({'session_id': session_id, 'files': uploaded})


@app.route('/api/new-session', methods=['POST'])
def new_session():
    """Create an empty session (no file upload) for tools like Webpage to PDF."""
    session_id = str(uuid.uuid4())
    work_dir   = WORK_ROOT / session_id
    work_dir.mkdir(parents=True)
    with _lock:
        _sessions[session_id] = {
            'created':  time.time(),
            'work_dir': work_dir,
            'inputs':   [],
            'outputs':  [],
        }
    return jsonify({'session_id': session_id, 'files': []})


@app.route('/api/run', methods=['POST'])
def run_workflow():
    data       = request.get_json(force=True)
    session_id = data.get('session_id')
    steps      = data.get('steps', [])

    sess = _get_session(session_id)
    if sess is None:
        return jsonify({'error': 'Session not found or expired'}), 404

    current_files = [Path(f['path']) for f in sess['inputs']]
    step_results  = []

    # ── Auto-convert: prepend convert_to_pdf when non-PDFs meet PDF-only tools ──
    has_non_pdf        = any(f.suffix.lower() != '.pdf' for f in current_files)
    needs_pdf          = any(s.get('tool') in _PDF_ONLY_TOOLS for s in steps)
    starts_with_convert = steps and steps[0].get('tool') == 'convert_to_pdf'
    auto_converted     = False

    if has_non_pdf and needs_pdf and not starts_with_convert:
        steps          = [{'tool': 'convert_to_pdf', 'params': {}}] + steps
        auto_converted = True

    for i, step in enumerate(steps):
        tool_id = step.get('tool')
        params  = step.get('params', {})

        # ── Pause at split — always wait for interactive group selection ──────
        if tool_id == 'split':
            with _lock:
                _sessions[session_id]['paused_files']        = list(current_files)
                _sessions[session_id]['remaining_steps']     = steps[i:]
                _sessions[session_id]['step_results_so_far'] = list(step_results)
                _sessions[session_id]['pause_step_index']    = i
            return jsonify({
                'paused':           True,
                'pause_type':       'split',
                'pause_step_index': i,
                'steps_completed':  len(step_results),
                'steps_remaining':  len(steps) - i,
                'auto_converted':   auto_converted,
            })

        # ── Pause at organize_pages — always wait for interactive arrangement ──
        if tool_id == 'organize_pages':
            with _lock:
                _sessions[session_id]['paused_files']        = list(current_files)
                _sessions[session_id]['remaining_steps']     = steps[i:]
                _sessions[session_id]['step_results_so_far'] = list(step_results)
                _sessions[session_id]['pause_step_index']    = i
            return jsonify({
                'paused':           True,
                'pause_type':       'organize',
                'pause_step_index': i,
                'steps_completed':  len(step_results),
                'steps_remaining':  len(steps) - i,
                'auto_converted':   auto_converted,
            })

        # ── Pause at sign_pdf — always wait for interactive placement ──────
        if tool_id == 'sign_pdf' and not params.get('placement'):
            with _lock:
                _sessions[session_id]['paused_files']        = list(current_files)
                _sessions[session_id]['remaining_steps']     = steps[i:]
                _sessions[session_id]['step_results_so_far'] = list(step_results)
                _sessions[session_id]['pause_step_index']    = i
            return jsonify({
                'paused':           True,
                'pause_type':       'sign',
                'pause_step_index': i,
                'steps_completed':  len(step_results),
                'steps_remaining':  len(steps) - i,
                'auto_converted':   auto_converted,
            })

        # ── Pause at rename when ask=True and names not yet provided ──
        if tool_id == 'rename' and params.get('ask') and not params.get('names'):
            from tools.rename import eval_template_for_preview
            template   = str(params.get('template', '{original}'))
            pdf_files  = [f for f in current_files if f.suffix.lower() == '.pdf']
            previews   = [
                eval_template_for_preview(template, f.stem, idx)
                for idx, f in enumerate(pdf_files)
            ]
            file_names = [f.name for f in pdf_files]
            with _lock:
                _sessions[session_id]['paused_files']        = list(current_files)
                _sessions[session_id]['remaining_steps']     = steps[i:]
                _sessions[session_id]['step_results_so_far'] = list(step_results)
                _sessions[session_id]['pause_step_index']    = i
            return jsonify({
                'paused':           True,
                'pause_type':       'rename',
                'pause_step_index': i,
                'steps_completed':  len(step_results),
                'steps_remaining':  len(steps) - i,
                'auto_converted':   auto_converted,
                'file_names':       file_names,
                'name_previews':    previews,
            })

        if tool_id not in TOOLS:
            return jsonify({'error': f'Unknown tool: "{tool_id}"'}), 400

        step_dir = sess['work_dir'] / f'step_{i:02d}_{tool_id}'
        step_dir.mkdir(exist_ok=True)

        try:
            output_files = TOOLS[tool_id]['func'](current_files, params, step_dir)
        except Exception as exc:
            return jsonify({
                'error':       str(exc),
                'failed_step': i,
                'tool':        TOOLS[tool_id]['name'],
            }), 500

        step_results.append({
            'step':         i,
            'tool':         tool_id,
            'input_count':  len(current_files),
            'output_count': len(output_files),
        })
        current_files = output_files

    outputs = [
        {'index': idx, 'name': f.name, 'size': f.stat().st_size}
        for idx, f in enumerate(current_files)
    ]

    with _lock:
        _sessions[session_id]['outputs'] = current_files

    return jsonify({'success': True, 'steps': step_results, 'outputs': outputs,
                    'auto_converted': auto_converted})


@app.route('/api/resume', methods=['POST'])
def resume_workflow():
    """Resume a paused workflow after the user has arranged pages."""
    data       = request.get_json(force=True)
    session_id = data.get('session_id')
    order      = data.get('order', [])
    names      = data.get('names')   # for rename pause

    sess = _get_session(session_id)
    if sess is None:
        return jsonify({'error': 'Session not found or expired'}), 404

    paused_files    = sess.get('paused_files')
    remaining_steps = sess.get('remaining_steps')

    if not paused_files or not remaining_steps:
        return jsonify({'error': 'No paused workflow found'}), 400

    first_tool = remaining_steps[0].get('tool')

    if first_tool == 'split':
        groups = data.get('groups')
        if groups is not None:
            remaining_steps[0]['params']['groups'] = groups
    elif first_tool == 'organize_pages':
        # Inject the user's page order into the organize step
        remaining_steps[0]['params']['order'] = order
    elif first_tool == 'rename' and names is not None:
        # Inject the user-supplied names into the rename step
        remaining_steps[0]['params']['names'] = names
    elif first_tool == 'sign_pdf':
        signatures = data.get('signatures')
        if signatures is not None:
            remaining_steps[0]['params']['signatures'] = signatures

    step_results = list(sess.get('step_results_so_far', []))
    step_offset  = sess.get('pause_step_index', 0)
    current_files = list(paused_files)

    # Clear pause state
    with _lock:
        _sessions[session_id]['paused_files']        = None
        _sessions[session_id]['remaining_steps']     = None
        _sessions[session_id]['step_results_so_far'] = []

    for i, step in enumerate(remaining_steps):
        tool_id = step.get('tool')
        params  = step.get('params', {})

        if tool_id not in TOOLS:
            return jsonify({'error': f'Unknown tool: "{tool_id}"'}), 400

        step_dir = sess['work_dir'] / f'step_{step_offset + i:02d}_{tool_id}'
        step_dir.mkdir(exist_ok=True)

        try:
            output_files = TOOLS[tool_id]['func'](current_files, params, step_dir)
        except Exception as exc:
            return jsonify({
                'error':       str(exc),
                'failed_step': step_offset + i,
                'tool':        TOOLS[tool_id]['name'],
            }), 500

        step_results.append({
            'step':         step_offset + i,
            'tool':         tool_id,
            'input_count':  len(current_files),
            'output_count': len(output_files),
        })
        current_files = output_files

    outputs = [
        {'index': idx, 'name': f.name, 'size': f.stat().st_size}
        for idx, f in enumerate(current_files)
    ]

    with _lock:
        _sessions[session_id]['outputs'] = current_files

    return jsonify({'success': True, 'steps': step_results, 'outputs': outputs})


@app.route('/api/download/<session_id>/<int:file_index>')
def download_one(session_id, file_index):
    sess = _get_session(session_id)
    if sess is None:
        return jsonify({'error': 'Session not found'}), 404

    outputs = sess.get('outputs', [])
    if file_index >= len(outputs):
        return jsonify({'error': 'File index out of range'}), 404

    f = outputs[file_index]
    return send_file(f, as_attachment=True, download_name=f.name)


@app.route('/api/download-all/<session_id>')
def download_all(session_id):
    sess = _get_session(session_id)
    if sess is None:
        return jsonify({'error': 'Session not found'}), 404

    outputs = sess.get('outputs', [])
    if not outputs:
        return jsonify({'error': 'No output files'}), 404

    if len(outputs) == 1:
        f = outputs[0]
        return send_file(f, as_attachment=True, download_name=f.name)

    buf = io.BytesIO()
    seen: set = set()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in outputs:
            name = f.name
            base, ext, n = f.stem, f.suffix, 1
            while name in seen:
                name = f"{base}_{n}{ext}"
                n   += 1
            seen.add(name)
            zf.write(f, name)
    buf.seek(0)
    return send_file(buf, mimetype='application/zip',
                     as_attachment=True, download_name='pdfer_output.zip')


# Tools that require PDF input — used for auto-convert logic
_PDF_ONLY_TOOLS = {
    'merge', 'split', 'split_pages', 'compress', 'page_numbers', 'rotate',
    'watermark', 'organize_pages', 'rename', 'protect', 'unlock',
    'pdf_to_images', 'pdf_to_format', 'extract_text', 'edit_metadata',
    'grayscale', 'interleave', 'flatten', 'header_footer',
    'extract_images', 'pdf_to_markdown', 'sign_pdf', 'pdf_to_html',
}


@app.route('/api/thumbnails/<session_id>')
def get_thumbnails(session_id):
    """Return base64 PNG thumbnails for every page of every PDF in the session."""
    sess = _get_session(session_id)
    if sess is None:
        return jsonify({'error': 'Session not found'}), 404

    thumbnails = []
    global_idx = 0

    # Use intermediate files if the workflow is paused, otherwise use original inputs
    paused = sess.get('paused_files')
    if paused:
        # paused_files is a list of Path objects
        file_sources = [{'name': p.name, 'path': str(p)} for p in paused]
    else:
        file_sources = [{'name': f['name'], 'path': f['path']} for f in sess['inputs']]

    for file_info in file_sources:
        path = Path(file_info['path'])
        if path.suffix.lower() != '.pdf':
            # Placeholder for non-PDF files
            thumbnails.append({
                'global_index': global_idx,
                'file_name':    file_info['name'],
                'page':         0,
                'total_pages':  1,
                'placeholder':  True,
                'data':         None,
            })
            global_idx += 1
            continue

        try:
            with fitz.open(str(path)) as doc:
                for page_idx in range(len(doc)):
                    page = doc[page_idx]
                    mat  = fitz.Matrix(0.28, 0.28)   # ~A4 → ~167×236 px
                    pix  = page.get_pixmap(matrix=mat, alpha=False)
                    b64  = base64.b64encode(pix.tobytes('png')).decode()
                    thumbnails.append({
                        'global_index': global_idx,
                        'file_name':    file_info['name'],
                        'page':         page_idx,
                        'total_pages':  len(doc),
                        'placeholder':  False,
                        'data':         f'data:image/png;base64,{b64}',
                    })
                    global_idx += 1
        except Exception as exc:
            thumbnails.append({
                'global_index': global_idx,
                'file_name':    file_info['name'],
                'page':         0,
                'total_pages':  1,
                'placeholder':  True,
                'error':        str(exc),
                'data':         None,
            })
            global_idx += 1

    return jsonify({'thumbnails': thumbnails, 'total': len(thumbnails)})


@app.route('/api/page_preview/<session_id>/<int:global_idx>')
def get_page_preview(session_id, global_idx):
    """Return a single page at higher resolution for interactive overlays."""
    scale = min(3.0, max(0.2, float(request.args.get('scale', '1.0'))))
    sess  = _get_session(session_id)
    if sess is None:
        return jsonify({'error': 'Session not found'}), 404

    paused = sess.get('paused_files')
    if paused:
        file_sources = [{'name': p.name, 'path': str(p)} for p in paused]
    else:
        file_sources = [{'name': f['name'], 'path': f['path']} for f in sess['inputs']]

    current = 0
    for file_info in file_sources:
        path = Path(file_info['path'])
        if path.suffix.lower() != '.pdf':
            if current == global_idx:
                return jsonify({'placeholder': True, 'total_pages': 1})
            current += 1
            continue
        try:
            with fitz.open(str(path)) as doc:
                total = len(doc)
                for page_idx in range(total):
                    if current == global_idx:
                        mat = fitz.Matrix(scale, scale)
                        pix = doc[page_idx].get_pixmap(matrix=mat, alpha=False)
                        b64 = base64.b64encode(pix.tobytes('png')).decode()
                        return jsonify({
                            'data':        f'data:image/png;base64,{b64}',
                            'total_pages': total,
                            'page':        page_idx,
                        })
                    current += 1
        except Exception as exc:
            return jsonify({'error': str(exc)}), 500

    return jsonify({'error': 'Page not found'}), 404


@app.route('/api/session/<session_id>/file/<safe_name>', methods=['DELETE'])
def delete_file(session_id, safe_name):
    sess = _get_session(session_id)
    if sess is None:
        return jsonify({'error': 'Session not found or expired'}), 404

    # Find the file in inputs by safe_name
    target = next((f for f in sess['inputs'] if f['safe_name'] == safe_name), None)
    if target is None:
        return jsonify({'error': 'File not found in session'}), 404

    # Delete from disk
    try:
        Path(target['path']).unlink(missing_ok=True)
    except Exception:
        pass

    # Remove from session inputs
    with _lock:
        sess['inputs'] = [f for f in sess['inputs'] if f['safe_name'] != safe_name]

    return jsonify({'success': True, 'files': sess['inputs']})


@app.route('/api/session/<session_id>/add_files', methods=['POST'])
def add_files(session_id):
    sess = _get_session(session_id)
    if sess is None:
        return jsonify({'error': 'Session not found or expired'}), 404

    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'error': 'No files provided'}), 400

    inp_dir = Path(sess['work_dir']) / 'input'
    inp_dir.mkdir(parents=True, exist_ok=True)

    # Gather existing safe names to avoid collisions
    existing_names = {f['safe_name'] for f in sess['inputs']}

    newly_added = []
    for f in files:
        if not f.filename or not _allowed(f.filename):
            continue
        safe = secure_filename(f.filename)
        dest = inp_dir / safe
        # Avoid overwriting existing files (both on disk and in session)
        stem, ext, n = dest.stem, dest.suffix, 1
        while dest.exists() or dest.name in existing_names:
            dest = inp_dir / f"{stem}_{n}{ext}"
            n += 1
        f.save(dest)
        entry = {
            'name':      f.filename,
            'safe_name': dest.name,
            'size':      dest.stat().st_size,
            'path':      str(dest),
            'ext':       dest.suffix.lstrip('.').lower(),
        }
        newly_added.append(entry)
        existing_names.add(dest.name)

    if not newly_added:
        return jsonify({'error': 'No valid files (check allowed types)'}), 400

    with _lock:
        sess['inputs'].extend(newly_added)

    return jsonify({'files': newly_added})


@app.route('/api/session/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    with _lock:
        sess = _sessions.pop(session_id, None)
    if sess:
        shutil.rmtree(sess['work_dir'], ignore_errors=True)
    return jsonify({'success': True})


# ── Entry ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print(f'\n  ┌──────────────────────────────┐')
    print(f'  │  pdfer  →  http://localhost:{PORT}  │')
    print(f'  │  All processing is local     │')
    print(f'  └──────────────────────────────┘\n')
    app.run(host='0.0.0.0', port=PORT, debug=False)
