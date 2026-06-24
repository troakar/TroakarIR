# Git Cheat Sheet: Save and Push

## User Name & Email
```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

## Basic Workflow
```bash
git status               # Что изменилось
git add .                # Добавить ВСЕ файлы
git add file.py          # Добавить один файл
git add -p               # Добавить частями (по кусочкам)
git commit -m "Описание" # Создать коммит
git push origin main     # Запушить на GitHub
```

## Commit с доп. инфой
```bash
git commit -m "Заголовок" -m "Подробное описание"
git commit -m "fix: исправил баг с текстурами (ред. 5409)"
```

## Pull перед работой
```bash
git pull origin main     # Обновить перед началом
```

## Log
```bash
git log --oneline        # Краткая история
git log --oneline -5     # Последние 5 коммитов
git diff                 # Что изменилось но ещё не в add
```
