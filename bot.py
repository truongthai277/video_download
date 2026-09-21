import os
import sys
import time
import queue
import threading
import telebot
from telebot import types
from dotenv import load_dotenv
import yt_dlp

# Nạp biến môi trường từ file .env
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

# Thư mục lưu video
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Hàng đợi tải video cho Bot
bot_queue = queue.Queue()


def format_bytes(size):
    if not size or size <= 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def extract_urls(text):
    if not text:
        return []
    urls = []
    seen = set()
    for word in text.split():
        w = word.strip()
        if (w.startswith("http://") or w.startswith("https://")) and w not in seen:
            urls.append(w)
            seen.add(w)
    return urls


def download_media(url, format_type='video_best'):
    """Tải video hoặc audio bằng yt-dlp"""
    outtmpl = os.path.join(DOWNLOAD_DIR, '%(title).150s [%(id)s].%(ext)s')
    ydl_opts = {
        'outtmpl': outtmpl,
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

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        final_filename = None
        if 'requested_downloads' in info and info['requested_downloads']:
            filepath = info['requested_downloads'][0].get('filepath')
            if filepath and os.path.exists(filepath):
                final_filename = filepath

        if not final_filename:
            expected_filepath = ydl.prepare_filename(info)
            if format_type == 'audio_mp3':
                base, _ = os.path.splitext(expected_filepath)
                expected_filepath = base + '.mp3'
            
            if os.path.exists(expected_filepath):
                final_filename = expected_filepath
            else:
                base, _ = os.path.splitext(expected_filepath)
                for ext in ['.mp4', '.mkv', '.webm', '.mp3']:
                    if os.path.exists(base + ext):
                        final_filename = base + ext
                        break

        return {
            'filepath': final_filename,
            'title': info.get('title', 'Video'),
            'duration': info.get('duration', 0),
            'uploader': info.get('uploader', 'Unknown'),
            'format_type': format_type
        }


def process_queue(bot):
    """Worker xử lý tải lần lượt từng video được gửi từ Telegram"""
    while True:
        task = bot_queue.get()
        try:
            chat_id = task['chat_id']
            url = task['url']
            format_type = task['format_type']
            msg_id = task.get('msg_id')

            bot.edit_message_text(
                f"⏳ <b>Đang tải video...</b>\n🔗 <code>{url}</code>\nVui lòng chờ trong giây lát...",
                chat_id=chat_id,
                message_id=msg_id,
                parse_mode='HTML'
            )

            result = download_media(url, format_type)
            filepath = result.get('filepath')

            if not filepath or not os.path.exists(filepath):
                bot.edit_message_text(
                    f"❌ Không tìm thấy file sau khi tải: {url}",
                    chat_id=chat_id,
                    message_id=msg_id
                )
                continue

            filesize = os.path.getsize(filepath)
            filesize_str = format_bytes(filesize)
            title = result.get('title', 'Video')

            # Giới hạn dung lượng gửi qua Telegram bot thông thường là 50MB (52,428,800 bytes)
            MAX_TELEGRAM_SIZE = 49.5 * 1024 * 1024

            if filesize <= MAX_TELEGRAM_SIZE:
                bot.edit_message_text(
                    f"📤 <b>Đang gửi file lên Telegram...</b>\n🎬 <b>{title}</b> ({filesize_str})",
                    chat_id=chat_id,
                    message_id=msg_id,
                    parse_mode='HTML'
                )

                with open(filepath, 'rb') as f:
                    if format_type == 'audio_mp3':
                        bot.send_audio(
                            chat_id=chat_id,
                            audio=f,
                            title=title,
                            performer=result.get('uploader'),
                            duration=result.get('duration'),
                            caption=f"🎵 {title}\n💾 Dung lượng: {filesize_str}"
                        )
                    else:
                        bot.send_video(
                            chat_id=chat_id,
                            video=f,
                            caption=f"🎬 <b>{title}</b>\n💾 Dung lượng: {filesize_str}",
                            parse_mode='HTML',
                            supports_streaming=True
                        )

                bot.delete_message(chat_id=chat_id, message_id=msg_id)
            else:
                # File vượt quá 50MB, thông báo lưu trên máy tính
                bot.edit_message_text(
                    f"✅ <b>Tải thành công!</b>\n\n"
                    f"🎬 <b>Tiêu đề:</b> {title}\n"
                    f"💾 <b>Dung lượng:</b> {filesize_str}\n"
                    f"📁 <b>Tên file:</b> <code>{os.path.basename(filepath)}</code>\n\n"
                    f"⚠️ <i>Do file lớn hơn 50MB (giới hạn của Telegram Bot API), file đã được lưu an toàn trong thư mục <b>downloads</b> trên máy tính của bạn!</i>",
                    chat_id=chat_id,
                    message_id=msg_id,
                    parse_mode='HTML'
                )

        except Exception as e:
            try:
                bot.send_message(task['chat_id'], f"❌ <b>Lỗi khi tải video:</b>\n<code>{str(e)}</code>", parse_mode='HTML')
            except Exception:
                pass
        finally:
            bot_queue.task_done()


def main():
    if not BOT_TOKEN or BOT_TOKEN == "your_bot_token_here":
        print("=" * 60)
        print("⚠️ CHƯA CẤU HÌNH BOT TOKEN TELEGRAM!")
        print("Vui lòng mở file '.env' hoặc nhập TOKEN vào biến môi trường TELEGRAM_BOT_TOKEN.")
        print("Xem hướng dẫn tạo Bot với @BotFather trong phần chat.")
        print("=" * 60)
        token_input = input("Nhập Bot Token của bạn ngay tại đây (hoặc Enter để thoát): ").strip()
        if token_input:
            with open(os.path.join(BASE_DIR, ".env"), "w", encoding="utf-8") as env_file:
                env_file.write(f"TELEGRAM_BOT_TOKEN={token_input}\n")
            bot = telebot.TeleBot(token_input)
        else:
            sys.exit(1)
    else:
        bot = telebot.TeleBot(BOT_TOKEN)

    # Khởi động background worker xử lý tải
    worker = threading.Thread(target=process_queue, args=(bot,), daemon=True)
    worker.start()

    @bot.message_handler(commands=['start', 'help'])
    def send_welcome(message):
        welcome_text = (
            "👋 <b>Xin chào! Tôi là Bot Tải Video.</b>\n\n"
            "Chỉ cần gửi cho tôi bất kỳ đường link video nào từ:\n"
            "• 🔴 YouTube\n"
            "• ⚫ TikTok (không logo)\n"
            "• 🔵 Facebook (Reels / Watch)\n"
            "• 🟣 Instagram (Reels / Post)\n"
            "• ⚪ Twitter / X, SoundCloud...\n\n"
            "📥 <i>Bạn có thể gửi 1 link hoặc gửi nhiều link cùng lúc (mỗi dòng 1 link)!</i>"
        )
        bot.reply_to(message, welcome_text, parse_mode='HTML')

    @bot.message_handler(func=lambda message: True)
    def handle_message(message):
        text = message.text or ""
        urls = extract_urls(text)

        if not urls:
            bot.reply_to(
                message,
                "⚠️ Không tìm thấy đường link video hợp lệ trong tin nhắn.\n"
                "Vui lòng gửi link bắt đầu bằng <code>http://</code> hoặc <code>https://</code>",
                parse_mode='HTML'
            )
            return

        # Nếu chỉ có 1 link, đưa ra menu chọn chất lượng
        if len(urls) == 1:
            url = urls[0]
            markup = types.InlineKeyboardMarkup(row_width=2)
            btn_best = types.InlineKeyboardButton("🎬 Video Max (MP4)", callback_data=f"dl|video_best|{url}")
            btn_720 = types.InlineKeyboardButton("📺 720p (HD)", callback_data=f"dl|video_720|{url}")
            btn_mp3 = types.InlineKeyboardButton("🎵 Âm Thanh (MP3)", callback_data=f"dl|audio_mp3|{url}")
            markup.add(btn_best, btn_720)
            markup.add(btn_mp3)

            bot.reply_to(
                message,
                f"🔗 <b>Đã nhận link:</b>\n<code>{url}</code>\n\nChọn định dạng bạn muốn tải:",
                reply_markup=markup,
                parse_mode='HTML'
            )
        else:
            # Nếu có nhiều link, tự động thêm tất cả vào hàng đợi tải video tốt nhất
            status_msg = bot.reply_to(
                message,
                f"📋 <b>Đã nhận {len(urls)} link video!</b>\nĐang đưa vào hàng đợi tải lần lượt từng video...",
                parse_mode='HTML'
            )
            for u in urls:
                task_msg = bot.send_message(
                    message.chat.id,
                    f"⏳ <i>Đang chờ trong hàng đợi:</i>\n<code>{u}</code>",
                    parse_mode='HTML'
                )
                bot_queue.put({
                    'chat_id': message.chat.id,
                    'url': u,
                    'format_type': 'video_best',
                    'msg_id': task_msg.message_id
                })

    @bot.callback_query_handler(func=lambda call: call.data.startswith('dl|'))
    def callback_download(call):
        try:
            parts = call.data.split('|', 2)
            format_type = parts[1]
            url = parts[2]

            bot.edit_message_text(
                f"⏳ <b>Đã đưa vào hàng đợi tải:</b>\n🔗 <code>{url}</code>\nĐang xử lý...",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode='HTML'
            )

            bot_queue.put({
                'chat_id': call.message.chat.id,
                'url': url,
                'format_type': format_type,
                'msg_id': call.message.message_id
            })
            bot.answer_callback_query(call.id, "Đã thêm vào hàng đợi!")
        except Exception as e:
            bot.answer_callback_query(call.id, f"Lỗi: {str(e)}")

    print("=" * 60)
    print("🤖 Telegram Bot đang chạy và lắng nghe tin nhắn...")
    print("Nhấn Ctrl + C để dừng Bot.")
    print("=" * 60)
    bot.infinity_polling(timeout=20, long_polling_timeout=10)


if __name__ == '__main__':
    main()
