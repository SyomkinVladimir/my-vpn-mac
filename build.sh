#!/bin/bash

echo "🐙 Начинаем сборку OctaraAgent..."

echo "🧹 1/4 Очистка старых билдов..."
rm -rf build dist/*.app

echo "📦 2/4 Сборка приложения (PyInstaller)..."
pyinstaller --noconfirm --windowed --hidden-import keyring --name "OctaraAgent" menu_app.py > /dev/null 2>&1

echo "👻 3/4 Скрытие иконки из Дока..."
plutil -insert LSUIElement -bool true dist/OctaraAgent.app/Contents/Info.plist

echo "🔐 4/4 Подписание кода (Code Signing)..."
codesign --force --deep --sign - dist/OctaraAgent.app

echo "🚀 Запуск приложения..."
open dist/OctaraAgent.app

echo "✅ Готово! Осьминог должен появиться в трее."