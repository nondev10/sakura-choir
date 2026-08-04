import os
import json
import random
import subprocess
from pathlib import Path

# ---------- 交互工具 ----------
def get_input(prompt, default=None, cast_type=str):
    while True:
        val = input(prompt).strip()
        if val == "" and default is not None:
            return default
        try:
            return cast_type(val)
        except:
            print(f"请输入有效的{cast_type.__name__}")

# ---------- 扫描文件夹 ----------
def scan_audio_files(folder):
    exts = [".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg"]
    files = []
    for ext in exts:
        files.extend(folder.glob(f"*{ext}"))
        files.extend(folder.glob(f"*{ext.upper()}"))
    return sorted(set(files))

# ---------- 主函数 ----------
def main():
    print("🎤 欢迎使用虚拟合唱生成器（乘法堆叠版）")
    print("💡 逻辑说明：每个音源按'人数'展开，然后通过复制堆叠凑齐总人数。")
    print("   (例如: 30,1,1,1,2 -> 35人基础池 -> x2+30 -> 100人)\n")

    # 1. 音频源文件夹
    folder = input(f"请输入音频文件夹路径（默认 assets/audio）: ").strip()
    folder = folder if folder else "assets/audio"
    folder_path = Path(folder)
    if not folder_path.exists():
        print("❌ 文件夹不存在")
        return

    files = scan_audio_files(folder_path)
    if not files:
        print("❌ 未找到音频文件")
        return

    # 2. 收集音源信息（记录人数和齐头点）
    print(f"\n📂 找到 {len(files)} 个文件，请逐个输入信息：")
    source_list = []  # 每个元素: {"file": path, "count": N, "voice_start": X}
    for f in files:
        print(f"\n--- {f.name} ---")
        count = get_input("该音源代表多少人？（作为堆叠基数，默认1）: ", default=1, cast_type=int)
        start = get_input("人声开始对齐点（秒，默认0）: ", default=0.0, cast_type=float)
        source_list.append({
            "file": str(f),
            "count": count,
            "voice_start": start
        })

    # 计算最大对齐点
    max_start = max([s["voice_start"] for s in source_list])

    # 3. 目标总人数与批次
    total_people = get_input("\n🎯 本轮目标总人数（例如 100）: ", default=100, cast_type=int)
    batch_size = get_input("每批次混合人数（建议30~50，默认30）: ", default=30, cast_type=int)
    gain = get_input("输出音量增益倍数（默认3）: ", default=3.0, cast_type=float)

    # 4. 选择声部策略
    print("\n📋 请选择声部配置策略：")
    print("  1. 标准四声部 (S/A/T/B 3:3:2:2，层次分明)")
    print("  2. 大齐唱 (八度叠加，气势宏大)")
    print("  3. 纯随机 (跑调大，模拟街头)")
    strategy = get_input("请输入编号（默认 1）: ", default=1, cast_type=int)

    if strategy == 1:
        parts = [
            {"name": "Soprano", "ratio": 0.30, "shift_semitones": 0},
            {"name": "Alto",    "ratio": 0.30, "shift_semitones": -3},
            {"name": "Tenor",   "ratio": 0.20, "shift_semitones": -7},
            {"name": "Bass",    "ratio": 0.20, "shift_semitones": -12}
        ]
        detune_range = 8
    elif strategy == 2:
        parts = [
            {"name": "High", "ratio": 0.40, "shift_semitones": 0},
            {"name": "Low",  "ratio": 0.40, "shift_semitones": -12},
            {"name": "Mid",  "ratio": 0.20, "shift_semitones": -5}
        ]
        detune_range = 5
    else:
        parts = [{"name": "Random", "ratio": 1.0, "shift_semitones": 0}]
        detune_range = 15

    # 5. 选择声场模型
    print("\n🎧 请选择声场模型：")
    print("  1. 标准立体声 (线性左右)")
    print("  2. 球形声场 (中间饱满，两侧衰减，默认)")
    print("  3. 宽声场 (极左极右增强)")
    field = get_input("请输入编号（默认 2）: ", default=2, cast_type=int)

    # ===== 核心算法：按“人数”展开基础池 =====
    print("\n🔧 正在按人数展开基础池...")
    base_pool = []  # 存储待分配声部的原始引用
    for src in source_list:
        for _ in range(src["count"]):
            base_pool.append(src)
    
    base_size = len(base_pool)
    print(f"✅ 基础池构建完成，共 {base_size} 个实例 (例如 30+1+1+1+2=35)")

    # 按目标人数进行乘法堆叠
    singer_refs = []  # 最终选中参与本轮的引用列表
    if base_size >= total_people:
        # 基础池人数够多，随机截取
        singer_refs = random.sample(base_pool, total_people)
        print(f"📌 基础池足够，随机抽取 {total_people} 人")
    else:
        # 关键：乘法堆叠逻辑 (模拟你的 x2 + 30)
        repeats = total_people // base_size
        remainder = total_people % base_size
        
        # 复制整数倍 (例如 x2)
        for _ in range(repeats):
            singer_refs.extend(base_pool)
        
        # 补足余数 (例如 +30)
        if remainder > 0:
            singer_refs.extend(random.sample(base_pool, remainder))
        
        print(f"📌 堆叠策略: 复制 {repeats} 次基础池 (共 {repeats*base_size} 人)，再随机补足 {remainder} 人，合计 {total_people} 人")

    # 打乱顺序，避免同源聚集
    random.shuffle(singer_refs)

    # 为每个最终参与者分配具体的声部、变调、延迟、声像
    print("🎼 正在分配声部与随机参数...")
    singers = []
    
    # 根据声部比例分配角色
    part_assignments = []
    for part in parts:
        count = int(total_people * part["ratio"])
        part_assignments.extend([part] * count)
    # 补全/截断确保精确
    while len(part_assignments) < total_people:
        part_assignments.append(random.choice(parts))
    part_assignments = part_assignments[:total_people]
    random.shuffle(part_assignments)

    for idx, ref in enumerate(singer_refs):
        part = part_assignments[idx]
        shift_cents = part["shift_semitones"] * 100 + random.uniform(-detune_range, detune_range)
        delay_ms = random.randint(0, 30)
        pan = random.uniform(0.1, 0.9)
        singers.append({
            "file": ref["file"],
            "voice_start": ref["voice_start"],
            "shift_cents": shift_cents,
            "delay_ms": delay_ms,
            "pan": pan
        })

    print(f"👥 最终歌手名单生成完毕，共 {len(singers)} 人")

    # ===== 批次处理函数 =====
    OUTPUT_DIR = Path("output")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def build_ffmpeg_command(batch_singers, batch_idx):
        input_args = []
        for s in batch_singers:
            input_args.extend(["-i", s["file"]])

        filter_chains = []
        for idx, s in enumerate(batch_singers):
            # 对齐延迟
            align_delay = max_start - s["voice_start"]
            total_delay_ms = align_delay * 1000 + s["delay_ms"]

            # 变调
            semitones = s["shift_cents"] / 100.0
            rate_ratio = 2 ** (semitones / 12.0)
            tempo_ratio = 1.0 / rate_ratio
            if tempo_ratio < 0.5:
                tempo_ratio = 0.5
            if tempo_ratio > 2.0:
                tempo_ratio = 2.0

            # ---- 声场算法 ----
            pan = s["pan"]
            if field == 1:
                gain_L = pan
                gain_R = 1 - pan
            elif field == 3:
                gain_L = min(1.2, pan * 1.4)
                gain_R = min(1.2, (1 - pan) * 1.4)
            else:  # 球形声场（默认）
                dist_from_center = abs(pan - 0.5) * 2
                attenuation = 1 - 0.3 * (dist_from_center ** 1.5)
                gain_L = pan * attenuation * (1 + 0.1 * (1 - dist_from_center))
                gain_R = (1 - pan) * attenuation * (1 + 0.1 * (1 - dist_from_center))

            filters = []
            filters.append(f"adelay={total_delay_ms}|{total_delay_ms}")
            filters.append("pan=mono|c0=0.5*c0+0.5*c1")
            filters.append(f"asetrate=44100*{rate_ratio}")
            filters.append(f"atempo={tempo_ratio}")
            filters.append(f"pan=stereo|c0={gain_L}*c0|c1={gain_R}*c0")

            filter_chain = f"[{idx}:a]" + ",".join(filters) + f"[a{idx}]"
            filter_chains.append(filter_chain)

        amix_inputs = "".join([f"[a{i}]" for i in range(len(batch_singers))])
        amix_filter = f"{amix_inputs}amix=inputs={len(batch_singers)}:duration=longest"
        filter_complex_str = ",".join(filter_chains) + ";" + amix_filter
        out_path = str(OUTPUT_DIR / f"batch_{batch_idx:04d}.wav")

        cmd = ["ffmpeg", "-y", *input_args, "-filter_complex", filter_complex_str, "-ac", "2", "-ar", "44100", out_path]
        return cmd

    # ===== 生成批次 =====
    batch_count = 0
    print(f"\n🚀 开始分批合成，每批 {batch_size} 人...")
    for i in range(0, len(singers), batch_size):
        batch = singers[i:i+batch_size]
        if len(batch) < 2:
            continue
        cmd = build_ffmpeg_command(batch, batch_count + 1)
        print(f"🔄 正在生成第 {batch_count + 1} 批 ({len(batch)}人)...")
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
            batch_count += 1
        except subprocess.CalledProcessError as e:
            print(f"❌ 批次失败: {e.stderr}")
            return

    if batch_count == 0:
        print("❌ 没有生成批次")
        return

    # ===== 最终合成 =====
    batch_files = sorted(OUTPUT_DIR.glob("batch_*.wav"))
    print(f"🎧 合并 {len(batch_files)} 个批次，增益 {gain}x ...")
    
    input_args = []
    for bf in batch_files:
        input_args.extend(["-i", str(bf)])
    filter_inputs = "".join([f"[{i}:a]" for i in range(len(batch_files))])
    merge_cmd = [
        "ffmpeg", "-y", *input_args,
        "-filter_complex", f"{filter_inputs}amix=inputs={len(batch_files)}:duration=longest,volume={gain}",
        "-ac", "2", "-ar", "44100", "output/final_choir.wav"
    ]
    
    try:
        subprocess.run(merge_cmd, check=True, capture_output=True, text=True, encoding='utf-8')
        print("\n🎉 大功告成！")
        print(f"📁 文件已保存: output/final_choir.wav (共 {total_people} 人)")
        print("\n💡 【乘法迭代提示】")
        print(f"   要把这 {total_people} 人翻倍到 {total_people * 100} 人？")
        print("   1. 将 output/final_choir.wav 复制到你的音频文件夹 (如 assets/audio)")
        print("   2. 再次运行本脚本，该音源输入人数填 100，目标人数填 10000")
        print("   3. 这样就能实现 100 -> 10000 -> 1000000 的指数级堆叠！")
    except Exception as e:
        print(f"❌ 合并失败: {e}")

if __name__ == "__main__":
    main()
