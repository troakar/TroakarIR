from PIL import Image
import os
import tkinter as tk
from tkinter import filedialog

def slice_sprite_sheet(image_path=None, grid_size=4, output_folder="masks"):
    # Создаем папку, если ее нет
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        
    # Если путь к изображению не передан, предлагаем выбрать
    if image_path is None:
        root = tk.Tk()
        root.withdraw()  # Скрываем основное окно
        image_path = filedialog.askopenfilename(
            title="Выберите изображение для нарезки",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp")]
        )
        if not image_path:
            print("🚫 Выбор файла отменен")
            return
    
    img = Image.open(image_path).convert('L') # Сразу в Ч/Б
    width, height = img.size
    
    # Считаем размер одного тайла (1024 / 4 = 256)
    tile_w = width // grid_size
    tile_h = height // grid_size
    
    count = 1
    for row in range(grid_size):
        for col in range(grid_size):
            # Высчитываем координаты обрезки (left, upper, right, lower)
            left = col * tile_w
            upper = row * tile_h
            right = left + tile_w
            lower = upper + tile_h
            
            # Вырезаем квадрат 256x256
            tile = img.crop((left, upper, right, lower))
            
            # Сжимаем до 128x128 для нашего Taichi-движка
            # И используем NEAREST, чтобы сохранить жесткие черно-белые края (без мыла)
            tile = tile.resize((128, 128), Image.NEAREST)
            
            # Уменьшаем на 1 пиксель, чтобы создать пространство для границы
            tile = tile.resize((127, 127), Image.NEAREST)
            
            # Создаем новое изображение 128x128 с черной границей
            bordered_tile = Image.new('L', (128, 128), color=0)  # Черный фон
            bordered_tile.paste(tile, (1, 1))  # Вставляем уменьшенное изображение с отступом 1 пиксель
            
            # Сохраняем
            filename = f"shape_{count:02d}.png"
            bordered_tile.save(os.path.join(output_folder, filename))
            print(f"✅ Сохранен резонатор: {filename}")
            count += 1

# ЗАПУСК
slice_sprite_sheet()