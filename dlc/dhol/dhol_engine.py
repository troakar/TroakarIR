# dlc/dhol/dhol_engine.py
import os
import sys
import numpy as np
import taichi as ti
import scipy.io.wavfile as wav
from scipy.signal import lfilter, butter, fftconvolve
import pyroomacoustics as pra
from engine.grid_builder import build_heterogeneous_grids

from engine.tactile import generate_tactile_profile
from engine.shell_texture import apply_dynamic_shell_texture
from config.materials import MATERIAL_PHYSICS
from config.instruments import PERCUSSION_PRESETS
from engine.core_taichi import generate_fdtd_ir

def get_effective_properties(mat: dict) -> dict:
    density = mat.get("density", 0.5)
    E_long = mat.get("E_long", 10.0)
    E_trans = mat.get("E_trans", mat.get("E_long", 10.0))
    loss = mat.get("loss_factor", 0.02)
    visco = mat.get("visco_gamma", 1e-5)
    poisson = mat.get("poisson", 0.3) # Добавляем коэффициент Пуассона по спецификации
    
    tactile = mat.get("tactile_profile", {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.0}).copy()
    
    # Рассчитываем суммарную долю включений для балансировки энергии
    inclusions = mat.get("inclusions", [])
    total_inc_ratio = sum(float(inc.get("density_ratio", 0.0)) for inc in inclusions)
    base_ratio = max(0.01, 1.0 - total_inc_ratio)
    
    for inc in inclusions:
        inc_mat = inc["material"]
        if isinstance(inc_mat, str):
            # Загружаем из актуальной базы материалов!
            inc_mat = MATERIAL_PHYSICS.get(inc_mat, {})
        
        ratio = float(inc.get("density_ratio", 0.1))
        density = density * (1.0 - ratio) + inc_mat.get("density", density) * ratio
        E_long = E_long * (1.0 - ratio) + inc_mat.get("E_long", E_long) * ratio
        E_trans = E_trans * (1.0 - ratio) + inc_mat.get("E_trans", inc_mat.get("E_long", E_trans)) * ratio
        loss = loss * (1.0 - ratio) + inc_mat.get("loss_factor", loss) * ratio
        visco = visco * (1.0 - ratio) + inc_mat.get("visco_gamma", visco) * ratio
        poisson = poisson * (1.0 - ratio) + inc_mat.get("poisson", poisson) * ratio
        
        inc_tactile = inc_mat.get("tactile_profile", {})
        tactile["fibrousness"] = tactile.get("fibrousness", 0.0) * (1-ratio) + inc_tactile.get("fibrousness", 0.0) * ratio
        tactile["fluidity"] = tactile.get("fluidity", 0.0) * (1-ratio) + inc_tactile.get("fluidity", 0.0) * ratio
        tactile["granularity"] = tactile.get("granularity", 0.0) * (1-ratio) + inc_tactile.get("granularity", 0.0) * ratio
        tactile["brittleness"] = tactile.get("brittleness", 0.0) * (1-ratio) + inc_tactile.get("brittleness", 0.0) * ratio
        
    effective_mat = mat.copy()
    effective_mat.update({
        "density": density,
        "E_long": E_long,
        "E_trans": E_trans,
        "loss_factor": loss,
        "visco_gamma": visco,
        "poisson": poisson,
        "tactile_profile": tactile
    })
    
    # Балансировка энергии: Пропорционально глушим базовые слои Art Direction матрицы,
    # чтобы освободить акустическое пространство под текстуры включений
    if "granular" in effective_mat and isinstance(effective_mat["granular"], dict):
        effective_mat["granular"] = effective_mat["granular"].copy()
        effective_mat["granular"]["intensity"] = effective_mat["granular"].get("intensity", 0.0) * base_ratio
        
    if "fibrous" in effective_mat and isinstance(effective_mat["fibrous"], dict):
        effective_mat["fibrous"] = effective_mat["fibrous"].copy()
        effective_mat["fibrous"]["intensity"] = effective_mat["fibrous"].get("intensity", 0.0) * base_ratio
        
    if "fluid" in effective_mat and isinstance(effective_mat["fluid"], dict):
        effective_mat["fluid"] = effective_mat["fluid"].copy()
        effective_mat["fluid"]["intensity"] = effective_mat["fluid"].get("intensity", 0.0) * base_ratio
        
    return effective_mat

def note_to_frequency(note_name: str) -> float:
    notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    name = note_name[:-1]
    octave = int(note_name[-1])
    if name.endswith('b'):
        flat_to_sharp = {'Db': 'C#', 'Eb': 'D#', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#'}
        name = flat_to_sharp.get(name, name)
    key_number = notes.index(name) + (octave + 1) * 12
    return 440.0 * (2.0 ** ((key_number - 69) / 12.0))

N_MAX = 512
N_REF = 128

def init_taichi_headless():
    try:
        # Проверяем, запущен ли уже движок
        taichi_is_ready = ti.lang.impl.get_runtime().prog is not None
    except Exception:
        taichi_is_ready = False

    if taichi_is_ready:
        return

    print("🔄 Инициализация Taichi Engine...")
    print("ℹ️  Принудительный выбор графического процессора (CUDA или Vulkan)")
    print("ℹ️  Выделение 2.0 ГБ видеопамяти для симуляции FDTD")
    
    try:
        ti.init(arch=ti.gpu, device_memory_GB=2.0, log_level=ti.WARN)
        print("✅ [TAICHI] GPU инициализирован. Активное аппаратное ускорение.")
    except Exception as e:
        print(f"⚠️  GPU не доступен: {e}")
        print("ℹ️  Принудительный fallback на CPU (низкая производительность)...")
        ti.init(arch=ti.cpu, log_level=ti.WARN)
        print("✅ [TAICHI] CPU инициализирован. Готов к работе.")

init_taichi_headless()

p_A = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
p_A_past = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
p_A_future = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
mask_A = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))

p_B = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
p_B_past = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
p_B_future = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
mask_B = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))

stat_vol_A = ti.field(dtype=ti.f32, shape=())
stat_vol_B = ti.field(dtype=ti.f32, shape=())
stat_strain_A = ti.field(dtype=ti.f32, shape=())
stat_strain_B = ti.field(dtype=ti.f32, shape=())

c_sq_x_A_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
c_sq_y_A_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
loss_A_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
visco_A_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))

c_sq_x_B_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
c_sq_y_B_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
loss_B_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
visco_B_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))


@ti.kernel
def init_dhol_fields(N: ti.i32):
    stat_vol_A[None] = 0.0
    stat_vol_B[None] = 0.0
    stat_strain_A[None] = 0.0
    stat_strain_B[None] = 0.0
    for i, j in ti.ndrange(N, N):
        p_A[i, j] = 0.0
        p_A_past[i, j] = 0.0
        p_A_future[i, j] = 0.0
        p_B[i, j] = 0.0
        p_B_past[i, j] = 0.0
        p_B_future[i, j] = 0.0

@ti.kernel
def compute_dhol_stats(N: ti.i32):
    stat_vol_A[None] = 0.0
    stat_vol_B[None] = 0.0
    stat_strain_A[None] = 0.0
    stat_strain_B[None] = 0.0
    
    for i, j in ti.ndrange(N, N):
        stat_vol_A[None] += p_A[i, j] * mask_A[i, j]
        if i > 0 and i < N-1 and j > 0 and j < N-1 and mask_A[i, j] > 0.5:
            dx = p_A[i+1, j] - p_A[i, j]
            dy = p_A[i, j+1] - p_A[i, j]
            stat_strain_A[None] += dx*dx + dy*dy
            
    for i, j in ti.ndrange(N, N):
        stat_vol_B[None] += p_B[i, j] * mask_B[i, j]
        if i > 0 and i < N-1 and j > 0 and j < N-1 and mask_B[i, j] > 0.5:
            dx = p_B[i+1, j] - p_B[i, j]
            dy = p_B[i, j+1] - p_B[i, j]
            stat_strain_B[None] += dx*dx + dy*dy

@ti.kernel
def step_dhol_fdtd(
    N: ti.i32,
    coupling_k: ti.f32, vol_A: ti.f32, vol_B: ti.f32,
    vol_A_delayed: ti.f32, vol_B_delayed: ti.f32, # <--- ДОБАВЛЕНЫ ЗАДЕРЖАННЫЕ ОБЪЕМЫ
    strike_x_A: ti.i32, strike_y_A: ti.i32, strike_val_A: ti.f32, radius_A: ti.f32,
    strike_x_B: ti.i32, strike_y_B: ti.i32, strike_val_B: ti.f32, radius_B: ti.f32,
    bend_A: ti.f32, bend_B: ti.f32,
    strain_A: ti.f32, strain_B: ti.f32,
    damp_A_val: ti.f32, damp_A_cov: ti.i32,
    damp_B_val: ti.f32, damp_B_cov: ti.i32
):
    # Раздельное давление воздуха: задержка создает акустический объем 3D кадушки
    p_air_A = -coupling_k * (vol_A + vol_B_delayed) * 0.05
    p_air_B = -coupling_k * (vol_A_delayed + vol_B) * 0.05
    
    safe_r_A = ti.max(radius_A, 0.001)
    safe_r_B = ti.max(radius_B, 0.001)

    # --- РАСЧЕТ ДЛЯ БАСОВОЙ МЕМБРАНЫ (A) ---
    for i, j in ti.ndrange(N, N):
        if i > 0 and i < N-1 and j > 0 and j < N-1 and mask_A[i, j] > 0.5:
            # Читаем локальные свойства из пространственных карт
            base_cx = c_sq_x_A_field[i, j]
            base_cy = c_sq_y_A_field[i, j]
            local_loss = loss_A_field[i, j]
            local_visco = visco_A_field[i, j]
            
            # Динамическое натяжение от силы удара
            dyn_c_x_A = ti.min(base_cx * (1.0 + bend_A * strain_A * 8000.0), 0.40)
            dyn_c_y_A = ti.min(base_cy * (1.0 + bend_A * strain_A * 8000.0), 0.40)

            lap_curr_x = p_A[i-1, j] + p_A[i+1, j] - 2.0 * p_A[i, j]
            lap_curr_y = p_A[i, j-1] + p_A[i, j+1] - 2.0 * p_A[i, j]
            lap_past_x = p_A_past[i-1, j] + p_A_past[i+1, j] - 2.0 * p_A_past[i, j]
            lap_past_y = p_A_past[i, j-1] + p_A_past[i, j+1] - 2.0 * p_A_past[i, j]
            
            lap_curr = dyn_c_x_A * lap_curr_x + dyn_c_y_A * lap_curr_y
            lap_past = dyn_c_x_A * lap_past_x + dyn_c_y_A * lap_past_y
            
            # Используем ЛОКАЛЬНУЮ вязкость (гасит резонанс на стыках с включениями)
            force = lap_curr + local_visco * (lap_curr - lap_past)
            force += p_air_A * mask_A[i, j]
            
            if radius_A > 0.1:
                dist = ti.cast((i - strike_x_A)**2 + (j - strike_y_A)**2, ti.f32)
                if dist < radius_A:
                    force += strike_val_A * ti.exp(-dist / (safe_r_A * 0.3))
                    
            total_loss = local_loss
            if i < damp_A_cov:
                total_loss += damp_A_val
                
            p_A_future[i, j] = (2.0 * p_A[i, j] - p_A_past[i, j] * (1.0 - total_loss) + force) / (1.0 + total_loss)
        else:
            p_A_future[i, j] = 0.0

    # --- РАСЧЕТ ДЛЯ ЗВОНКОЙ МЕМБРАНЫ (B) ---
    for i, j in ti.ndrange(N, N):
        if i > 0 and i < N-1 and j > 0 and j < N-1 and mask_B[i, j] > 0.5:
            # Читаем локальные свойства из пространственных карт
            base_cx = c_sq_x_B_field[i, j]
            base_cy = c_sq_y_B_field[i, j]
            local_loss = loss_B_field[i, j]
            local_visco = visco_B_field[i, j]
            
            dyn_c_x_B = ti.min(base_cx * (1.0 + bend_B * strain_B * 8000.0), 0.40)
            dyn_c_y_B = ti.min(base_cy * (1.0 + bend_B * strain_B * 8000.0), 0.40)

            lap_curr_x = p_B[i-1, j] + p_B[i+1, j] - 2.0 * p_B[i, j]
            lap_curr_y = p_B[i, j-1] + p_B[i, j+1] - 2.0 * p_B[i, j]
            lap_past_x = p_B_past[i-1, j] + p_B_past[i+1, j] - 2.0 * p_B_past[i, j]
            lap_past_y = p_B_past[i, j-1] + p_B_past[i, j+1] - 2.0 * p_B_past[i, j]
            
            lap_curr = dyn_c_x_B * lap_curr_x + dyn_c_y_B * lap_curr_y
            lap_past = dyn_c_x_B * lap_past_x + dyn_c_y_B * lap_past_y
            
            force = lap_curr + local_visco * (lap_curr - lap_past)
            force += p_air_B * mask_B[i, j]

            if radius_B > 0.1:
                dist = ti.cast((i - strike_x_B)**2 + (j - strike_y_B)**2, ti.f32)
                if dist < radius_B:
                    force += strike_val_B * ti.exp(-dist / (safe_r_B * 0.3))
                    
            total_loss = local_loss
            if i < damp_B_cov:
                total_loss += damp_B_val
                
            p_B_future[i, j] = (2.0 * p_B[i, j] - p_B_past[i, j] * (1.0 - total_loss) + force) / (1.0 + total_loss)
        else:
            p_B_future[i, j] = 0.0

@ti.kernel
def apply_dhol_tactile_forces(
    N: ti.i32, gran: ti.f32, brit: ti.f32, strike_force: ti.f32,
    slap_fric_A: ti.f32, slap_fric_B: ti.f32,
    strike_x_A: ti.i32, strike_y_A: ti.i32,
    strike_x_B: ti.i32, strike_y_B: ti.i32,
    r_strike_A: ti.f32, r_strike_B: ti.f32
):
    # --- 1. Стандартные случайные тактильные силы материала ---
    limit = 75 + ti.cast(strike_force * 100.0, ti.i32)
    for idx in range(180):
        if idx < limit:
            i_A = ti.cast(ti.random() * N, ti.i32)
            j_A = ti.cast(ti.random() * N, ti.i32)
            if i_A > 0 and i_A < N-1 and j_A > 0 and j_A < N-1 and mask_A[i_A, j_A] > 0.5:
                strain_A = ti.abs(p_A[i_A, j_A] - p_A_past[i_A, j_A])
                if gran > 0.0 and strain_A > 0.00001:
                    if ti.random() < gran: 
                        p_A_future[i_A, j_A] += (ti.random() - 0.5) * gran * strain_A * 0.3
                if brit > 0.0 and strain_A > 0.002:
                    if ti.random() < brit * 0.1: 
                        p_A_future[i_A, j_A] += (ti.random() - 0.5) * brit * strain_A * 1.5
                        p_A_future[i_A, j_A] *= 0.90 

            i_B = ti.cast(ti.random() * N, ti.i32)
            j_B = ti.cast(ti.random() * N, ti.i32)
            if i_B > 0 and i_B < N-1 and j_B > 0 and j_B < N-1 and mask_B[i_B, j_B] > 0.5:
                strain_B = ti.abs(p_B[i_B, j_B] - p_B_past[i_B, j_B])
                if gran > 0.0 and strain_B > 0.00001:
                    if ti.random() < gran: 
                        p_B_future[i_B, j_B] += (ti.random() - 0.5) * gran * strain_B * 0.3
                if brit > 0.0 and strain_B > 0.002:
                    if ti.random() < brit * 0.1:
                        p_B_future[i_B, j_B] += (ti.random() - 0.5) * brit * strain_B * 1.5
                        p_B_future[i_B, j_B] *= 0.90

    # --- 2. [NEW] ФИЗИЧЕСКОЕ ТРЕНИЕ ЛАДОНИ (ШППП) СТРОГО В ЗОНЕ УДАРА ---
    if slap_fric_A > 0.0 and r_strike_A > 0.1:
        # Внедряем хаотические микро-сдвиги в пределах радиуса соприкосновения ладони
        # Это физически возбуждает высокочастотный треск "ШППП" прямо внутри сетки!
        for idx in range(120):
            i_A = ti.cast(ti.random() * N, ti.i32)
            j_A = ti.cast(ti.random() * N, ti.i32)
            if i_A > 0 and i_A < N-1 and j_A > 0 and j_A < N-1 and mask_A[i_A, j_A] > 0.5:
                dist = ti.cast((i_A - strike_x_A)**2 + (j_A - strike_y_A)**2, ti.f32)
                if dist < r_strike_A**2:
                    p_A_future[i_A, j_A] += (ti.random() - 0.5) * slap_fric_A * 0.035

    if slap_fric_B > 0.0 and r_strike_B > 0.1:
        for idx in range(120):
            i_B = ti.cast(ti.random() * N, ti.i32)
            j_B = ti.cast(ti.random() * N, ti.i32)
            if i_B > 0 and i_B < N-1 and j_B > 0 and j_B < N-1 and mask_B[i_B, j_B] > 0.5:
                dist = ti.cast((i_B - strike_x_B)**2 + (j_B - strike_y_B)**2, ti.f32)
                if dist < r_strike_B**2:
                    p_B_future[i_B, j_B] += (ti.random() - 0.5) * slap_fric_B * 0.035

@ti.kernel
def update_dhol_fields(N: ti.i32):
    for i, j in ti.ndrange(N, N):
        p_A_past[i, j] = p_A[i, j]
        p_A[i, j] = p_A_future[i, j]
        p_B_past[i, j] = p_B[i, j]
        p_B[i, j] = p_B_future[i, j]

def apply_acoustic_shell(membrane_signal, fs, mat_properties, note_hz, articulation, strike_force=1.0, autotune_shell=False, ring_mod=0.0, body_damping=0.0):
    E_long = mat_properties.get("E_long", 10.0)
    density = mat_properties.get("density", 0.5)
    loss_mat = max(0.0001, mat_properties.get("loss_factor", 0.02))
    thickness = mat_properties.get("base_thickness", 0.004)
    
    # 1. Физическая скорость звука в материале стенки
    v_sound = np.sqrt((E_long * 1e9) / (density * 1000.0))
    f_helmholtz = np.clip(note_hz * 1.0, 40.0, 150.0)
    
    # Зависимость изгибных мод кадушки от толщины стенки h
    base_shell = np.clip(v_sound * 0.05 * ((thickness / 0.004) ** 0.3), 150.0, 4500.0)
    if autotune_shell and note_hz > 0:
        ratio = base_shell / note_hz
        consonant_multipliers = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]
        best_mult = min(consonant_multipliers, key=lambda x: abs(x - ratio))
        base_shell = note_hz * best_mult
    
    freqs = [f_helmholtz, base_shell, base_shell * 1.61, base_shell * 2.3, base_shell * 3.5, base_shell * 5.4, base_shell * 8.1]
    
    # 2. Модель стыковых потерь Лютье (Boundary-Loss Model)
    # Потери на стыках и креплениях прижимного обода (типичное значение 0.015)
    eta_boundary = 0.015
    
    # С ростом ring_mod лютье сводит внешние потери к нулю, стремясь к идеальной развязке
    total_loss = loss_mat + eta_boundary * (1.0 - ring_mod)
    
    dynamic_q_scale = 0.76 + 0.24 * (strike_force ** 0.5)
    
    # Базовое значение Q, жестко ограниченное общими потерями системы
    base_q = (0.85 / total_loss) * dynamic_q_scale
    
    q_helmholtz = np.clip(base_q * 2.2, 30.0, 110.0)
    q_factors = [q_helmholtz, base_q, base_q * 1.1, base_q * 1.3, base_q * 1.5, base_q * 1.8, base_q * 2.0]
    
    # Дополнительная коррекция добротности для ярких артикуляций стороны B
    if ring_mod > 0 and articulation in ["tek_A", "tek_B"]:
        boost_mult = 1.5
        q_factors[1] *= (1.0 + ring_mod * boost_mult)
        q_factors[2] *= (1.0 + ring_mod * boost_mult)
    
    # 3. Эффективность излучения звука (Radiation Efficiency) жестких кадушек
    radiation_efficiency = np.sqrt(E_long / density)
    shell_gain = 0.08 * (radiation_efficiency ** 0.25)
    
    # Инициализация списка gains (переменная теперь гарантированно объявлена до использования!)
    gains = [0.35, shell_gain, shell_gain * 0.7, shell_gain * 0.5, shell_gain * 0.3, shell_gain * 0.15, shell_gain * 0.08]
    
    # Корректировка усиления под артикуляции
    if articulation == "tek_A":
        q_factors[1] *= 1.2
        q_factors[2] *= 1.4
        gains[0] *= 0.65 
        gains[1] *= 0.85 
    elif articulation == "tek_B":
        q_factors[1] *= 1.2
        q_factors[2] *= 1.3
        gains[0] *= 0.35 
        gains[1] *= 0.75 
        gains[2] *= 0.70 
    elif articulation == "chapa":
        gains[0] *= 0.65      
        q_factors[0] *= 0.25  
        q_factors[1] *= 1.5
        q_factors[2] *= 1.2
        gains[1] *= 1.60  
        gains[2] *= 1.40  
        gains[3] *= 1.50  
        q_factors[3] *= 1.30
    elif articulation == "clap_tek":
        gains[0] *= 0.15
        gains[1] *= 1.0
    elif articulation == "open_bass":
        gains[0] *= 1.4
    elif articulation == "duum":
        gains[0] *= 1.1
        gains[1] *= 1.2
    elif articulation == "mute":
        gains[0] *= 0.25      
        q_factors[0] *= 0.35  
        gains[1] *= 0.40      
    elif articulation == "kopal":
        gains[0] *= 0.15       
        q_factors[0] *= 0.40   
        gains[1] *= 1.5        
        gains[2] *= 1.3
    elif articulation == "tchipot":
        gains[0] *= 0.10
        q_factors[0] *= 0.30
        gains[1] *= 1.2
    elif articulation == "wood_click":
        gains[0] = 0.0  
        gains[1] *= 1.6 
        gains[2] *= 1.5
        gains[3] *= 1.4
        gains[4] *= 1.4
        gains[5] *= 2.5 
        gains[6] *= 3.0 
        
    shell_output = np.zeros_like(membrane_signal)
    
    for f, q, g in zip(freqs, q_factors, gains):
        if f < fs / 2.1:
            w0 = 2.0 * np.pi * f / fs
            alpha = np.sin(w0) / (2.0 * q)
            a0 = 1.0 + alpha
            b = [np.sin(w0) / (2.0 * a0), 0.0, -np.sin(w0) / (2.0 * a0)]
            a = [1.0, -2.0 * np.cos(w0) / a0, (1.0 - alpha) / a0]
            shell_output += lfilter(b, a, membrane_signal) * g
            
    # Динамическое демпфирование корпуса телом (ADSR-огибающая поглощения)
    if body_damping > 0.0:
        t_arr = np.arange(len(shell_output)) / fs
        tail_tau = np.clip(1.5 * np.exp(-body_damping * 3.5), 0.06, 1.5)
        tail_env = np.exp(-t_arr / tail_tau)
        
        attack_time = 0.012
        attack_env = np.clip(t_arr / attack_time, 0.0, 1.0)
        
        damping_env = (1.0 - attack_env) + attack_env * tail_env
        shell_output *= damping_env
        
    return shell_output

def apply_meat_and_fat(sig, fs, articulation, strike_force, saturation=0.0, skin_mat=None, shell_mat=None, shell_attack=0.5, shell_sustain=1.0, membrane_snap=1.0):
    out = sig.copy()
    
    # Инициализируем переменные для тактильного профиля кадушки
    shell_vel = np.zeros_like(sig)
    shell_accel = np.zeros_like(sig)
    shell_stress = np.zeros_like(sig)
    
    t_arr = np.arange(len(out)) / fs
    # Значительно усиливаем атаку (Punch) для возвращения характерного "шлепка"
    punch_env = 1.0 + 0.45 * np.exp(-t_arr / 0.012) * strike_force
    out *= punch_env
    
    # Фазовая дисперсия (Allpass) на выходе. Для chapa отключаем, чтобы не было фазовой грязи.
    if articulation != "chapa":
        if articulation in ["tek_A", "tek_B", "kopal", "tchipot", "wood_click", "clap_tek"]:
            disp_stages = 2
            c = -0.15
        else: 
            disp_stages = 2
            c = -0.65
            
        for _ in range(disp_stages):
            out = lfilter([c, 1.0], [1.0, c], out)
            
    if articulation == "wood_click":
        room_mix = 0.0
    else:
        room_mix = 0.12 if articulation in ["tek_A", "tek_B"] else (0.02 if articulation == "mute" else 0.15)
        
    if articulation != "chapa":
        delay_samples = int(0.028 * fs)
        room = np.zeros_like(out)
        if len(out) > delay_samples:
            room[delay_samples:] += out[:-delay_samples] * (room_mix * 0.7)
            
        b_r, a_r = butter(1, 4000.0 / (fs/2.0), btype='low')
        out += lfilter(b_r, a_r, room)
    
    E_skin = skin_mat.get("E_long", 1.5) if skin_mat else 1.5
    den_skin = skin_mat.get("density", 1.0) if skin_mat else 1.0
    loss_skin = skin_mat.get("loss_factor", 0.05) if skin_mat else 0.05
    
    E_shell = shell_mat.get("E_long", 11.2) if shell_mat else 11.2
    den_shell = shell_mat.get("density", 0.64) if shell_mat else 0.64
    loss_shell = shell_mat.get("loss_factor", 0.018) if shell_mat else 0.018
    
    if articulation == "wood_click":
        E_eff, den_eff, loss_eff = E_shell, den_shell, loss_shell
    else:
        E_eff = (E_skin * 0.75) + (E_shell * 0.25)
        den_eff = (den_skin * 0.75) + (den_shell * 0.25)
        loss_eff = (loss_skin * 0.75) + (loss_shell * 0.25)
    
    v_sound = np.sqrt(max(E_eff, 0.01) / max(den_eff, 0.1))
    click_freq = 600.0 + 450.0 * (v_sound ** 1.5)
    click_freq = np.clip(click_freq, 600.0, 12000.0)
    
    # КРИТИЧЕСКИЙ ФИКС: Ослабляем коэффициент демпфирования верхних частот клика.
    # Ранее при -35.0 частота среза щелчка падала до 3кГц, делая TEK абсолютно глухим.
    # При -12.0 она остается на уровне 9.5 - 11.5 кГц, сохраняя яркий хруст козьей кожи!
    damp_freq = 20000.0 * np.exp(-12.0 * loss_eff)
    damp_freq = np.clip(damp_freq, click_freq + 1500.0, fs/2.1)
    
    b_hi, a_hi = butter(2, click_freq / (fs/2.0), btype='high')
    hi_layer = lfilter(b_hi, a_hi, sig)
    
    b_damp, a_damp = butter(1, damp_freq / (fs/2.0), btype='low')
    hi_layer = lfilter(b_damp, a_damp, hi_layer)

    if shell_mat:
        shell_texture = apply_dynamic_shell_texture(
            shell_mat, fs, len(out), strike_force, saturation, articulation
        )

        # Значительно повышаем микс "вкусной" текстуры дерева (Shell Engine)
        if articulation == "wood_click":
            tex_mix = 0.85
        elif articulation in ["kopal", "tchipot", "clap_tek"]:
            tex_mix = 0.55
        elif articulation == "mute":
            tex_mix = 0.20
        elif articulation in ["tek_A", "tek_B"]:
            tex_mix = 0.50  # Яркий деревянный тон для Тэка
        else:
            tex_mix = 0.35
            
        tex_mix *= (0.5 + 0.5 * (strike_force ** 1.5))
        tex_mix *= (1.0 + saturation * 1.0)
        
        # Раздельное насыщение атаки и сустейна для Shell Engine
        t_tex = np.arange(len(shell_texture)) / fs
        env_attack = np.exp(-t_tex / 0.04) # 40ms attack window
        env_sustain = 1.0 - env_attack
        
        shell_env = (env_attack * shell_attack) + (env_sustain * shell_sustain)
        
        out += shell_texture * tex_mix * shell_env

    headroom = 0.4
    saturation_drive = 1.0 + (saturation * 0.15)
    out = np.tanh(out * headroom * saturation_drive) / (headroom * saturation_drive)
    
    if articulation in ["tek_A", "tek_B"]:
        click_decay = 0.25
        snap_boost = 1.0
    elif articulation == "chapa":
        click_decay = 0.38
        snap_boost = 6.0
    else:
        click_decay = 0.04
        snap_boost = 1.0
        
    click_env = np.exp(-t_arr / click_decay) 
    out += hi_layer * click_env * (0.15 + membrane_snap * 0.35) * snap_boost * (strike_force ** 2.0)
    
    return out

def apply_3d_studio_room(mono_signal, fs):
    room_dim = [5.0, 6.0, 3.0]
    mat = pra.Material(0.45, 0.1)
    room = pra.ShoeBox(room_dim, fs=fs, materials=mat, max_order=8)
    source_pos = [2.5, 2.0, 0.8]
    room.add_source(source_pos, signal=mono_signal)
    
    mic_array = np.array([
        [source_pos[0] - 0.23, source_pos[1] + 1.48, 1.45],
        [source_pos[0] + 0.17, source_pos[1] + 1.52, 1.55]
    ])
    room.add_microphone_array(mic_array.T)
    room.simulate()
    stereo_room = room.mic_array.signals.T
    if len(stereo_room) > len(mono_signal):
        stereo_room = stereo_room[:len(mono_signal)]
    else:
        stereo_room = np.pad(stereo_room, ((0, len(mono_signal) - len(stereo_room)), (0, 0)))
    return stereo_room

def declick_ar_model(sig, fs, ms_window=5.0, slew_factor=2.5, cutoff_hz=8500.0):
    """
    Адаптивный полосовой декрикер (slew-rate лимитер огибающей).
    Изолирует спектр выше cutoff_hz, вычисляет естественную скорость изменения 
    сигнала в окне ms_window (5 мс) и мягко лимитирует любые резкие физические 
    разрывы моделирования, переводя треск в естественный шелест кожи.
    """
    from scipy.ndimage import uniform_filter1d
    from scipy.signal import butter, lfilter
    
    n_samples = len(sig)
    nyquist = fs / 2.0
    
    # 1. Защищаем тело звука: изолируем только ультра-ВЧ спектр треска
    b, a = butter(2, cutoff_hz / nyquist, btype='high')
    hf = lfilter(b, a, sig)
    lf = sig - hf  # 100% тела звука ниже 8.5 кГц остается нетронутым
    
    # 2. Вычисляем физическую скорость изменения (Slew Rate) на каждом сэмпле
    dy = np.diff(hf)
    dy = np.concatenate(([0.0], dy))
    
    # Количество сэмплов в окне 5 мс (при 44.1 кГц это ~220 сэмплов)
    window_samples = max(5, int((ms_window / 1000.0) * fs))
    
    # Находим скользящую огибающую естественной скорости изменения ВЧ-сигнала
    smooth_env = uniform_filter1d(np.abs(dy), size=window_samples)
    
    # Устанавливаем динамический предел скорости: 
    # Естественный шум меняется плавно, физический щелчок дает взрывной скачок.
    max_slew = np.clip(slew_factor * smooth_env, 0.0005, 1.0)
    
    # 3. Применяем динамическое ограничение скорости нарастания (Slew Rate Limiting)
    cleaned_hf = hf.copy()
    for i in range(1, n_samples):
        step = cleaned_hf[i] - cleaned_hf[i-1]
        limit = max_slew[i]
        
        if np.abs(step) > limit:
            cleaned_hf[i] = cleaned_hf[i-1] + np.sign(step) * limit
            
    # Возвращаем очищенный спектр, объединенный с оригинальным телом звука
    return lf + cleaned_hf, {"total_clicks": 1, "frames_with_clicks": 1}

def generate_air_column_ir(base_shell_hz, fs=44100, duration=0.4, articulation="duum", body_damping=0.0):
    """
    Генерирует акустический отклик воздушного столба внутри кадушки.
    Динамически удлиняет воздушный сустейн для артикуляции chapa.
    """
    t_arr = np.arange(int(fs * duration)) / fs
    air_ir = np.zeros_like(t_arr)
    
    # Резонансные частоты воздуха
    freqs = [base_shell_hz, base_shell_hz * 2.0, base_shell_hz * 3.0]
    
# 1. НАСТРОЙКА ВОЗДУШНОГО СПАДА ПОД АРТИКУЛЯЦИЮ
    if articulation == "chapa":
        decay_times = [0.100, 0.045, 0.020]
        amplitudes = [1.0, 0.55, 0.25]
    else:
        decay_times = [0.045, 0.018, 0.008]
        amplitudes = [1.0, 0.45, 0.20]
        
    # [NEW] Воздух также гасится, если тело закрывает кадушку
    decay_times = [tau / (1.0 + body_damping * 3.0) for tau in decay_times]
    
    for f, tau, amp in zip(freqs, decay_times, amplitudes):
        if f < fs / 2.1:
            phase = np.random.uniform(0, 2 * np.pi)
            decay = np.exp(-t_arr / tau)
            air_ir += amp * decay * np.sin(2 * np.pi * f * t_arr + phase)
            
    # Добавляем ранние воздушные отражения внутри кадушки
    reflections = [int(0.0015 * fs), int(0.0030 * fs), int(0.0045 * fs)]
    ref_gains = [0.35, 0.18, 0.08]
    
    for delay, gain in zip(reflections, ref_gains):
        if len(air_ir) > delay:
            air_ir[delay:] += air_ir[:-delay] * gain
            
    # Мягкий фильтр воздушного трения
    b, a = butter(2, 7500.0 / (fs / 2.0), btype='low')
    air_ir = lfilter(b, a, air_ir)
    
    if np.max(np.abs(air_ir)) > 0:
        air_ir /= np.max(np.abs(air_ir))
        
    return air_ir

_BODY_IR_CACHE = {}

def generate_body_ir(shell_mat_dict, base_shell_hz, fs=44100, duration=0.4, articulation="duum", body_damping=0.0):
    """
    Генерирует гибридный IR. 
    Добавлена жесткая синхронизация длины массивов для исключения ошибок округления.
    """
    ir_instrument = PERCUSSION_PRESETS["tom_low"].copy()
    ir_instrument['f0'] = base_shell_hz  
    
    exciter_impulse = np.zeros(int(fs * duration))
    
    # 1. ТЮНИНГ ВОЗБУДИТЕЛЯ
    if articulation == "chapa":
        pulse_len = int(0.0025 * fs)
        dirac_gain = 0.60
        noise_gain = 0.40
        cutoff_hz = 1400.0
    else:
        pulse_len = int(0.0015 * fs)
        dirac_gain = 0.70
        noise_gain = 0.30
        cutoff_hz = 800.0
        
    noise = np.random.normal(0, 1.0, pulse_len)
    env = (1.0 - np.linspace(0, 1, pulse_len)) ** 2
    b, a = butter(2, cutoff_hz / (fs / 2.0), btype='high')
    filtered_noise = lfilter(b, a, noise * env)
    
    if np.max(np.abs(filtered_noise)) > 0:
        filtered_noise /= np.max(np.abs(filtered_noise))
        
    exciter_impulse[0] = dirac_gain
    exciter_impulse[:pulse_len] += filtered_noise * noise_gain
    exciter_impulse /= np.max(np.abs(exciter_impulse))

    # 2. ПОЛУЧАЕМ ИМПУЛЬС ДЕРЕВА
    body_ir_stereo = generate_fdtd_ir(
        inst_dict=ir_instrument,
        mat_dict=shell_mat_dict,
        sample_rate=fs,
        duration=duration,
        exciter_signal=exciter_impulse,
        is_stereo=False,
        strike_force=1.0,
        N_grid=128,
        show_gui=False
    )
    
    body_ir_mono = (body_ir_stereo[:, 0] + body_ir_stereo[:, 1]) * 0.5
    if np.max(np.abs(body_ir_mono)) > 0:
        body_ir_mono /= np.max(np.abs(body_ir_mono))
        
    # 3. ПОДГОТОВКА ВОЗДУХА
    target_len = len(body_ir_mono) # Запоминаем точное кол-во сэмплов
    actual_duration = target_len / fs
    
    air_ir = generate_air_column_ir(base_shell_hz, fs, actual_duration, articulation=articulation, body_damping=body_damping)
    
    # --- КРИТИЧЕСКИЙ ФИКС: Жесткое выравнивание длины ---
    if len(air_ir) > target_len:
        air_ir = air_ir[:target_len]
    elif len(air_ir) < target_len:
        air_ir = np.pad(air_ir, (0, target_len - len(air_ir)))
    # ---------------------------------------------------
    
    # 4. СМЕШИВАЕМ (теперь ошибки не будет)
    mixed_ir = 0.4 * body_ir_mono + 0.6 * air_ir
    
    if np.max(np.abs(mixed_ir)) > 0:
        mixed_ir /= np.max(np.abs(mixed_ir))
        
    return mixed_ir

def apply_body_convolution(input_signal, ir_signal, fs, mix=0.35):
    if mix == 0.0:
        return input_signal
    nyquist = fs / 2.0
    cutoff_hz = 900.0
    b, a = butter(4, cutoff_hz / nyquist, btype='high')
    ir_highpass = lfilter(b, a, ir_signal)
    ir_len = int(0.15 * fs)
    if len(ir_highpass) > ir_len:
        ir_faded = ir_highpass[:ir_len]
        ir_faded *= (np.linspace(1.0, 0.0, ir_len)**2)
    else:
        ir_faded = ir_highpass
    if np.max(np.abs(ir_faded)) > 0:
        ir_faded /= np.max(np.abs(ir_faded))
    wet_signal = fftconvolve(input_signal, ir_faded, mode='full')
    wet_signal = wet_signal[:len(input_signal)]
    if np.max(np.abs(wet_signal)) > 0:
        wet_signal *= np.max(np.abs(input_signal)) / np.max(np.abs(wet_signal))
    output = input_signal * (1.0 - mix) + wet_signal * mix
    return output

def apply_internal_bells(membrane_signal, acceleration_signal, fs, material_name="brass", 
                         mix=0.15, rr_index=1, strike_force=1.0, bell_peak_ratio=1.0, ring_mod=0.0):
    """
    МАКСИМАЛЬНО ЖИВАЯ МОДЕЛЬ КОЛОКОЛЬЧИКОВ.
    Сбалансированная: жесткий transient-gate защищает атаку «Тэка», 
    а сдвинутые вверх фильтры HPF предотвращают эффект тамбурина.

    bell_peak_ratio : float
        Максимально допустимое отношение пиковой амплитуды колокольчиков к пиковой амплитуде тела.
        1.0 = колокольчики не превышают уровень основного сигнала.
    """
    from config.materials import MATERIAL_PHYSICS
    
    # --- 1. КИНЕМАТИКА И ЭНЕРГИЯ ---
    # Линейно ослабляем общую громкость колокольчиков на 55% (умножаем на 0.45)
    # Это предотвращает перегрузку атаки и сохраняет энергию барабана.
    acoustic_mix = (mix ** 1.8) * 0.45 
    
    kinetic_energy = strike_force ** 1.5 
    global_energy = np.clip(acoustic_mix * kinetic_energy, 0.001, 1.0)
    
    # RR-Синхронизированный генератор
    seed = int(hash(material_name) % 10000) + int(rr_index * 997) + int(strike_force * 100)
    rng = np.random.RandomState(seed)
    
    # Физика материала
    mat = MATERIAL_PHYSICS.get(material_name, MATERIAL_PHYSICS.get("steel", {}))
    E = float(mat.get("E_long", 200.0))
    rho = float(mat.get("density", 7.8))
    loss = float(mat.get("loss_factor", 0.0005))
    
    f0 = 1400.0 * np.sqrt(max(0.1, E) / max(0.1, rho))
    f0 = np.clip(f0, 2000.0, 7500.0) 
    
    num_samples = len(membrane_signal)
    hit_idx = int(np.argmax(np.abs(acceleration_signal))) if np.max(np.abs(acceleration_signal)) > 0 else 0
    t_decay = np.maximum(0, np.arange(num_samples) - hit_idx) / fs
    
    # --- СЛОЙ 1: ОСНОВНЫЕ КОЛОКОЛА (4 крупных объекта) ---
    base_freqs = [f0, f0 * 1.48, f0 * 2.12, f0 * 2.95]
    gains = [1.0, 
             0.75 * (kinetic_energy ** 0.3), 
             0.45 * (kinetic_energy ** 0.5), 
             0.20 * (kinetic_energy ** 0.8)]
    
    base_q = 0.5 / max(1e-5, loss)
    
    # [ПРАВКА] Взаимодействие бубенцов с резонансом кадушки (Luthier Ring)
    # Если корпус настроен петь (высокий ring_mod), внутренние бубенцы резонируют дольше
    luthier_bell_boost = 1.0 + (ring_mod * 2.5 * (0.02 / loss) ** 0.2)
    sustain_scale = (0.15 + 0.85 * kinetic_energy) * (0.3 + 0.7 * mix) * luthier_bell_boost
    q_bell = np.clip(base_q * sustain_scale, 5.0, 600.0) # Повышен лимит добротности для металла
    
    abs_acc = np.abs(acceleration_signal)
    main_excitation = np.zeros_like(abs_acc)
    threshold = 0.0003 * np.sqrt(rho)
    active_mask = abs_acc > threshold
    main_excitation[active_mask] = abs_acc[active_mask] - threshold
    
    bounce_decay_time = 0.05 + 0.35 * (strike_force * mix)
    bounce_env = np.exp(-t_decay / bounce_decay_time) * kinetic_energy

    bell_output = np.zeros(num_samples)
    num_bells = 4 
    
    for bell_idx in range(num_bells):
        detune = rng.uniform(0.95, 1.05)
        bounce_prob = rng.rand(num_samples)
        sparsity = rng.uniform(0.0005, 0.002) 
        bounce_triggers = (bounce_prob < (sparsity * bounce_env)).astype(np.float32)
        bounce_amps = rng.uniform(0.1, 0.9, num_samples) * bounce_triggers * bounce_env
        
        bell_exc = (main_excitation + bounce_amps) * rng.normal(0.4, 0.6, num_samples)
        
        bell_layer = np.zeros(num_samples)
        for f, g in zip(base_freqs, gains):
            f_det = f * detune
            if f_det < fs / 2.1:
                w0 = 2.0 * np.pi * f_det / fs
                alpha = np.sin(w0) / (2.0 * q_bell * rng.uniform(0.8, 1.2))
                a0 = 1.0 + alpha
                b = [np.sin(w0) / (2.0 * a0), 0.0, -np.sin(w0) / (2.0 * a0)]
                a = [1.0, -2.0 * np.cos(w0) / a0, (1.0 - alpha) / a0]
                bell_layer += lfilter(b, a, bell_exc) * g
                
        delay_samples = int(rng.uniform(0.0, 0.008) * fs)
        if delay_samples > 0:
            bell_layer = np.roll(bell_layer, delay_samples)
            bell_layer[:delay_samples] = 0
            
        bell_output += bell_layer * (1.0 / num_bells)

    # --- СЛОЙ 2: МИКРО-ДИСПЕРСНЫЕ БУБЕНЦЫ (12 мелких объектов) ---
    micro_threshold = 0.00012 * np.sqrt(rho)
    micro_excitation = np.zeros_like(abs_acc)
    micro_active_mask = abs_acc > micro_threshold
    micro_excitation[micro_active_mask] = abs_acc[micro_active_mask] - micro_threshold

    micro_bounce_decay = 0.03 + 0.18 * (strike_force * mix)
    micro_bounce_env = np.exp(-t_decay / micro_bounce_decay) * kinetic_energy

    q_micro = np.clip(base_q * 0.12 * (0.4 + 0.6 * mix), 4.0, 45.0)
    
    micro_bell_output = np.zeros(num_samples)
    num_micro_bells = 12 

    for m_idx in range(num_micro_bells):
        micro_detune = rng.uniform(1.65, 2.75)
        f_micro = f0 * micro_detune
        
        micro_prob = rng.rand(num_samples)
        micro_triggers = (micro_prob < (0.004 * micro_bounce_env)).astype(np.float32)
        micro_amps = rng.uniform(0.05, 0.35, num_samples) * micro_triggers * micro_bounce_env
        
        micro_exc = (micro_excitation * 0.4 + micro_amps) * rng.normal(0.4, 0.6, num_samples)
        
        if f_micro < fs / 2.1:
            w0 = 2.0 * np.pi * f_micro / fs
            alpha = np.sin(w0) / (2.0 * q_micro)
            a0 = 1.0 + alpha
            b = [np.sin(w0) / (2.0 * a0), 0.0, -np.sin(w0) / (2.0 * a0)]
            a = [1.0, -2.0 * np.cos(w0) / a0, (1.0 - alpha) / a0]
            
            micro_layer = lfilter(b, a, micro_exc)
            
            delay_samples = int(rng.uniform(0.003, 0.018) * fs)
            if delay_samples > 0:
                micro_layer = np.roll(micro_layer, delay_samples)
                micro_layer[:delay_samples] = 0
                
            micro_bell_output += micro_layer

    # --- СВЕДЕНИЕ И ПОСТ-ОБРАБОТКА СЛОЁВ ---
    nyquist = fs / 2.0

    # 1. Спектральная чистка основных колоколов (СДВИГ HPF ВВЕРХ с 1800 до 2500 Гц)
    b_hp, a_hp = butter(2, 2500.0 / nyquist, btype='high')
    bell_output = lfilter(b_hp, a_hp, bell_output)

    lp_cutoff = 2200.0 + 15000.0 * (kinetic_energy ** 0.8) * (0.4 + 0.6 * mix)
    lp_cutoff = np.clip(lp_cutoff, 2000.0, nyquist - 200.0)
    b_lp, a_lp = butter(2, lp_cutoff / nyquist, btype='low')
    bell_output = lfilter(b_lp, a_lp, bell_output)

    # 2. Спектральная чистка микро-колоколов (СДВИГ HPF ВВЕРХ с 3800 до 5000 Гц)
    b_hp_m, a_hp_m = butter(2, 5000.0 / nyquist, btype='high')
    micro_bell_output = lfilter(b_hp_m, a_hp_m, micro_bell_output)

    b_lp_m, a_lp_m = butter(2, 7500.0 / nyquist, btype='low')
    micro_bell_output = lfilter(b_lp_m, a_lp_m, micro_bell_output)

    # 3. Нормализация и сложение слоев
    max_main = np.max(np.abs(bell_output))
    if max_main > 0:
        bell_output /= max_main
        
    max_micro = np.max(np.abs(micro_bell_output))
    if max_micro > 0:
        micro_bell_output = (micro_bell_output / max_micro) * 0.18
        
    combined_bells = bell_output * 0.82 + micro_bell_output * 0.18

    # --- НОВЫЙ БЛОК: АДАПТИВНЫЙ ПИКОВЫЙ ЛИМИТЕР ДЛЯ КОЛОКОЛЬЧИКОВ ---
    # Вычисляем пиковое значение тела (входного сигнала)
    body_peak = np.max(np.abs(membrane_signal))
    if body_peak > 1e-6:
        # Порог, выше которого колокольчикам запрещено подниматься
        limit_threshold = body_peak * bell_peak_ratio
        
        # Применяем мягкое насыщение (soft-clip) к combined_bells,
        # чтобы их амплитуда не выходила за limit_threshold
        # Используем tanh – он сохраняет форму сигнала, но плавно ограничивает пики
        combined_bells = np.tanh(combined_bells / limit_threshold) * limit_threshold
    
    # 4. АБСОЛЮТНЫЙ TRANSIENT-GATE (Колокольчики гасятся на 100% на пике атаки барабана)
    dry_env = lfilter([0.05], [1.0, -0.95], np.abs(membrane_signal))
    max_env = np.max(dry_env) + 1e-9
    # Применяем жесткое ограничение: если огибающая > 0.7, дакинг становится полным (0.0)
    duck_factor = np.clip(1.0 - (dry_env / max_env) * 1.4, 0.0, 1.0)
    combined_bells *= duck_factor
    
    # 5. Плавный Fade-Out (увод хвостов)
    fade_len = min(int(fs * 0.35), num_samples // 3)
    if fade_len > 0:
        fade_curve = np.linspace(1.0, 0.0, fade_len) ** 2
        combined_bells[-fade_len:] *= fade_curve
    
    # Защита от клиппинга
    max_total = np.max(np.abs(combined_bells))
    if max_total > 0:
        combined_bells /= max_total
        combined_bells *= np.clip(np.max(main_excitation) * 3.5, 0.0, 1.0)
        
    return membrane_signal + combined_bells * acoustic_mix
def synthesize_dhol_strike(
    freq_A, freq_B, 
    articulation="duum", strike_force=1.0, 
    skin_mat_name="animal_skin", shell_mat_name="walnut",
    duration=1.5, fs=44100, 
    yield_cb=None,
    saturation=0.0,
    mat_boost=0.0,
    membrane_tactile=1.0,
    membrane_snap=1.0,
    shell_attack=0.5,
    shell_sustain=1.0,
    show_gui=False,
    N_grid=256,
    rr_index=1,
    autotune_shell=False,
    ring_mod=0.0,
    body_polish_mix=0.35,
    use_bells=False,
    bell_material="steel",
    bell_mix=0.15,
    body_damping=0.25
):
    init_taichi_headless()
    if show_gui and os.environ.get('DISPLAY') is None:
        print("⚠️ DISPLAY environment not found, forcing headless mode and disabling GUI.")
        show_gui = False

    N_grid = min(N_grid, N_MAX)
    init_dhol_fields(N_grid)
    
    skin_mat_raw = MATERIAL_PHYSICS.get(skin_mat_name, MATERIAL_PHYSICS["animal_skin"])
    shell_mat_raw = MATERIAL_PHYSICS.get(shell_mat_name, MATERIAL_PHYSICS["walnut"])
    
    skin_mat = get_effective_properties(skin_mat_raw)
    shell_mat = get_effective_properties(shell_mat_raw)

    if rr_index > 1:
        state = np.random.RandomState(int(rr_index * 137 + strike_force * 997))
        force_mod = state.uniform(-0.04, 0.04)
        strike_force = np.clip(strike_force + force_mod, 0.05, 1.0)

    r_mask = np.zeros((N_MAX, N_MAX), dtype=np.float32)
    radius_pixels = 0.4375 * N_grid
    center = N_grid / 2.0
    for i in range(N_grid):
        for j in range(N_grid):
            if (i - center)**2 + (j - center)**2 < radius_pixels**2:
                r_mask[i, j] = 1.0
                
    mask_A.from_numpy(r_mask)
    mask_B.from_numpy(r_mask)
    grid_area = np.pi * (radius_pixels ** 2)

    max_freq = max(freq_A, freq_B)
    ideal_c_step = max_freq * np.pi * N_grid / (2.4048 * fs)
    
    M = 1
    if ideal_c_step > 0.42:
        M = int(np.ceil(ideal_c_step / 0.42))
    estimated_complexity = N_grid * N_grid * M
    estimated_render_time = duration * M
    print(f"📊 Сетка: {N_grid}x{N_grid} | Стабильность CFL: требуется {M} субстепов за сэмпл.")
    print(f"⏱ Оценочное время рендеринга: {estimated_render_time:.2f} сек. при текущей длительности и CFL.")
    if estimated_complexity > (N_REF ** 3):
        print(f"⚠️ Высокая нагрузка: оценочная вычислительная сложность {estimated_complexity:,} > {N_REF ** 3:,}.")

    # ------------------------------------------------------------------
    # --- НОВЫЙ БЛОК: ГЕНЕРАЦИЯ ГЕТЕРОГЕННЫХ КАРТ ИЗ GRID_BUILDER ---
    # ------------------------------------------------------------------
    
    # 1. Генерируем сырую карту свойств из исходного материала (с учетом включений!)
    grids_raw, _ = build_heterogeneous_grids(r_mask, skin_mat_raw, MATERIAL_PHYSICS)
    
    # 2. Вычисляем скалярную базу для калибровки тона (Тюнинг ноты)
    base_E = skin_mat_raw.get("E_long", 10.0)
    base_rho = skin_mat_raw.get("density", 1.0)
    base_v_sq = base_E / base_rho
    
    # 3. Карты локальной скорости звука и анизотропии
    local_v_sq_map = grids_raw["E_l"] / (grids_raw["rho"] + 1e-9)
    v_sq_ratio_map = local_v_sq_map / base_v_sq  # Локальные отклонения от базовой ноты
    
    E_l_map = grids_raw["E_l"]
    E_t_map = grids_raw["E_t"]
    sum_E_map = E_l_map + E_t_map + 1e-9
    aniso_x_map = 2.0 * E_l_map / sum_E_map
    aniso_y_map = 2.0 * E_t_map / sum_E_map
    
    # 4. Перевод в квадраты CFL скорости для Taichi
    base_c_sq_A = (freq_A * np.pi * N_grid / (2.4048 * fs * M)) ** 2
    base_c_sq_B = (freq_B * np.pi * N_grid / (2.4048 * fs * M)) ** 2
    
    c_x_A_map = np.clip(base_c_sq_A * v_sq_ratio_map * aniso_x_map, 0.001, 0.24).astype(np.float32)
    c_y_A_map = np.clip(base_c_sq_A * v_sq_ratio_map * aniso_y_map, 0.001, 0.24).astype(np.float32)
    
    c_x_B_map = np.clip(base_c_sq_B * v_sq_ratio_map * aniso_x_map, 0.001, 0.24).astype(np.float32)
    c_y_B_map = np.clip(base_c_sq_B * v_sq_ratio_map * aniso_y_map, 0.001, 0.24).astype(np.float32)
    
    # Загружаем карты скорости в память видеокарты/Taichi
    c_sq_x_A_field.from_numpy(c_x_A_map)
    c_sq_y_A_field.from_numpy(c_y_A_map)
    c_sq_x_B_field.from_numpy(c_x_B_map)
    c_sq_y_B_field.from_numpy(c_y_B_map)

    # 5. Инициализация множителей затухания (позже переопределяются артикуляциями)
    # [NEW] Тело барабанщика прижимает края мембраны, увеличивая потери энергии
    mult_loss_A = 0.5 * (1.0 + body_damping * 1.5)
    mult_visco_A = 25.0 * (1.0 + body_damping * 0.5)
    mult_loss_B = 0.5 * 0.8 * (1.0 + body_damping * 1.5)
    mult_visco_B = 25.0 * 0.7 * (1.0 + body_damping * 0.5)

    max_steps = int(duration * fs)
    fdtd_signal = np.zeros(max_steps)
    
    # [NEW] Массивы физической телеметрии (Сенсоры)
    velocity_arr = np.zeros(max_steps, dtype=np.float32)
    acceleration_arr = np.zeros(max_steps, dtype=np.float32)
    stress_arr = np.zeros(max_steps, dtype=np.float32)
    prev_vel = 0.0
    
    tactile = skin_mat.get("tactile_profile", {})
    gran = np.clip(tactile.get("granularity", 0.0), 0.0, 1.0)
    brit = np.clip(tactile.get("brittleness", 0.0), 0.0, 1.0)
    has_tactile = (gran > 0 or brit > 0 or articulation == "chapa")
    
    contact_time_ms = 5.0
    mic_mix_A, mic_mix_B = 0.75, 0.25
    r_strike_A, r_strike_B = 10.0 * (N_grid / 128.0), 0.0
    exc_multiplier = 0.14
    strike_x_A, strike_y_A = N_grid // 2, N_grid // 2
    strike_x_B, strike_y_B = N_grid // 2, N_grid // 2
    target_membrane = "A"

    if articulation == "open_bass":
        contact_time_ms = 5.0 - (2.5 * strike_force) 
        mic_mix_A, mic_mix_B = 0.75, 0.25
        r_strike_A = (20.0 + 5.0 * strike_force) * (N_grid / 128.0)
        exc_multiplier = 0.14 
        target_membrane = "A"

    elif articulation == "duum":
        contact_time_ms = 3.5 - (1.0 * strike_force) 
        mic_mix_A, mic_mix_B = 0.85, 0.15
        r_strike_A = (16.0 + 6.0 * strike_force) * (N_grid / 128.0)
        exc_multiplier = 0.35 
        strike_y_A = int(center + 0.78 * radius_pixels)
        target_membrane = "A"

    elif articulation == "mute":
        contact_time_ms = 5.0 - (2.5 * strike_force) 
        mic_mix_A, mic_mix_B = 0.75, 0.25
        r_strike_A = (20.0 + 5.0 * strike_force) * (N_grid / 128.0)
        exc_multiplier = 0.14 
        target_membrane = "A"

    elif articulation == "tek_B":
        contact_time_ms = 2.0 - (1.3 * (strike_force ** 1.5)) 
        mic_mix_A, mic_mix_B = 0.10, 0.90
        r_strike_A = 0.0 
        r_strike_B = (3.0 + 4.0 * strike_force) * (N_grid / 128.0)
        exc_multiplier = 0.32 
        mult_loss_B = 0.18
        mult_visco_B = 0.12 
        strike_y_B = int(center + 0.88 * radius_pixels) 
        target_membrane = "B"

    elif articulation == "tek_A":
        contact_time_ms = 2.0 - (1.3 * (strike_force ** 1.5)) 
        mic_mix_A, mic_mix_B = 0.90, 0.10
        r_strike_B = 0.0
        r_strike_A = (3.0 + 4.0 * strike_force) * (N_grid / 128.0)
        exc_multiplier = 0.32 
        mult_loss_A = 0.40
        mult_visco_A = 0.35
        strike_y_A = int(center + 0.88 * radius_pixels) 
        target_membrane = "A"

    elif articulation == "chapa":
        # ГИБРИД: 1.25 мс (среднее между 1.0 и 1.5)
        contact_time_ms = 1.25 
        mic_mix_A, mic_mix_B = 0.50, 0.50 
        r_strike_A = (4.5 + 2.5 * strike_force) * (N_grid / 128.0) 
        r_strike_B = 0.0
        exc_multiplier = 0.95 
        strike_y_A = int(center + 0.80 * radius_pixels) 
        target_membrane = "A"

        pulse_len = max(10, int((contact_time_ms / 1000.0) * fs * M))
        slap_noise = np.random.normal(0, 1.0, pulse_len)
        nyquist = fs / 2.0
        
        # ГИБРИД: Спектр от 1.25 до 8 кГц (сочный, но не излишне звонкий)
        low_f = np.clip(1250.0, 50.0, nyquist - 1000.0)
        high_f = np.clip(8000.0, low_f + 500.0, nyquist - 100.0)
        b_slap, a_slap = butter(2, [low_f / nyquist, high_f / nyquist], btype='bandpass')
        slap_filtered = lfilter(b_slap, a_slap, slap_noise)
        
        # ГИБРИД: Спад 9.0 (между старым резким 15.0 и слишком долгим 4.0)
        slap_env = np.exp(-np.linspace(0, 9.0, pulse_len))
        slap_transient = slap_filtered * 5.5 * slap_env * (strike_force ** 1.1)
        
        t_sharp = np.linspace(0, np.pi, pulse_len)
        body_punch = np.sin(t_sharp) * np.exp(-np.linspace(0, 3.0, pulse_len)) * (strike_force * exc_multiplier * 1.5)
        
        exciter = body_punch + slap_transient

    elif articulation == "clap_tek":
        contact_time_ms = 0.9
        mic_mix_A, mic_mix_B = 0.05, 0.95
        r_strike_B = 6.0 * (N_grid / 128.0)
        exc_multiplier = 0.45
        # Вычисляем множители пропорционально карте, сохраняя исходные пропорции
        base_loss = skin_mat.get("loss_factor", 0.04)
        base_visco = skin_mat.get("visco_gamma", 2e-5)
        mult_loss_B = 0.38 / base_loss
        mult_visco_B = 0.01 / base_visco
        target_membrane = "B"

    elif articulation == "kopal":
        contact_time_ms = 1.8 - (0.6 * strike_force) 
        mic_mix_A, mic_mix_B = 0.85, 0.15
        r_strike_A = (3.5 + 2.0 * strike_force) * (N_grid / 128.0)
        exc_multiplier = 0.65 
        strike_y_A = int(center + 0.30 * radius_pixels) 
        target_membrane = "A"

    elif articulation == "tchipot":
        contact_time_ms = 0.8
        mic_mix_A, mic_mix_B = 0.15, 0.85
        r_strike_B = 3.0 * (N_grid / 128.0)
        exc_multiplier = 0.35
        mult_loss_B = 0.01
        mult_visco_B = 0.5
        strike_y_B = int(center + 0.72 * radius_pixels)
        target_membrane = "B"

    elif articulation == "wood_click":
        contact_time_ms = 1.0 - (0.4 * strike_force) 
        mic_mix_A, mic_mix_B = 1.0, 0.0
        r_strike_A = 2.0 * (N_grid / 128.0)
        exc_multiplier = 0.6 
        strike_y_A = int(center + 0.95 * radius_pixels) 
        target_membrane = "A"

    elif articulation == "bass_slide":
        contact_time_ms = 600.0 
        mic_mix_A, mic_mix_B = 0.85, 0.15
        r_strike_A = 2.0
        exc_multiplier = 0.022  
        target_membrane = "A"
    else:
        contact_time_ms = 5.0 - (2.5 * strike_force) 
        mic_mix_A, mic_mix_B = 0.75, 0.25
        r_strike_A = (20.0 + 5.0 * strike_force) * (N_grid / 128.0)
        exc_multiplier = 0.14 
        target_membrane = "A"

    E_long = shell_mat.get("E_long", 10.0)
    density = shell_mat.get("density", 0.5)
    v_sound = np.sqrt((E_long * 1e9) / (density * 1000.0))
    shell_freq = freq_B if target_membrane == "B" else freq_A
    base_shell = np.clip(v_sound * 0.06, 150.0, 4500.0)
    if autotune_shell and shell_freq > 0:
        ratio = base_shell / shell_freq
        consonant_multipliers = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]
        best_mult = min(consonant_multipliers, key=lambda x: abs(x - ratio))
        base_shell = shell_freq * best_mult

    # === [NEW] Кэширование IR корпуса в RAM ===
    mat_hash = (
        round(shell_mat.get("E_long", 10.0), 3), 
        round(shell_mat.get("density", 0.5), 3), 
        round(shell_mat.get("loss_factor", 0.02), 4)
    )
    cache_key = (mat_hash, round(base_shell, 1), fs, articulation, round(body_damping, 2))
    
    global _BODY_IR_CACHE
    if cache_key in _BODY_IR_CACHE:
        body_ir = _BODY_IR_CACHE[cache_key]
    else:
        body_ir = generate_body_ir(shell_mat, base_shell_hz=base_shell, fs=fs, articulation=articulation, body_damping=body_damping)
        _BODY_IR_CACHE[cache_key] = body_ir
    # ==========================================

    if rr_index > 1 and articulation not in ["tek_A", "tek_B", "tchipot", "wood_click", "clap_tek"]:
        max_jitter = max(1, int(N_grid * 0.015))
        jitter_x = state.randint(-max_jitter, max_jitter + 1)
        jitter_y = state.randint(-max_jitter, max_jitter + 1)
        
        strike_x_A = int(np.clip(strike_x_A + jitter_x, 2, N_grid - 3))
        strike_y_A = int(np.clip(strike_y_A + jitter_y, 2, N_grid - 3))
        strike_x_B = int(np.clip(strike_x_B + jitter_x, 2, N_grid - 3))
        strike_y_B = int(np.clip(strike_y_B + jitter_y, 2, N_grid - 3))
    
    # Смещение микрофонов от центра (чтобы ловить четные моды, а не только [1,1])
    pickup_x_A = int(N_grid * 0.42)
    pickup_y_A = int(N_grid * 0.44)
    pickup_x_B = int(N_grid * 0.42)
    pickup_y_B = int(N_grid * 0.70)

    # ------------------------------------------------------------------
    # --- ПРИМЕНЕНИЕ АРТИКУЛЯЦИЙ И ТРЕНИЯ ОБ ОБОД (BEARING EDGE) ---
    # ------------------------------------------------------------------
    edge_multiplier = np.ones((N_MAX, N_MAX), dtype=np.float32)
    bearing_width = 3.5 # Ширина деревянного порожка в пикселях
    for i in range(N_grid):
        for j in range(N_grid):
            if r_mask[i, j] > 0.5:
                dist = np.sqrt((i - center)**2 + (j - center)**2)
                dist_to_edge = radius_pixels - dist
                if dist_to_edge < bearing_width:
                    edge_multiplier[i, j] = 1.0 + 5.0 * np.exp(-dist_to_edge / 1.0)
                    
    loss_A_map = (grids_raw["loss"] * mult_loss_A * edge_multiplier / M).astype(np.float32)
    visco_A_map = (grids_raw["visco"] * mult_visco_A * edge_multiplier / M).astype(np.float32)
    
    loss_B_map = (grids_raw["loss"] * mult_loss_B * edge_multiplier / M).astype(np.float32)
    visco_B_map = (grids_raw["visco"] * mult_visco_B * edge_multiplier / M).astype(np.float32)
    
    loss_A_field.from_numpy(loss_A_map)
    visco_A_field.from_numpy(visco_A_map)
    loss_B_field.from_numpy(loss_B_map)
    visco_B_field.from_numpy(visco_B_map)
    
     # --- ВОССТАНАВЛИВАЕМ УДАЛЕННЫЕ ПЕРЕМЕННЫЕ ---
    # 1. Акустическая связь между мембранами (через воздух)
    coupling_k_step = 0.010 / M if articulation in ["tek_A", "tek_B"] else 0.015 / M
    
    # 2. Жесткость мембраны (потребуется в конце функции для wood-фильтров)
    E_x = skin_mat.get("E_long", 10.0)

    pulse_len = max(10, int((contact_time_ms / 1000.0) * fs * M))
    t_pulse = np.linspace(-np.pi/2, np.pi/2, pulse_len)

    if articulation in ["tek_A", "tek_B"]:
        finger_noise = np.random.normal(0, 1.0, pulse_len)
        nyquist = fs / 2.0
        
        low_f = np.clip(1500.0, 50.0, nyquist - 1000.0)
        high_f = np.clip(13000.0, low_f + 500.0, nyquist - 100.0)
        b_finger, a_finger = butter(1, [low_f / nyquist, high_f / nyquist], btype='bandpass')
        finger_filtered = lfilter(b_finger, a_finger, finger_noise)
        
        finger_filtered = lfilter([0.3, 0.7], [1.0], finger_filtered)
        
        finger_env = np.exp(-np.linspace(0, 2.5, pulse_len))
        
        finger_snap = finger_filtered * 0.55 * finger_env * (strike_force ** 1.1)
        
        exciter = (np.cos(t_pulse) ** 2) * (strike_force * exc_multiplier * 1.1) + finger_snap
    elif articulation == "chapa":
        pulse_len = max(10, int((contact_time_ms / 1000.0) * fs * M))
        
        slap_noise = np.random.normal(0, 1.0, pulse_len)
        nyquist = fs / 2.0
        
        low_f = np.clip(800.0, 50.0, nyquist - 1000.0)
        high_f = np.clip(12000.0, low_f + 500.0, nyquist - 100.0)
        b_slap, a_slap = butter(2, [low_f / nyquist, high_f / nyquist], btype='bandpass')
        slap_filtered = lfilter(b_slap, a_slap, slap_noise)
        
        slap_env = np.exp(-np.linspace(0, 5.0, pulse_len))
        slap_transient = slap_filtered * 6.0 * slap_env * (strike_force ** 1.1)
        
        t_sharp = np.linspace(0, np.pi, pulse_len)
        body_punch = np.sin(t_sharp) * np.exp(-np.linspace(0, 3.0, pulse_len)) * (strike_force * exc_multiplier * 1.5)
        
        exciter = body_punch + slap_transient
    elif articulation == "bass_slide":
        total_substeps = max_steps * M
        slide_substeps = min(total_substeps, int((contact_time_ms / 1000.0) * fs * M))
        
        t_exc = np.arange(slide_substeps) / (fs * M)
        f_sweep = np.linspace(45.0, 115.0, slide_substeps)
        decay_sweep = np.exp(-t_exc / 0.25) 
        phase_sweep = 2.0 * np.pi * np.cumsum(f_sweep) / (fs * M)
        
        b_rub, a_rub = butter(1, 250.0 / (fs * M / 2.0), btype='low')
        friction_noise = np.random.normal(0, 1.0, slide_substeps)
        friction_noise = lfilter(b_rub, a_rub, friction_noise) * 0.15
        
        slide_active = (np.sin(phase_sweep) * 0.6 + friction_noise) * decay_sweep * strike_force * exc_multiplier
        exciter = np.zeros(total_substeps)
        exciter[:slide_substeps] = slide_active
    elif articulation in ["kopal", "tchipot", "wood_click"]:
        t_pulse = np.linspace(0, np.pi, pulse_len)
        hard_pulse = np.sin(t_pulse) * (strike_force ** 1.2) * exc_multiplier * 2.0
        
        E_x = skin_mat.get("E_long", 1.5)
        den_x = skin_mat.get("density", 1.1)
        loss_x = skin_mat.get("loss_factor", 0.05)
        brit_x = skin_mat.get("tactile_profile", {}).get("brittleness", 0.0)
        
        if articulation == "wood_click":
            E_x = shell_mat.get("E_long", 11.2)
            den_x = shell_mat.get("density", 0.64)
            loss_x = shell_mat.get("loss_factor", 0.018)
        
        v_sound = np.sqrt(max(E_x, 0.01) / max(den_x, 0.1))
        click_freq = 600.0 + 500.0 * (v_sound ** 1.5)
        click_freq = np.clip(click_freq, 600.0, 14000.0)
        
        damp_freq = 20000.0 * np.exp(-40.0 * loss_x)
        damp_freq = np.clip(damp_freq, click_freq + 600.0, fs/2.1)
        
        b_click, a_click = butter(2, click_freq / (fs * M / 2.0), btype='high')
        contact_click = lfilter(b_click, a_click, np.random.normal(0, 1.0, pulse_len)) * 0.18 * strike_force
        
        b_cdamp, a_cdamp = butter(1, damp_freq / (fs * M / 2.0), btype='low')
        contact_click = lfilter(b_cdamp, a_cdamp, contact_click)
        
        if brit_x > 0.1:
            contact_click[0] += brit_x * strike_force * 0.6
            
        exciter = hard_pulse + contact_click

    elif articulation == "clap_tek":
        clap_noise = np.random.normal(0, 1.0, pulse_len)
        
        # Определяем частоту Найквиста на субстеп-частоте симуляции
        nyquist_sub = (fs * M) / 2.0
        
        # Ограничиваем частоты полосы, чтобы они никогда не превысили Найквист при любом M
        low_f = np.clip(2000.0, 50.0, nyquist_sub - 500.0)
        high_f = np.clip(7000.0, low_f + 500.0, nyquist_sub - 100.0)
        
        # Передаем массив из двух частот, нормированных на Найквист субстеппинга
        b_clap, a_clap = butter(1, [low_f / nyquist_sub, high_f / nyquist_sub], btype='bandpass')
        clap_filtered = lfilter(b_clap, a_clap, clap_noise)
        
        exciter = (np.cos(t_pulse) ** 2) * (strike_force * exc_multiplier) + clap_filtered * 0.6 * strike_force


    else: 
        t_pulse = np.linspace(-np.pi/2, np.pi/2, pulse_len)
        exciter = (np.cos(t_pulse) ** 2) * (strike_force ** 1.3) * exc_multiplier
    
    exciter_scale = float(N_REF) / float(N_grid)
    exciter *= exciter_scale

    if brit > 0.05:
        exciter[0] += strike_force * brit * 0.6 
    
    bend_dampener = np.clip(1.0 - (brit * 1.5), 0.05, 1.0)
    p_bend_A = 0.12 * (strike_force ** 2.5) * bend_dampener
    p_bend_B = 0.09 * (strike_force ** 3.0) * bend_dampener
    
    if articulation in ["kopal", "tchipot", "wood_click", "clap_tek"]:
        p_bend_A *= 0.10
        p_bend_B *= 0.10

    inertia_tau = 0.0037 
    strain_alpha = 1.0 - np.exp(-1.0 / (fs * inertia_tau))
    
    smoothed_strain_A = 0.0
    smoothed_strain_B = 0.0

    # --- [НОВОЕ] КОЛЬЦЕВОЙ БУФЕР ВОЗДУШНОГО СТОЛБА ---
    delay_substeps = max(1, int(0.001 * fs * M)) 
    vol_history_A = np.zeros(delay_substeps, dtype=np.float32)
    vol_history_B = np.zeros(delay_substeps, dtype=np.float32)
    history_idx = 0
    # -------------------------------------------------

    gui = None
    if show_gui:
        gui = ti.GUI(f"Dhol: {articulation.upper()} (Grid: {N_grid})", res=(2 * N_grid, N_grid), background_color=0x000000)
        
    actual_steps_rendered = 0

    for step in range(max_steps):
        actual_steps_rendered += 1
        
        if step % 800 == 0:
            if yield_cb:
                yield_cb(step, max_steps)
                
            if show_gui and gui:
                if not gui.running:
                    gui.close()
                    raise InterruptedError("Рендеринг прерван.")
                    
                field_A = p_A.to_numpy()[:N_grid, :N_grid]
                field_B = p_B.to_numpy()[:N_grid, :N_grid]
                
                mask_vis = mask_A.to_numpy()[:N_grid, :N_grid]
                img = np.zeros((2 * N_grid, N_grid, 3), dtype=np.float32)
                
                img[:N_grid, :, :] += mask_vis[:, :, None] * 0.15
                img[N_grid:, :, :] += mask_vis[:, :, None] * 0.15
                
                vis_gain = 25.0 
                
                img[:N_grid, :, 0] += np.clip(field_A * vis_gain, 0, 1) * mask_vis
                img[:N_grid, :, 2] += np.clip(-field_A * vis_gain, 0, 1) * mask_vis
                
                img[N_grid:, :, 1] += np.clip(field_B * vis_gain, 0, 1) * mask_vis
                img[N_grid:, :, 2] += np.clip(-field_B * vis_gain, 0, 1) * mask_vis
                
                gui.set_image(img)
                progress_val = step / max_steps
                gui.line(begin=(0.05, 0.05), end=(0.95, 0.05), color=0x222222, radius=2)
                gui.line(begin=(0.05, 0.05), end=(0.05 + 0.9 * progress_val, 0.05), color=0x00ff96, radius=2)
                gui.show()
                
                ac_A = field_A - np.mean(field_A)
                ac_B = field_B - np.mean(field_B)
                real_energy = np.max(np.abs(ac_A)) + np.max(np.abs(ac_B))
                if step > fs * 0.15 and real_energy < 5e-5:
                    break
            else:
                compute_dhol_stats(N_grid)
                if step > fs * 0.15 and (stat_strain_A[None] + stat_strain_B[None]) < 1e-9:
                    break

        compute_dhol_stats(N_grid)
        raw_strain_A = stat_strain_A[None] / grid_area * ((N_grid / float(N_REF)) ** 2)
        raw_strain_B = stat_strain_B[None] / grid_area * ((N_grid / float(N_REF)) ** 2)
        
        smoothed_strain_A += strain_alpha * (raw_strain_A - smoothed_strain_A)
        smoothed_strain_B += strain_alpha * (raw_strain_B - smoothed_strain_B)
        
        avg_vol_A = stat_vol_A[None] / grid_area
        avg_vol_B = stat_vol_B[None] / grid_area

        damp_A_val, damp_A_cov = 0.0, 0
        damp_B_val, damp_B_cov = 0.0, 0
        
        if articulation == "mute":
            mute_start = int(0.025 * fs)
            if step > mute_start:
                ramp = min(1.0, (step - mute_start) / (0.020 * fs))
                damp_A_val, damp_A_cov = 0.035 * ramp, N_grid
                damp_B_val, damp_B_cov = 0.035 * ramp, N_grid
        elif articulation == "chapa":
            chapa_start = int(0.008 * fs) 
            if step > chapa_start:
                ramp = min(1.0, (step - chapa_start) / (0.005 * fs))
                damp_A_val, damp_A_cov = 0.02 * ramp, int(N_grid * 0.4)
                damp_B_val, damp_B_cov = 0.02 * ramp, int(N_grid * 0.4)
        elif articulation == "tek_B":
            damp_A_val, damp_A_cov = 0.04, int(N_grid * 0.39)
        elif articulation == "tek_A":
            damp_B_val, damp_B_cov = 0.04, int(N_grid * 0.39)
        elif articulation == "duum":
            if step < int(0.012 * fs):
                damp_A_val, damp_A_cov = 0.003, int(N_grid * 0.5)

        # Данный цикл зафиксирован строго внутри родительского "for step in range(max_steps):"
        for sub in range(M):
            step_internal = step * M + sub 

            exc_val_A = exciter[step_internal] if (step_internal < pulse_len and target_membrane == "A") else 0.0
            exc_val_B = exciter[step_internal] if (step_internal < pulse_len and target_membrane == "B") else 0.0

            damp_A_val_step = damp_A_val / M
            damp_B_val_step = damp_B_val / M

            vol_A_delayed = vol_history_A[history_idx]
            vol_B_delayed = vol_history_B[history_idx]
            
            vol_history_A[history_idx] = avg_vol_A
            vol_history_B[history_idx] = avg_vol_B
            history_idx = (history_idx + 1) % delay_substeps

            step_dhol_fdtd(
                N_grid,
                coupling_k_step, avg_vol_A, avg_vol_B, 
                vol_A_delayed, vol_B_delayed,  # <--- ВОТ ЭТУ СТРОЧКУ ТЫ ЗАБЫЛ ВСТАВИТЬ!
                strike_x_A, strike_y_A, exc_val_A, r_strike_A,
                strike_x_B, strike_y_B, exc_val_B, r_strike_B,
                p_bend_A, p_bend_B, smoothed_strain_A, smoothed_strain_B, 
                damp_A_val_step, damp_A_cov, damp_B_val_step, damp_B_cov
            )

            if has_tactile:
                slap_fric_A_step = 0.0
                slap_fric_B_step = 0.0 

                if articulation == "chapa" and step < int(0.15 * fs):
                    t_curr = step / fs
                    env = np.exp(-t_curr / 0.090)
                    if t_curr < 0.003:
                        env *= (t_curr / 0.003)
                    slap_fric_A_step = env * (strike_force ** 1.1) * 20.0

                apply_dhol_tactile_forces(
                    N_grid, gran, brit, strike_force,
                    slap_fric_A_step, slap_fric_B_step,
                    strike_x_A, strike_y_A,
                    strike_x_B, strike_y_B,
                    r_strike_A, r_strike_B
                )

            update_dhol_fields(N_grid)

        # Снятие телеметрии с точки удара
        tx, ty = (strike_x_A, strike_y_A) if target_membrane == "A" else (strike_x_B, strike_y_B)
        
        if target_membrane == "A":
            p_curr = p_A[tx, ty]
            p_past = p_A_past[tx, ty]
            # Аппроксимация тензора напряжений (Laplacian)
            local_stress = p_A[tx+1, ty] + p_A[tx-1, ty] + p_A[tx, ty+1] + p_A[tx, ty-1] - 4.0 * p_curr
        else:
            p_curr = p_B[tx, ty]
            p_past = p_B_past[tx, ty]
            local_stress = p_B[tx+1, ty] + p_B[tx-1, ty] + p_B[tx, ty+1] + p_B[tx, ty-1] - 4.0 * p_curr
            
        current_vel = p_curr - p_past
        current_accel = current_vel - prev_vel
        prev_vel = current_vel
        
        velocity_arr[step] = current_vel
        acceleration_arr[step] = current_accel
        stress_arr[step] = local_stress

        fdtd_signal[step] = p_A[pickup_x_A, pickup_y_A] * mic_mix_A + p_B[pickup_x_B, pickup_y_B] * mic_mix_B

    if show_gui and gui:
        gui.close()

    # Окончание главного цикла симуляции
    fdtd_signal = fdtd_signal[:actual_steps_rendered]
    velocity_arr = velocity_arr[:actual_steps_rendered]
    acceleration_arr = acceleration_arr[:actual_steps_rendered]
    stress_arr = stress_arr[:actual_steps_rendered]
    
    fade_fdtd = min(int(fs * 0.01), len(fdtd_signal))
    if fade_fdtd > 0:
        fdtd_signal[-fade_fdtd:] *= np.linspace(1.0, 0.0, fade_fdtd) ** 2

    raw_shell_loss = shell_mat.get("loss_factor", 0.02)
    calc_loss = max(0.015, raw_shell_loss) 
    
    base_pad_seconds = 0.025 / calc_loss

    if articulation in ["tek_A", "tek_B"]:
        pad_seconds = np.clip(base_pad_seconds, 0.8, 1.4)
    elif articulation in ["tchipot", "wood_click", "clap_tek"]:
        pad_seconds = np.clip(base_pad_seconds, 0.4, 0.8)
    elif articulation in ["mute", "chapa"]:
        pad_seconds = np.clip(base_pad_seconds, 0.3, 0.6)
    elif articulation == "duum":
        pad_seconds = np.clip(base_pad_seconds, 1.0, 1.8)
    else:
        pad_seconds = np.clip(base_pad_seconds, 1.2, 2.5)

    pad_samples = int(fs * pad_seconds)
    padded_signal = np.pad(fdtd_signal, (0, pad_samples))
    
    # Дополняем массивы телеметрии нулями для совпадения длин
    velocity_arr = np.pad(velocity_arr, (0, pad_samples))
    acceleration_arr = np.pad(acceleration_arr, (0, pad_samples))
    stress_arr = np.pad(stress_arr, (0, pad_samples))
    
    # Саб-генератор подхватывает частоту мембраны B для артикуляций стороны B
    shell_freq = freq_B if target_membrane == "B" else freq_A
    shell_signal = apply_acoustic_shell(
        padded_signal, fs, shell_mat, shell_freq, articulation, strike_force, 
        autotune_shell=autotune_shell,
        ring_mod=ring_mod,
        body_damping=body_damping
    )
    
    shell_delay = int(0.00008 * fs)
    delayed_shell = np.zeros_like(shell_signal)
    if len(shell_signal) > shell_delay:
        delayed_shell[shell_delay:] = shell_signal[:-shell_delay]
    else:
        delayed_shell = shell_signal
        
    shell_dynamic_scale = 0.25 + 0.75 * (strike_force ** 0.85)
    delayed_shell *= shell_dynamic_scale
        
    mixed_signal = padded_signal + delayed_shell
    
    t_arr = np.arange(len(mixed_signal)) / fs
    
    tactile_noise = generate_tactile_profile(
        skin_mat, t_arr, mixed_signal, 
        velocity_arr, acceleration_arr, stress_arr,
        fs, fs/2.0, is_space=False, fatness=mat_boost, strike_force=strike_force
    )
    
    # 1. СНАЧАЛА вычисляем кинематику и напряжения деревянного корпуса
    shell_vel = np.append(np.diff(delayed_shell), 0).astype(np.float32)
    shell_accel = np.append(np.diff(shell_vel), 0).astype(np.float32)
    shell_stress = (shell_vel * 0.5).astype(np.float32)  # Напряжение сдвига волокон кадушки 
    
    # 2. И ТОЛЬКО ПОТОМ генерируем тактильный шум (используем mat_boost вместо fatness/saturation)
    shell_tactile_noise = generate_tactile_profile(
        shell_mat, t_arr, delayed_shell, 
        shell_vel, shell_accel, shell_stress,
        fs, fs/2.0, is_space=False, fatness=mat_boost, strike_force=strike_force
    )
    
    if articulation != "bass_slide":
        # Даем Тэкам и Чапе длинные "дышащие" хвосты
        if articulation in ["tek_A", "tek_B"]:
            tact_decay = 0.30
        elif articulation == "chapa":
            tact_decay = 0.28  # Пропускаем удлиненный шипящий хвост клэпа!
        else:
            tact_decay = 0.195
            
        tactile_env = np.exp(-t_arr / tact_decay) 
        tactile_noise *= tactile_env
        # Её тактильный хруст, дребезг и вибрация затухают на 100% естественно, следуя за физикой затухания корпуса

    if E_x < 5.0 and brit > 0.0:
        b_wood, a_wood = butter(2, 4500.0 / (fs / 2.0), btype='low')
        tactile_noise = lfilter(b_wood, a_wood, tactile_noise)
        
    # Радикально снижаем уровень сырого белого/гранулярного шума из tactile.py
    if articulation == "chapa":
        tactile_mix = 0.35 * (strike_force ** 1.2) # Делаем хвост хлопка ярким и читаемым
    elif articulation in ["tek_A", "tek_B"]:
        tactile_mix = 0.22 * (strike_force ** 1.5) 
    elif articulation == "mute":
        tactile_mix = 0.08 * (strike_force ** 2.2)
    else: 
        tactile_mix = 0.14 * (strike_force ** 2.2)
    
    shell_tactile_mix = 0.12 * (strike_force ** 2.0) # Слегка подняли базу для кадушки
    
    # Применяем новые независимые ручки mat_boost и membrane_tactile
    tactile_mix *= (1.0 + mat_boost * 1.0) * membrane_tactile
    shell_tactile_mix *= (1.0 + mat_boost * 1.0)
    
    final_output = mixed_signal * 0.65 + tactile_noise * tactile_mix + shell_tactile_noise * shell_tactile_mix
    
    final_output = apply_meat_and_fat(
        final_output, fs, articulation, strike_force, 
        saturation=saturation, skin_mat=skin_mat, shell_mat=shell_mat,
        shell_attack=shell_attack, shell_sustain=shell_sustain,
        membrane_snap=membrane_snap
    )
    
    # === БЛОК ДЕКЛИКИНГА (LPC AR Model) ===
    final_output, _ = declick_ar_model(final_output, fs)
    
    if use_bells and len(acceleration_arr) > 0:
        dynamic_mix = bell_mix * (strike_force ** 0.5)

        final_output = apply_internal_bells(
            membrane_signal=final_output,
            acceleration_signal=acceleration_arr,
            fs=fs,
            material_name=bell_material,
            mix=dynamic_mix,
            rr_index=rr_index,
            strike_force=strike_force,
            bell_peak_ratio=1.0,
            ring_mod=ring_mod
        )
    
    if body_polish_mix > 0.0:
        print(f"Applying body polish with mix: {body_polish_mix:.2f}")
        final_output = apply_body_convolution(final_output, body_ir, fs, mix=body_polish_mix)
    
    # === БЛОК 1: Калибровка сухого сигнала ===
    max_val = np.max(np.abs(final_output))
    if max_val > 0:
        final_output /= max_val
        
        # Практика сэмплирования: оставляем запеченный диапазон в 8 дБ.
        # Всю остальную динамику возьмет на себя движок сэмплера (Kontakt/т.п.)
        min_force = 16.0 / 127.0
        min_amp = 10.0 ** (-8.0 / 20.0) # -8 дБ (≈ 0.398)
        
        clipped_force = np.clip(strike_force, min_force, 1.0)
        norm_force = (clipped_force - min_force) / (1.0 - min_force)
        
        # Линейная интерполяция амплитуды (norm_force вместо norm_force ** 1.1)
        # делает тихие слои более "мясистыми" до того, как сэмплер их приглушит
        dynamic_range_scale = min_amp + (1.0 - min_amp) * norm_force
        final_output *= dynamic_range_scale * 0.85

    env = np.abs(final_output)
    active_indices = np.where(env > 1e-4)[0]
    if len(active_indices) > 0:
        final_output = final_output[:active_indices[-1] + int(fs * 0.05)]

    room_stereo = apply_3d_studio_room(final_output, fs)
    
    if articulation in ["duum", "kopal", "bass_slide", "mute", "wood_click", "open_bass"]:
        dry_mix = 0.80
        wet_mix = 0.20
    else:
        dry_mix = 0.60
        wet_mix = 0.40
        
    dry_stereo = np.column_stack((final_output, final_output))
    stereo_output = (dry_stereo * dry_mix) + (room_stereo * wet_mix)
    
    max_val = np.max(np.abs(stereo_output))
    if max_val > 0:
        min_force = 16.0 / 127.0
        min_amp = 10.0 ** (-8.0 / 20.0) 
        
        clipped_force = np.clip(strike_force, min_force, 1.0)
        norm_force = (clipped_force - min_force) / (1.0 - min_force)
        
        dynamic_range_scale = min_amp + (1.0 - min_amp) * norm_force
        stereo_output = (stereo_output / max_val) * dynamic_range_scale * 0.92

    if yield_cb:
        yield_cb(max_steps, max_steps)

    return stereo_output