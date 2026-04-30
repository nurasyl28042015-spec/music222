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
TOKEN = "8779251097:AAFLBBJhfp58iYJw8_8uKacKQmPKXOHKESQ"
DOWNLOAD_PATH = "bot_downloads"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

bot = Bot(token=TOKEN)
dp = Dispatcher()
shazam = Shazam()

def clear_download_folder():
    if os.path.exists(DOWNLOAD_PATH):
        shutil.rmtree(DOWNLOAD_PATH)
    os.makedirs(DOWNLOAD_PATH)

# Функция поиска аудио по названию (для ссылок и поиска)
async def download_audio_by_title(title: str):
    unique_id = str(asyncio.get_event_loop().time()).replace('.', '')
    path_template = f"{DOWNLOAD_PATH}/audio_{unique_id}.%(ext)s"
    
    ydl_opts = {
        'outtmpl': path_template,
        'format': 'bestaudio/best',
        'quiet': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    # Ищем официальное аудио на YouTube по названию из Shazam
    search_query = f"ytsearch1:{title} official audio"
    with YoutubeDL(ydl_opts) as ydl:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(search_query, download=True))
        if 'entries' in info:
            info = info['entries'][0]
        path = ydl.prepare_filename(info).rsplit('.', 1)[0] + ".mp3"
        return path, info.get('title', 'Unknown')

# Функция для поиска списка треков (для текстовых запросов)
async def search_tracks(query: str, limit=5):
    ydl_opts = {
        'quiet': True,
        'noplaylist': True,
        'default_search': f'ytsearch{limit}',
        'nocheckcertificate': True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(f"ytsearch{limit}:{query} official audio", download=False))
        if not info or 'entries' not in info:
            return []
        return [{'id': e['id'], 'title': e['title']} for e in info['entries']]

# Функция скачивания по конкретному ID (для кнопок)
async def download_by_id(video_id: str):
    unique_id = str(asyncio.get_event_loop().time()).replace('.', '')
    path_template = f"{DOWNLOAD_PATH}/audio_{unique_id}.%(ext)s"
    ydl_opts = {
        'outtmpl': path_template,
        'format': 'bestaudio/best',
        'quiet': True,
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

# Скачивание видео из TikTok/Reels
async def download_video_link(url: str):
    unique_id = str(asyncio.get_event_loop().time()).replace('.', '')
    filename = f"{DOWNLOAD_PATH}/video_{unique_id}.%(ext)s"
    ydl_opts = {
        'outtmpl': filename,
        'quiet': True,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    }
    with YoutubeDL(ydl_opts) as ydl:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
        return ydl.prepare_filename(info)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("хуйло ебаннаясыллку кидай или название песни**!")

# --- ОБНОВЛЕННЫЙ ХЕНДЛЕР ССЫЛОК ---
@dp.message(lambda msg: msg.text and any(x in msg.text.lower() for x in ['tiktok.com', 'instagram.com', 'youtube.com/shorts', 'youtu.be']))
async def handle_link(message: types.Message):
    status = await message.answer(" Обработка... Загружаю видео.")
    files_to_delete = []
    try:
        # 1. Скачиваем видео
        video_path = await download_video_link(message.text)
        files_to_delete.append(video_path)
        
        # 2. Распознаем через Shazam
        await status.edit_text(" Распознаю музыку...")
        out = await shazam.recognize_song(video_path)
        
        if out and out.get('track'):
            track_title = f"{out['track']['subtitle']} - {out['track']['title']}"
            await status.edit_text(f" Найдено: {track_title}\n📥 Ищу полную версию MP3...")
            
            # 3. АВТОМАТИЧЕСКИ КАЧАЕМ MP3
            audio_path, final_audio_title = await download_audio_by_title(track_title)
            files_to_delete.append(audio_path)
            
            # 4. Отправляем и видео, и аудио
            await message.answer_video(types.FSInputFile(video_path), caption=f" Видео")
            await message.answer_audio(types.FSInputFile(audio_path), title=final_audio_title, caption=" Полная версия")
        else:
            await status.edit_text(" Музыка не распознана, отправляю только видео.")
            await message.answer_video(types.FSInputFile(video_path))

    except Exception as e:
        logging.error(e)
        await message.answer(f"Ошибка при обработке ссылки.")
    finally:
        await asyncio.sleep(2)
        try: await status.delete()
        except: pass
        # Удаляем временные файлы
        for f in files_to_delete:
            if os.path.exists(f): os.remove(f)

# Поиск по названию (кнопки)
@dp.message(F.text)
async def handle_search(message: types.Message):
    query = message.text
    status = await message.answer(f" Ищу: {query}...")
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

# Обработка кнопок
@dp.callback_query(F.data.startswith("dl_"))
async def process_download(callback: types.CallbackQuery):
    video_id = callback.data.split("_")[1]
    await callback.message.edit_text("Скачиваю выбранный трек...")
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
    try: asyncio.run(main())
    except: pass