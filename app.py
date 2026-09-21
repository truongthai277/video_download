import os
import sys
import uuid
import time
import queue
import subprocess
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, abort
import yt_dlp

app = Flask(__name__)

# Thư mục lưu video tải về
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Quản lý hàng đợi và tác vụ
download_tasks = {}
tasks_lock = threading.Lock()
task_queue = queue.Queue()


def format_bytes(size):
    """Chuyển đổi số bytes sang định dạng KB, MB, GB dễ đọc"""
    if not size or size <= 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def format_seconds(seconds):
    """Chuyển đổi số giây sang mm:ss hoặc hh:mm:ss"""
    if not seconds or seconds < 0:
        return "--:--"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def extract_urls(text):
    """Trích xuất danh sách URL hợp lệ từ chuỗi nhiều dòng"""
    if not text:
        return []
    lines = text.strip().splitlines()
    urls = []
    seen = set()
    for line in lines:
        u = line.strip()
        if (u.startswith('http://') or u.startswith('https://')) and u not in seen:
            urls.append(u)
            seen.add(u)
    return urls


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/info', methods=['POST'])
def get_info():
    """Lấy thông tin video (thumbnail, title, duration) trước khi tải"""
    data = request.get_json() or {}
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'error': 'Vui lòng cung cấp đường link (URL) hợp lệ'}), 400

    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return jsonify({'error': 'Không tìm thấy thông tin video'}), 404

            title = info.get('title', 'Video không tên')
            thumbnail = info.get('thumbnail') or (info.get('thumbnails', [{}])[-1].get('url') if info.get('thumbnails') else None)
            duration = info.get('duration')
            duration_str = format_seconds(duration) if duration else 'Trực tiếp / Không rõ'
            uploader = info.get('uploader') or info.get('channel') or info.get('creator') or 'Không rõ tác giả'
            extractor = info.get('extractor_key') or info.get('extractor') or 'Web'
            view_count = info.get('view_count')
            formatted_views = f"{view_count:,}" if view_count else None

            return jsonify({
                'title': title,
                'thumbnail': thumbnail,
                'duration': duration_str,
                'uploader': uploader,
                'extractor': extractor,
                'views': formatted_views,
                'url': url
            })
    except Exception as e:
        return jsonify({'error': f'Lỗi khi phân tích video: {str(e)}'}), 400


def run_download_task(task_id):
    """Thực thi tải 1 video cụ thể (chạy trong Queue Worker)"""
    with tasks_lock:
        task = download_tasks.get(task_id)
        if not task or task.get('status') == 'cancelled':
            return
        task['status'] = 'downloading'
        task['start_time'] = time.time()
        url = task['url']
        format_type = task['format_type']

    def progress_hook(d):
        with tasks_lock:
            t = download_tasks.get(task_id)
            if not t or t.get('status') == 'cancelled':
                return

            if d.get('status') == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes', 0)
                speed = d.get('speed')
                eta = d.get('eta')

                percent = (downloaded / total * 100) if total > 0 else 0
                t['progress'] = round(percent, 1)
                t['speed'] = f"{format_bytes(speed)}/s" if speed else ""
                t['eta'] = format_seconds(eta) if eta else ""
                t['downloaded'] = format_bytes(downloaded)
                t['total'] = format_bytes(total) if total > 0 else "Đang tính..."

            elif d.get('status') == 'finished':
                t['status'] = 'processing'
                t['progress'] = 99.0
                t['eta'] = "Đang xử lý ghép file..."

    # Cấu hình lưu trữ
    outtmpl = os.path.join(DOWNLOAD_DIR, '%(title).150s [%(id)s].%(ext)s')

    ydl_opts = {
        'outtmpl': outtmpl,
        'progress_hooks': [progress_hook],
        'quiet': True,
        'no_warnings': True,
        'windowsfilenames': True,
    }

    if format_type == 'audio_mp3':
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    elif format_type == 'video_1080':
        ydl_opts.update({
            'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
            'merge_output_format': 'mp4',
        })
    elif format_type == 'video_720':
        ydl_opts.update({
            'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best',
            'merge_output_format': 'mp4',
        })
    else:  # video_best
        ydl_opts.update({
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Lấy thông tin & tải
            info = ydl.extract_info(url, download=True)

            final_filename = None
            if 'requested_downloads' in info and info['requested_downloads']:
                filepath = info['requested_downloads'][0].get('filepath')
                if filepath and os.path.exists(filepath):
                    final_filename = os.path.basename(filepath)

            if not final_filename:
                expected_filepath = ydl.prepare_filename(info)
                if format_type == 'audio_mp3':
                    base, _ = os.path.splitext(expected_filepath)
                    expected_filepath = base + '.mp3'

                if os.path.exists(expected_filepath):
                    final_filename = os.path.basename(expected_filepath)
                else:
                    base, _ = os.path.splitext(expected_filepath)
                    for ext in ['.mp4', '.mkv', '.webm', '.mp3']:
                        if os.path.exists(base + ext):
                            final_filename = os.path.basename(base + ext)
                            break

            with tasks_lock:
                t = download_tasks.get(task_id)
                if t and t.get('status') != 'cancelled':
                    t['status'] = 'finished'
                    t['progress'] = 100.0
                    t['filename'] = final_filename
                    t['title'] = info.get('title', 'Video đã tải')
    except Exception as e:
        with tasks_lock:
            t = download_tasks.get(task_id)
            if t and t.get('status') != 'cancelled':
                t['status'] = 'error'
                t['error'] = str(e)


def queue_worker():
    """Background worker xử lý hàng đợi tải tuần tự từng video một"""
    while True:
        try:
            task_id = task_queue.get()
            with tasks_lock:
                task = download_tasks.get(task_id)

            if task and task.get('status') == 'queued':
                run_download_task(task_id)
        except Exception as e:
            print(f"[Queue Worker Error]: {e}")
        finally:
            task_queue.task_done()


# Khởi động Queue Worker duy nhất
worker_thread = threading.Thread(target=queue_worker, daemon=True)
worker_thread.start()


@app.route('/api/queue/add', methods=['POST'])
def add_to_queue():
    """Thêm một hoặc nhiều URL vào hàng đợi tải"""
    data = request.get_json() or {}
    raw_urls = data.get('urls')
    format_type = data.get('format_type', 'video_best')

    urls = []
    if isinstance(raw_urls, list):
        for u in raw_urls:
            urls.extend(extract_urls(str(u)))
    elif isinstance(raw_urls, str):
        urls = extract_urls(raw_urls)

    if not urls:
        return jsonify({'error': 'Không tìm thấy đường dẫn (URL) video hợp lệ nào'}), 400

    added_tasks = []
    with tasks_lock:
        for u in urls:
            task_id = uuid.uuid4().hex
            task_info = {
                'id': task_id,
                'url': u,
                'format_type': format_type,
                'status': 'queued',
                'progress': 0,
                'speed': '',
                'eta': '',
                'downloaded': '0 B',
                'total': '0 B',
                'filename': None,
                'title': u,  # Tạm thời đặt là URL, sẽ cập nhật khi tải
                'error': None,
                'created_at': time.time()
            }
            download_tasks[task_id] = task_info
            task_queue.put(task_id)
            added_tasks.append(task_info)

    return jsonify({
        'success': True,
        'count': len(added_tasks),
        'tasks': added_tasks
    })


@app.route('/api/queue/status', methods=['GET'])
def get_queue_status():
    """Lấy danh sách tất cả các tác vụ trong hàng đợi và trạng thái của chúng"""
    with tasks_lock:
        tasks_list = list(download_tasks.values())

    # Sắp xếp theo thời gian tạo tăng dần
    tasks_list.sort(key=lambda x: x.get('created_at', 0))

    summary = {
        'total': len(tasks_list),
        'queued': sum(1 for t in tasks_list if t['status'] == 'queued'),
        'downloading': sum(1 for t in tasks_list if t['status'] in ['downloading', 'processing']),
        'finished': sum(1 for t in tasks_list if t['status'] == 'finished'),
        'error': sum(1 for t in tasks_list if t['status'] == 'error'),
        'cancelled': sum(1 for t in tasks_list if t['status'] == 'cancelled'),
    }

    return jsonify({
        'tasks': tasks_list,
        'summary': summary
    })


@app.route('/api/queue/cancel/<task_id>', methods=['POST'])
def cancel_task(task_id):
    """Hủy một tác vụ nếu nó đang chờ trong hàng đợi"""
    with tasks_lock:
        task = download_tasks.get(task_id)
        if not task:
            return jsonify({'error': 'Không tìm thấy tác vụ'}), 404

        if task['status'] == 'queued':
            task['status'] = 'cancelled'
            return jsonify({'success': True, 'message': 'Đã hủy tác vụ trong hàng đợi'})
        elif task['status'] in ['downloading', 'processing']:
            return jsonify({'error': 'Tác vụ đang tải không thể hủy trực tiếp'}), 400
        else:
            return jsonify({'message': 'Tác vụ đã kết thúc'}), 200


@app.route('/api/queue/clear', methods=['POST'])
def clear_completed_tasks():
    """Xóa các tác vụ đã hoàn thành hoặc lỗi khỏi giao diện hàng đợi"""
    with tasks_lock:
        to_delete = [
            tid for tid, t in download_tasks.items()
            if t['status'] in ['finished', 'error', 'cancelled']
        ]
        for tid in to_delete:
            del download_tasks[tid]

    return jsonify({'success': True, 'cleared_count': len(to_delete)})


# Giữ endpoint đơn lẻ để tương thích ngược
@app.route('/api/download', methods=['POST'])
def single_download():
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    format_type = data.get('format_type', 'video_best')

    if not url:
        return jsonify({'error': 'Vui lòng cung cấp URL'}), 400

    task_id = uuid.uuid4().hex
    with tasks_lock:
        task_info = {
            'id': task_id,
            'url': url,
            'format_type': format_type,
            'status': 'queued',
            'progress': 0,
            'speed': '',
            'eta': '',
            'downloaded': '0 B',
            'total': '0 B',
            'filename': None,
            'title': url,
            'error': None,
            'created_at': time.time()
        }
        download_tasks[task_id] = task_info
        task_queue.put(task_id)

    return jsonify({'task_id': task_id})


@app.route('/api/progress/<task_id>', methods=['GET'])
def get_progress(task_id):
    with tasks_lock:
        task = download_tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Không tìm thấy tác vụ'}), 404
    return jsonify(task)


@app.route('/api/file/<path:filename>', methods=['GET'])
def download_file(filename):
    try:
        return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)
    except FileNotFoundError:
        abort(404)


@app.route('/api/open-folder', methods=['POST'])
def open_folder():
    try:
        if sys.platform == 'win32':
            os.startfile(DOWNLOAD_DIR)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', DOWNLOAD_DIR])
        else:
            subprocess.Popen(['xdg-open', DOWNLOAD_DIR])
        return jsonify({'success': True, 'path': DOWNLOAD_DIR})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/history', methods=['GET'])
def get_history():
    files = []
    try:
        for entry in os.scandir(DOWNLOAD_DIR):
            if entry.is_file():
                stat = entry.stat()
                ext = os.path.splitext(entry.name)[1].lower().replace('.', '')
                is_audio = ext in ['mp3', 'm4a', 'wav', 'flac', 'aac']
                files.append({
                    'name': entry.name,
                    'size': format_bytes(stat.st_size),
                    'size_bytes': stat.st_size,
                    'time': datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m/%Y %H:%M'),
                    'mtime': stat.st_mtime,
                    'is_audio': is_audio,
                    'ext': ext
                })
        files.sort(key=lambda x: x['mtime'], reverse=True)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({'files': files, 'folder_path': DOWNLOAD_DIR})


@app.route('/api/delete/<path:filename>', methods=['DELETE'])
def delete_file(filename):
    try:
        file_path = os.path.join(DOWNLOAD_DIR, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return jsonify({'success': True})
        return jsonify({'error': 'File không tồn tại'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Video Downloader Web Server (Queue Mode) đang khởi động...")
    print(f"📁 Thư mục lưu video: {DOWNLOAD_DIR}")
    print("🌐 Truy cập tại: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False)
