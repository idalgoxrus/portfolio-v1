#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Создаю виртуальное окружение .venv ..."
    python -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt
python bot.py
