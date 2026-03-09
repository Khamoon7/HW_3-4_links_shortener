#!/bin/bash

# Применяем миграции базы данных
alembic upgrade head

# Запускаем приложение через gunicorn с uvicorn-воркерами
cd src
# Один воркер: фоновая задача cleanup запускается в lifespan и не должна дублироваться
gunicorn main:app --workers 1 --worker-class uvicorn.workers.UvicornWorker --bind=0.0.0.0:8000
