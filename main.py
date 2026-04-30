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
# Твой токен и путь для временных файлов
TOKEN = "8779251097:AAFLBBJhfp58iYJw8_8uKacKQmPKXOHKESQ"
DOWNLOAD_PATH = "bot_downloads"

# Настройка логирования для отслеживания ошибок
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

bot = Bot(token=TOKEN)
dp = Dispatcher()
shazam = Shazam()

def clear_download_folder():
    """Очищает папку загрузок при запуске бота."""
    if os.path.exists(DOWNLOAD_PATH):
        shutil.rmtree(DOWNLOAD_PATH)
    os.makedirs(DOWNLOAD_PATH)

# --- ПАРАМЕТРЫ ОБХОДА БЛОКИРОВОК ---
# Эти настройки помогают YouTube "поверить", что запрос идет от реального пользователя
YDL_COMMON_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'nocheckcertificate': True,
    # Использование клиента Android помогает обойти ошибку "Sign in to confirm you're not a bot"
    'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
}

async def download_audio_by_title(title: str):
    """Ищет и скачивает аудио по названию."""
    unique_id = str(asyncio.get_event_loop().time()).replace('.', '')
    path_template = f"{DOWNLOAD_PATH}/audio_{unique_id}.%(ext)s"
    
    ydl_opts = {
        **YDL_COMMON_OPTS,
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

async def search_tracks(query: str, limit=5):
    """Ищет варианты песен для вывода в кнопках."""
    ydl_opts = {
        **YDL_COMMON_OPTS,
        'noplaylist': True,
        'default_search': f'ytsearch{limit}',
    }
    with YoutubeDL(ydl_opts) as ydl:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(f"ytsearch{limit}:{query} official audio", download=False))
        if not info or 'entries' not in info:
            return []
        return [{'id': e['id'], 'title': e['title']} for e in info['entries']]

async def download_by_id(video_id: str):
    """Скачивает аудио по конкретному ID YouTube."""
    unique_id = str(asyncio.get_event_loop().time()).replace('.', '')
    path_template = f"{DOWNLOAD_PATH}/audio_{unique_id}.%(ext)s"
    ydl_opts = {
        **YDL_COMMON_OPTS,
        'outtmpl': path_template,
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    url = f"https://www.youtube.com/watch?v={video_id}"
    with YoutubeDL(ydl_opts) as ydl:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
        path = ydl.prepare_filename(info).rsplit('.', 1)[0] + ".mp3"
        return path, info.get('title', 'Unknown')

async def download_video_link(url: str):
    """Скачивает видео файл из ссылки."""
    unique_id = str(asyncio.get_event_loop().time()).replace('.', '')
    filename = f"{DOWNLOAD_PATH}/video_{unique_id}.%(ext)s"
    ydl_opts = {
        **YDL_COMMON_OPTS,
        'outtmpl': filename,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    }
    with YoutubeDL(ydl_opts) as ydl:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
        return ydl.prepare_filename(info)

# --- ОБРАБОТЧИКИ СООБЩЕНИЙ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Я помогу тебе скачать музыку.\n\n"
                         "🔗 Пришли мне ссылку на TikTok/Reels или просто напиши название песни!")

@dp.message(lambda msg: msg.text and any(x in msg.text.lower() for x in ['tiktok.com', 'instagram.com', 'youtube.com/shorts', 'youtu.be']))
async def handle_link(message: types.Message):
    status = await message.answer("⏳ Обработка... Загружаю видео.")
    files_to_delete = []
    try:
        # 1. Загрузка видео
        video_path = await download_video_link(message.text)
        files_to_delete.append(video_path)
        
        # 2. Распознавание музыки
        await status.edit_text("🔍 Распознаю музыку...")
        # Обновленный метод .recognize()
        out = await shazam.recognize(video_path)
        
        if out and out.get('track'):
            track_title = f"{out['track']['subtitle']} - {out['track']['title']}"
            await status.edit_text(f"✅ Найдено: {track_title}\n📥 Ищу полную версию MP3...")
            
            # 3. Загрузка MP3
            audio_path, final_audio_title = await download_audio_by_title(track_title)
            files_to_delete.append(audio_path)
            
            # 4. Отправка файлов пользователю
            await message.answer_video(types.FSInputFile(video_path), caption="🎬 Видео")
            await message.answer_audio(types.FSInputFile(audio_path), title=final_audio_title, caption="🎵 Полная версия")
        else:
            await status.edit_text("🤷 Музыка не распознана, отправляю только видео.")
            await message.answer_video(types.FSInputFile(video_path))

    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await message.answer("❌ Не удалось обработать ссылку. Возможно, видео защищено или YouTube блокирует запрос.")
    finally:
        await asyncio.sleep(2)
        try: await status.delete()
        except: pass
        # Удаляем временные файлы, чтобы не занимать место на диске
        for f in files_to_delete:
            if os.path.exists(f): os.remove(f)

@dp.message(F.text)
async def handle_search(message: types.Message):
    """Обработчик текстовых запросов (поиск по названию)."""
    query = message.text
    status = await message.answer(f"🔎 Ищу: {query}...")
    try:
        results = await search_tracks(query)
        if not results:
            await status.edit_text("Ничего не найдено.")
            return

        builder = InlineKeyboardBuilder()
        for res in results:
            short_title = (res['title'][:40] + '..') if len(res['title']) > 40 else res['title']
            builder.row(types.InlineKeyboardButton(text=f"🎵 {short_title}", callback_data=f"dl_{res['id']}"))

        await status.edit_text(f"Результаты по запросу '{query}':", reply_markup=builder.as_markup())
    except:
        await status.edit_text("Ошибка при поиске.")

@dp.callback_query(F.data.startswith("dl_"))
async def process_download(callback: types.CallbackQuery):
    """Обработка нажатия на кнопку скачивания трека из результатов поиска."""
    video_id = callback.data.split("_")[1]
    await callback.message.edit_text("📥 Скачиваю выбранный трек...")
    try:
        path, title = await download_by_id(video_id)
        await callback.message.answer_audio(types.FSInputFile(path), title=title)
        if os.path.exists(path): os.remove(path)
        await callback.message.delete()
    except:
        await callback.message.answer("Не удалось скачать.")

async def main():
    clear_download_folder()
    logging.info("Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
