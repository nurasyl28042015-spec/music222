import os
import asyncio
import logging
import shutil
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from yt_dlp import YoutubeDL
from shazamio import Shazam

# --- КОНФИГУРАЦИЯ ---
# Твой токен (не меняй, если он рабочий)
TOKEN = "8779251097:AAFLBBJhfp58iYJw8_8uKacKQmPKXOHKESQ"
DOWNLOAD_PATH = "bot_downloads"

# Настройка логов, чтобы видеть, что происходит внутри
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

bot = Bot(token=TOKEN)
dp = Dispatcher()
shazam = Shazam()

def clear_download_folder():
    """Создает или очищает папку для временных файлов видео и аудио."""
    if os.path.exists(DOWNLOAD_PATH):
        shutil.rmtree(DOWNLOAD_PATH)
    os.makedirs(DOWNLOAD_PATH)

# --- СПЕЦИАЛЬНЫЕ НАСТРОЙКИ ДЛЯ ОБХОДА БЛОКИРОВОК ---
# Эти параметры критически важны для работы на Render
YDL_OPTIONS = {
    'quiet': True,
    'no_warnings': True,
    'nocheckcertificate': True,
    # Имитируем запрос от мобильного приложения Android
    'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }
}

async def download_audio_by_title(title: str):
    """Ищет официальное аудио на YouTube и конвертирует в MP3."""
    unique_id = str(asyncio.get_event_loop().time()).replace('.', '')
    path_template = f"{DOWNLOAD_PATH}/audio_{unique_id}.%(ext)s"
    
    ydl_opts = {
        **YDL_OPTIONS,
        'outtmpl': path_template,
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    search_query = f"ytsearch1:{title} official audio"
    with YoutubeDL(ydl_opts) as ydl:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(search_query, download=True))
        if 'entries' in info:
            info = info['entries'][0]
        path = ydl.prepare_filename(info).rsplit('.', 1)[0] + ".mp3"
        return path, info.get('title', 'Unknown')

async def download_video_link(url: str):
    """Скачивает само видео (TikTok/Reels/Shorts)."""
    unique_id = str(asyncio.get_event_loop().time()).replace('.', '')
    filename = f"{DOWNLOAD_PATH}/video_{unique_id}.%(ext)s"
    ydl_opts = {
        **YDL_OPTIONS,
        'outtmpl': filename,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    }
    with YoutubeDL(ydl_opts) as ydl:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
        return ydl.prepare_filename(info)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Я готов скачивать музыку и видео.\n\n"
                         "Пришли мне ссылку на TikTok/Reels или просто название песни!")

@dp.message(lambda msg: msg.text and any(x in msg.text.lower() for x in ['tiktok.com', 'instagram.com', 'youtube.com/shorts', 'youtu.be']))
async def handle_link(message: types.Message):
    status = await message.answer("⏳ Начинаю загрузку...")
    files_to_delete = []
    try:
        # 1. Скачиваем видео
        video_path = await download_video_link(message.text)
        files_to_delete.append(video_path)
        
        # 2. Распознаем через Shazam (ИСПРАВЛЕНО: используем .recognize)
        await status.edit_text("🔍 Распознаю музыку...")
        out = await shazam.recognize(video_path)
        
        if out and out.get('track'):
            track_title = f"{out['track']['subtitle']} - {out['track']['title']}"
            await status.edit_text(f"✅ Найдено: {track_title}\n📥 Ищу MP3 версию...")
            
            # 3. Скачиваем MP3
            audio_path, final_title = await download_audio_by_title(track_title)
            files_to_delete.append(audio_path)
            
            # 4. Отправляем пользователю
            await message.answer_video(types.FSInputFile(video_path), caption="🎬 Видео")
            await message.answer_audio(types.FSInputFile(audio_path), title=final_title)
        else:
            await status.edit_text("🤷 Музыка не определена, отправляю видео.")
            await message.answer_video(types.FSInputFile(video_path))

    except Exception as e:
        logging.error(f"Ошибка загрузки: {e}")
        await message.answer("❌ Ошибка: YouTube заблокировал доступ или ссылка неверна.")
    finally:
        await asyncio.sleep(2)
        try: await status.delete()
        except: pass
        # Удаляем файлы, чтобы не занимать место на сервере Render
        for f in files_to_delete:
            if os.path.exists(f): os.remove(f)

# Поиск по текстовому названию
@dp.message(F.text)
async def handle_search(message: types.Message):
    query = message.text
    status = await message.answer(f"🔎 Ищу варианты для: {query}...")
    try:
        ydl_opts = {**YDL_OPTIONS, 'noplaylist': True, 'default_search': 'ytsearch5'}
        with YoutubeDL(ydl_opts) as ydl:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False))
            if not info or 'entries' not in info:
                await status.edit_text("Ничего не найдено.")
                return
            
            builder = InlineKeyboardBuilder()
            for res in info['entries']:
                short_title = (res['title'][:40] + '..') if len(res['title']) > 40 else res['title']
                builder.row(types.InlineKeyboardButton(text=f"🎵 {short_title}", callback_data=f"dl_{res['id']}"))
            
            await status.edit_text("Выбери нужный трек:", reply_markup=builder.as_markup())
    except Exception as e:
        logging.error(e)
        await status.edit_text("⚠️ Ошибка поиска.")

async def main():
    clear_download_folder()
    logging.info("Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except:
        pass
