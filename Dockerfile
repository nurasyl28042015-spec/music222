# Используем легкий образ Python
FROM python:3.12-slim

# Устанавливаем FFmpeg и инструменты сборки внутри сервера
RUN apt-get update && apt-get install -y ffmpeg build-essential && apt-get clean

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы проекта
COPY . .

# Устанавливаем библиотеки
RUN pip install --no-cache-dir -r requirements.txt

# Запускаем бота
CMD ["python", "main.py"]