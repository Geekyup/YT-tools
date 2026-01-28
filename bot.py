import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command
import yt_dlp
import logging

logging.getLogger('yt_dlp').setLevel(logging.ERROR)

BOT_TOKEN = "ВАШ_ТОКЕН_ЗДЕСЬ"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

video_cache = {}


def get_ydl_opts():
    """Оптимальные опции для yt-dlp"""
    return {
        'quiet': False,
        'no_warnings': False,
        'socket_timeout': 30,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        },
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
                'skip': ['hls', 'dash']
            }
        },
        'retries': 5,
        'fragment_retries': 5,
        'skip_unavailable_fragments': True,
        'ignore_no_formats_error': False,
    }


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Я скачиваю видео с YouTube.\n\n"
        "Отправь ссылку на видео и выбери качество:\n"
        "🎥 720p, 480p, 360p\n"
        "🎵 Только аудио\n\n"
        "⚠️ Максимум до 2GB"
    )


@dp.message(F.text.contains("youtube.com") | F.text.contains("youtu.be"))
async def handle_youtube_link(message: Message):
    url = message.text.strip()
    status_msg = await message.answer("🔍 Загружаю информацию...")
    
    try:
        ydl_opts = get_ydl_opts()
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            video_id = str(message.message_id)
            video_cache[video_id] = {
                'url': url,
                'title': info.get('title', 'Unknown')
            }
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎥 720p (HD)", callback_data=f"dl_{video_id}_720")],
                [InlineKeyboardButton(text="📱 480p (SD)", callback_data=f"dl_{video_id}_480")],
                [InlineKeyboardButton(text="📉 360p", callback_data=f"dl_{video_id}_360")],
                [InlineKeyboardButton(text="🎵 Аудио MP3", callback_data=f"dl_{video_id}_audio")]
            ])
            
            duration = info.get('duration', 0)
            duration_min = duration // 60 if duration else 0
            duration_sec = duration % 60 if duration else 0
            
            title = info.get('title', 'Видео')
            uploader = info.get('uploader', 'Unknown')
            
            await status_msg.edit_text(
                f"✅ <b>{title}</b>\n\n"
                f"⏱️ Длина: {duration_min}:{duration_sec:02d}\n"
                f"👤 Автор: {uploader}\n\n"
                f"Выбери качество:",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
    except Exception as e:
        error_msg = str(e)[:80]
        await status_msg.edit_text(f"❌ Ошибка: {error_msg}\n\nПроверь ссылку")


@dp.callback_query(F.data.startswith("dl_"))
async def process_download(callback: CallbackQuery):
    await callback.answer()
    
    try:
        parts = callback.data.split("_")
        video_id = parts[1]
        quality = parts[2]
        
        if video_id not in video_cache:
            await callback.message.edit_text("❌ Видео устарело. Отправь ссылку снова")
            return
        
        video_info = video_cache[video_id]
        url = video_info['url']
        title = video_info['title']
        
        await callback.message.edit_text(f"⏬ Скачиваю {quality}...")
        
        filename = f"video_{video_id}"
        ydl_opts = get_ydl_opts()
        
        if quality == "audio":
            # Аудио в любом доступном формате
            ydl_opts.update({
                'format': 'bestaudio',
                'postprocessors': [],
                'outtmpl': filename + '.%(ext)s',
            })
        else:
            # Видео правильного формата 16:9
            ydl_opts.update({
                'format': f'(bv*[height<={quality}]+ba/b[height<={quality}])[filesize<?2G]',
                'outtmpl': filename + '.%(ext)s',
            })
        
        # Скачиваем
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Ищем файл
        downloaded_file = None
        for file in os.listdir('.'):
            if file.startswith(filename) and not file.endswith('.info.json'):
                downloaded_file = file
                break
        
        if not downloaded_file:
            await callback.message.edit_text("❌ Файл не найден")
            return
        
        # Проверяем размер
        file_size = os.path.getsize(downloaded_file)
        
        if file_size == 0:
            os.remove(downloaded_file)
            await callback.message.edit_text("❌ YouTube заблокировал. Попробуй другое видео")
            return
        
        file_size_mb = file_size / (1024 * 1024)
        
        if file_size_mb > 2000:
            os.remove(downloaded_file)
            await callback.message.edit_text(f"❌ Слишком большой: {file_size_mb:.0f}MB")
            return
        
        await callback.message.edit_text(f"📤 Отправляю ({file_size_mb:.1f}MB)...")
        
        # Отправляем
        try:
            if quality == "audio":
                audio_file = FSInputFile(downloaded_file)
                await callback.message.answer_audio(
                    audio=audio_file,
                    title=title[:100],
                    performer="YouTube"
                )
            else:
                video_file = FSInputFile(downloaded_file)
                await callback.message.answer_video(
                    video=video_file,
                    caption=f"{title[:100]}\n\n{quality}p"
                )
            
            await callback.message.delete()
        except Exception as send_error:
            await callback.message.edit_text(f"❌ Ошибка отправки")
        finally:
            # Очищаем
            if os.path.exists(downloaded_file):
                try:
                    os.remove(downloaded_file)
                except:
                    pass
            if video_id in video_cache:
                del video_cache[video_id]
        
    except Exception as e:
        error_msg = str(e)[:100]
        await callback.message.edit_text(f"❌ Ошибка: {error_msg}")
        
        # Удаляем оставшиеся файлы
        try:
            video_id = callback.data.split("_")[1]
            filename = f"video_{video_id}"
            for file in os.listdir('.'):
                if file.startswith(filename):
                    try:
                        os.remove(file)
                    except:
                        pass
        except:
            pass


async def main():
    print("\n" + "=" * 60)
    print("🚀 YouTube Downloader Bot запущен!")
    print("=" * 60)
    print("Бот готов к использованию. Нажмите Ctrl+C для остановки")
    print("=" * 60 + "\n")
    
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        print("\n⏹ Бот остановлен пользователем")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
