FROM python:3.11-slim

# Рабочая директория приложения
RUN mkdir /url_shortener
WORKDIR /url_shortener

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY . .

# Конвертируем Windows CRLF -> LF встроенными средствами и выставляем права
RUN sed -i 's/\r//' docker/*.sh && chmod a+x docker/*.sh
