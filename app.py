from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for
import os
import uuid
import time
import threading
import psutil
from datetime import datetime
from werkzeug.utils import secure_filename
import requests

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2GB max
app.secret_key = 'supersecretkey'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Data structure to track transfers
transfers = {}
transfer_lock = threading.Lock()

# File type icons mapping
FILE_ICONS = {
    'image': 'far fa-file-image',
    'video': 'far fa-file-video',
    'audio': 'far fa-file-audio',
    'pdf': 'far fa-file-pdf',
    'zip': 'far fa-file-archive',
    'default': 'far fa-file'
}

def get_file_icon(filename):
    ext = filename.split('.')[-1].lower()
    if ext in ['jpg', 'jpeg', 'png', 'gif']:
        return FILE_ICONS['image']
    elif ext in ['mp4', 'mov', 'avi']:
        return FILE_ICONS['video']
    elif ext in ['mp3', 'wav']:
        return FILE_ICONS['audio']
    elif ext == 'pdf':
        return FILE_ICONS['pdf']
    elif ext in ['zip', 'rar', 'tar']:
        return FILE_ICONS['zip']
    return FILE_ICONS['default']

def human_readable_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

def get_system_stats():
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    return {
        'cpu': cpu,
        'mem_total': mem.total,
        'mem_used': mem.used,
        'disk_total': disk.total,
        'disk_used': disk.used,
        'timestamp': datetime.now().timestamp()
    }

def transfer_worker(url, transfer_id, is_upload=False, file_path=None, filename=None):
    start_time = time.time()
    
    with transfer_lock:
        transfers[transfer_id] = {
            'type': 'upload' if is_upload else 'download',
            'progress': 0,
            'speed': 0,
            'size': 0,
            'filename': filename if filename else (url.split('/')[-1] if url else ''),
            'start_time': start_time,
            'status': 'starting'
        }

    try:
        if is_upload and file_path:
            # file is already saved, just update status
            with transfer_lock:
                transfers[transfer_id].update({
                    'status': 'completed',
                    'progress': 100,
                    'size': os.path.getsize(file_path)
                })
        else:
            # Download from URL
            with requests.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                file_size = int(r.headers.get('content-length', 0))
                downloaded = 0
                start_time = time.time()
                
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], transfer_id)
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            elapsed = time.time() - start_time
                            speed = downloaded / elapsed if elapsed > 0 else 0
                            
                            with transfer_lock:
                                transfers[transfer_id].update({
                                    'progress': (downloaded / file_size * 100) if file_size > 0 else 0,
                                    'speed': speed,
                                    'size': file_size,
                                    'status': 'downloading'
                                })

                with transfer_lock:
                    transfers[transfer_id]['status'] = 'completed'
                    transfers[transfer_id]['progress'] = 100

    except Exception as e:
        with transfer_lock:
            transfers[transfer_id]['status'] = f'failed: {str(e)}'
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(url_for('home'))
    
    file = request.files['file']
    if file.filename == '':
        return redirect(url_for('home'))
    
    transfer_id = str(uuid.uuid4())
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], transfer_id)
    file.save(file_path)
    threading.Thread(target=transfer_worker, args=(None, transfer_id, True, file_path, filename)).start()
    return redirect(url_for('transfer_status', transfer_id=transfer_id))

@app.route('/download', methods=['POST'])
def download_file():
    url = request.form.get('url')
    if not url:
        return redirect(url_for('home'))
    
    transfer_id = str(uuid.uuid4())
    threading.Thread(target=transfer_worker, args=(url, transfer_id)).start()
    return redirect(url_for('transfer_status', transfer_id=transfer_id))

@app.route('/status/<transfer_id>')
def transfer_status(transfer_id):
    return render_template('status.html', transfer_id=transfer_id)

@app.route('/api/status/<transfer_id>')
def get_transfer_status(transfer_id):
    with transfer_lock:
        status = transfers.get(transfer_id, {'status': 'not found'})
    
    response = {
        'status': status.get('status'),
        'progress': status.get('progress', 0),
        'speed': human_readable_size(status.get('speed', 0)) + "/s",
        'filename': status.get('filename', ''),
        'size': human_readable_size(status.get('size', 0)),
        'type': status.get('type', 'download'),
        'download_url': url_for('download_completed', transfer_id=transfer_id, _external=True) if status.get('status') == 'completed' else None
    }
    print(f"Download URL for transfer_id {transfer_id}: {response['download_url']}")
    return jsonify(response)

@app.route('/download/<transfer_id>')
def download_completed(transfer_id):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], transfer_id)
    if not os.path.exists(file_path):
        return "File not found", 404
    
    filename = transfers.get(transfer_id, {}).get('filename', 'file')
    return send_from_directory(app.config['UPLOAD_FOLDER'], transfer_id, as_attachment=True, download_name=filename)

@app.route('/server-stats')
def server_stats():
    return render_template('server.html')

@app.route('/api/server-stats')
def server_stats_data():
    stats = get_system_stats()
    return jsonify(stats)

# Cleanup thread
def cleanup_files():
    while True:
        time.sleep(3600)
        now = time.time()
        for fname in os.listdir(app.config['UPLOAD_FOLDER']):
            path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
            if os.path.isfile(path) and (now - os.path.getctime(path)) > 86400:  # 24h
                os.remove(path)
                with transfer_lock:
                    if fname in transfers:
                        del transfers[fname]

threading.Thread(target=cleanup_files, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
