#!/usr/bin/env python3
"""
Screenshot Keeper - VLA 4枚自動撮影版（採用構成）

構成（4枚/セット）:
  1. Grid 48px - マクロ把握
  2. Grid 24px - ミクロ精度
  3. Checker 32px A - 細部検証1
  4. Checker 32px B - 細部検証2

機能:
- スクリーンショット撮影（PowerShell経由）
- 80セット保持（320枚）
- 5秒間隔自動撮影（デフォルト）

使用方法:
    python3 screenshot_keeper.py          # 5秒毎自動撮影
    python3 screenshot_keeper.py --once   # 1回のみ
    python3 screenshot_keeper.py --list   # 一覧
    python3 screenshot_keeper.py 10       # 10秒間隔

サブパターン（実験用）:
    python3 screenshot_experiment.py      # 全19パターン生成
"""

import os
import sys
import glob
import time
import signal
import subprocess
import tempfile
from datetime import datetime
from PIL import Image, ImageDraw

# 設定
SCREENSHOT_DIR = os.path.expanduser("~/Generalstab/VLA_screenshots")
SCREENSHOT_PATH_FILE = os.path.expanduser("~/Generalstab/SharedReminders/vla/screenshot_path.md")
MAX_KEEP = 80  # 最大保持セット数（80セット×4枚=320枚）
GRID_MACRO = 48  # マクロ把握用
GRID_MICRO = 24  # ミクロ精度用
GRID_CHECKER = 32  # チェッカーボード用


def ensure_dir():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(SCREENSHOT_PATH_FILE), exist_ok=True)


def get_sorted_sets():
    """タイムスタンプ順でセット一覧取得（新しい順）"""
    # 新形式: *_grid24div.png
    pattern = os.path.join(SCREENSHOT_DIR, "*_grid24div.png")
    files = glob.glob(pattern)
    # 旧形式もチェック
    for old_suffix in ["*_grid48.png", "*_grid.png"]:
        files.extend(glob.glob(os.path.join(SCREENSHOT_DIR, old_suffix)))
    # タイムスタンプ抽出してソート
    timestamps = set()
    for f in files:
        basename = os.path.basename(f)
        for suffix in ["_grid24div.png", "_grid48.png", "_grid.png"]:
            basename = basename.replace(suffix, "")
        timestamps.add(basename)
    return sorted(timestamps, reverse=True)


def cleanup_old():
    """古いセットを削除（MAX_KEEPセット残す）"""
    import shutil
    sets = get_sorted_sets()
    deleted = []

    if len(sets) > MAX_KEEP:
        old_sets = sets[MAX_KEEP:]
        for ts in old_sets:
            # 新形式: grid24div + tilesディレクトリ
            grid_path = os.path.join(SCREENSHOT_DIR, f"{ts}_grid24div.png")
            tiles_dir = os.path.join(SCREENSHOT_DIR, f"{ts}_tiles")
            if os.path.exists(grid_path):
                os.remove(grid_path)
            if os.path.exists(tiles_dir):
                shutil.rmtree(tiles_dir)
            # 旧形式
            for suffix in ["_grid48.png", "_grid24.png", "_checker_a.png", "_checker_b.png", "_raw.png", "_grid.png"]:
                filepath = os.path.join(SCREENSHOT_DIR, f"{ts}{suffix}")
                if os.path.exists(filepath):
                    os.remove(filepath)
            deleted.append(ts)

    return deleted


def capture_screen() -> Image.Image:
    """PowerShellでスクリーンショット取得"""
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        win_path = subprocess.run(
            ["wslpath", "-w", tmp_path],
            capture_output=True, text=True
        ).stdout.strip()

        ps_script = f'''
Add-Type -AssemblyName System.Windows.Forms
$screen = [System.Windows.Forms.Screen]::PrimaryScreen
$bitmap = New-Object System.Drawing.Bitmap($screen.Bounds.Width, $screen.Bounds.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($screen.Bounds.Location, [System.Drawing.Point]::Empty, $screen.Bounds.Size)
$bitmap.Save("{win_path}", [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
'''
        result = subprocess.run(
            ["powershell.exe", "-Command", ps_script],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0 or not os.path.exists(tmp_path):
            raise RuntimeError(f"PowerShellエラー: {result.stderr}")

        img = Image.open(tmp_path)
        img.load()
        return img

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def draw_grid(img: Image.Image, grid_size: int) -> Image.Image:
    """グリッド線描画（赤半透明）"""
    img_copy = img.copy()
    draw = ImageDraw.Draw(img_copy, 'RGBA')
    w, h = img_copy.size

    for x in range(0, w, grid_size):
        draw.line([(x, 0), (x, h)], fill=(255, 0, 0, 128), width=1)
    for y in range(0, h, grid_size):
        draw.line([(0, y), (w, y)], fill=(255, 0, 0, 128), width=1)

    return img_copy


def create_checkerboard(img: Image.Image, mode: str, grid_size: int) -> Image.Image:
    """チェッカーボード生成 (A=偶数表示, B=奇数表示)"""
    img_copy = img.copy()
    draw = ImageDraw.Draw(img_copy)
    w, h = img_copy.size

    cols = (w + grid_size - 1) // grid_size
    rows = (h + grid_size - 1) // grid_size

    for row in range(rows):
        for col in range(cols):
            is_even = (row + col) % 2 == 0
            should_black = (mode == 'A' and not is_even) or (mode == 'B' and is_even)

            if should_black:
                x1, y1 = col * grid_size, row * grid_size
                x2, y2 = min(x1 + grid_size, w), min(y1 + grid_size, h)
                draw.rectangle([x1, y1, x2, y2], fill=(0, 0, 0))

    return draw_grid(img_copy, grid_size)


def take_screenshot():
    """24分割タイル + グリッド1枚（座標はファイル名で特定）"""
    ensure_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        raw = capture_screen()
        w, h = raw.size

        # 24分割: 6列 × 4行
        cols, rows = 6, 4
        tile_w, tile_h = w // cols, h // rows  # 256×216px per tile

        # タイル用サブディレクトリ
        tile_dir = os.path.join(SCREENSHOT_DIR, f"{timestamp}_tiles")
        os.makedirs(tile_dir, exist_ok=True)

        # 24タイル生成
        tile_paths = []
        for row in range(rows):
            for col in range(cols):
                x1, y1 = col * tile_w, row * tile_h
                x2, y2 = x1 + tile_w, y1 + tile_h
                tile = raw.crop((x1, y1, x2, y2))
                tile_name = f"tile_r{row}_c{col}.png"
                tile_path = os.path.join(tile_dir, tile_name)
                tile.save(tile_path)
                tile_paths.append(tile_path)

        # グリッド画像（24分割線入り）
        grid_img = raw.copy()
        draw = ImageDraw.Draw(grid_img, 'RGBA')
        for col in range(1, cols):
            x = col * tile_w
            draw.line([(x, 0), (x, h)], fill=(255, 0, 0, 200), width=2)
        for row in range(1, rows):
            y = row * tile_h
            draw.line([(0, y), (w, y)], fill=(255, 0, 0, 200), width=2)

        # サムネイル結合画像（低トークン版）
        thumb_w, thumb_h = 64, 54  # 各タイルのサムネサイズ
        montage = Image.new('RGB', (thumb_w * cols, thumb_h * rows))
        for row in range(rows):
            for col in range(cols):
                x1, y1 = col * tile_w, row * tile_h
                x2, y2 = x1 + tile_w, y1 + tile_h
                tile = raw.crop((x1, y1, x2, y2))
                thumb = tile.resize((thumb_w, thumb_h), Image.LANCZOS)
                montage.paste(thumb, (col * thumb_w, row * thumb_h))
        # サムネにグリッド線追加
        draw_m = ImageDraw.Draw(montage)
        for col in range(1, cols):
            draw_m.line([(col * thumb_w, 0), (col * thumb_w, thumb_h * rows)], fill=(255, 0, 0), width=1)
        for row in range(1, rows):
            draw_m.line([(0, row * thumb_h), (thumb_w * cols, row * thumb_h)], fill=(255, 0, 0), width=1)

        # 保存
        paths = {
            'grid': os.path.join(SCREENSHOT_DIR, f"{timestamp}_grid24div.png"),
            'montage': os.path.join(SCREENSHOT_DIR, f"{timestamp}_montage.png"),
            'tiles_dir': tile_dir,
        }

        grid_img.save(paths['grid'])
        montage.save(paths['montage'])

        # screenshot_path.md更新
        with open(SCREENSHOT_PATH_FILE, 'w') as f:
            f.write(f"# 最新スクリーンショット\n\n")
            f.write(f"timestamp: {timestamp}\n")
            for k, v in paths.items():
                f.write(f"{k}: {v}\n")

        print(f"✅ {timestamp} (グリッド1枚 + 24タイル)")

        # 古いセット削除
        deleted = cleanup_old()
        if deleted:
            print(f"🗑️  削除: {len(deleted)}セット")

        return paths

    except Exception as e:
        print(f"❌ 失敗: {e}")
        return None


def list_screenshots():
    """保持中のセット一覧"""
    ensure_dir()
    sets = get_sorted_sets()

    if not sets:
        print("📂 スクリーンショットなし")
        return

    print(f"📂 保持中: {len(sets)}/{MAX_KEEP}セット")
    for ts in sets:
        grid_path = os.path.join(SCREENSHOT_DIR, f"{ts}_grid.png")
        if os.path.exists(grid_path):
            size_kb = os.path.getsize(grid_path) / 1024
            print(f"   {ts} ({size_kb:.0f}KB)")


def auto_capture(interval=5):
    """自動撮影モード"""
    print(f"🔄 自動撮影開始（{interval}秒間隔・{MAX_KEEP}セット保持・3枚/セット）")
    print("   Ctrl+C で停止")

    running = [True]

    def signal_handler(sig, frame):
        running[0] = False
        print("\n⏹️  停止")

    signal.signal(signal.SIGINT, signal_handler)

    count = 0
    while running[0]:
        count += 1
        take_screenshot()

        for _ in range(interval):
            if not running[0]:
                break
            time.sleep(1)

    print(f"✅ 合計 {count} セット撮影")


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "--list":
            list_screenshots()
        elif sys.argv[1] == "--once":
            take_screenshot()
        elif sys.argv[1] == "--help":
            print(__doc__)
        else:
            try:
                interval = int(sys.argv[1])
                auto_capture(interval)
            except ValueError:
                print(f"❌ 不明: {sys.argv[1]}")
    else:
        auto_capture()


if __name__ == "__main__":
    main()
