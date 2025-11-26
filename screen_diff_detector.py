#!/usr/bin/env python3
"""
画面差分検知・タイル選択ツール
- 前回タイル群 vs 今回タイル群で差分検出
- 変化タイルリスト + 色メタデータ出力
- LLMトークン節約（変化タイルだけ読む）

使い方:
    python3 画面差分検知_タイル選択_トークン節約.py --current /path/to/tiles
    python3 画面差分検知_タイル選択_トークン節約.py --current /path/to/tiles --prev /path/to/prev_tiles
    python3 画面差分検知_タイル選択_トークン節約.py --auto  # 自動で最新2つを比較

出力:
    - diff_report.md: 変化タイルリスト + 色メタデータ
    - JSON形式オプション（--json）
"""

import os
import sys
import argparse
import json
import glob
import shutil
from datetime import datetime
from PIL import Image
from collections import Counter

SCREENSHOT_DIR = os.path.expanduser("~/Generalstab/VLA_screenshots")
TILE_CACHE_DIR = os.path.expanduser("~/Generalstab/SharedReminders/vla/tile_cache")
DIFF_REPORT_PATH = os.path.expanduser("~/Generalstab/SharedReminders/vla/diff_report.md")


def compute_dhash(img: Image.Image, hash_size: int = 8) -> int:
    """
    差分ハッシュ（dHash）計算 - PIL自前実装
    隣接ピクセルの明暗比較で64bitハッシュ生成
    """
    # リサイズ（hash_size+1 x hash_size）
    img = img.convert('L').resize((hash_size + 1, hash_size), Image.LANCZOS)
    pixels = list(img.getdata())

    # 隣接ピクセル比較でビット列生成
    diff = []
    for row in range(hash_size):
        for col in range(hash_size):
            left = pixels[row * (hash_size + 1) + col]
            right = pixels[row * (hash_size + 1) + col + 1]
            diff.append(1 if left > right else 0)

    # ビット列を整数に変換
    return int(''.join(map(str, diff)), 2)


def hamming_distance(hash1: int, hash2: int) -> int:
    """ハミング距離（異なるビット数）"""
    return bin(hash1 ^ hash2).count('1')


def compute_histogram(img: Image.Image) -> dict:
    """色ヒストグラム計算（RGB各256bin）"""
    img = img.convert('RGB')
    r, g, b = img.split()
    return {
        'r': r.histogram(),
        'g': g.histogram(),
        'b': b.histogram()
    }


def histogram_diff(hist1: dict, hist2: dict) -> float:
    """ヒストグラム差分（0.0-1.0）"""
    total_diff = 0
    total_pixels = 0
    for channel in ['r', 'g', 'b']:
        for i in range(256):
            total_diff += abs(hist1[channel][i] - hist2[channel][i])
            total_pixels += hist1[channel][i] + hist2[channel][i]
    return total_diff / max(total_pixels, 1)


def get_dominant_colors(img: Image.Image, n: int = 3) -> list:
    """支配色抽出（上位n色）"""
    img = img.convert('RGB').resize((50, 50), Image.LANCZOS)  # 縮小で高速化
    pixels = list(img.getdata())

    # 色を16段階に量子化（4096色に削減）
    quantized = []
    for r, g, b in pixels:
        qr, qg, qb = r // 16, g // 16, b // 16
        quantized.append((qr * 16, qg * 16, qb * 16))

    counter = Counter(quantized)
    top_colors = counter.most_common(n)

    return [f"#{r:02X}{g:02X}{b:02X}" for (r, g, b), _ in top_colors]


def get_brightness(img: Image.Image) -> float:
    """平均輝度（0.0-1.0）"""
    img = img.convert('L')
    pixels = list(img.getdata())
    return sum(pixels) / (len(pixels) * 255)


def get_color_ratio(img: Image.Image) -> dict:
    """明暗比率"""
    brightness = get_brightness(img)
    img = img.convert('L')
    pixels = list(img.getdata())
    dark = sum(1 for p in pixels if p < 85) / len(pixels)
    mid = sum(1 for p in pixels if 85 <= p < 170) / len(pixels)
    light = sum(1 for p in pixels if p >= 170) / len(pixels)
    return {'dark': round(dark, 2), 'mid': round(mid, 2), 'light': round(light, 2)}


def analyze_tile(img_path: str) -> dict:
    """タイル分析（色メタデータ生成）"""
    img = Image.open(img_path)
    return {
        'dominant_colors': get_dominant_colors(img),
        'color_ratio': get_color_ratio(img),
        'brightness': round(get_brightness(img), 2)
    }


def find_tile_dirs():
    """最新2つのタイルディレクトリを取得"""
    pattern = os.path.join(SCREENSHOT_DIR, "*_tiles")
    dirs = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if len(dirs) >= 2:
        return dirs[1], dirs[0]  # prev, current
    elif len(dirs) == 1:
        return None, dirs[0]
    return None, None


def list_tiles(tile_dir: str) -> list:
    """タイルファイル一覧"""
    pattern = os.path.join(tile_dir, "tile_r*_c*.png")
    return sorted(glob.glob(pattern))


def compare_tiles(prev_dir: str, curr_dir: str,
                  dhash_threshold: int = 3,
                  histogram_threshold: float = 0.05) -> dict:
    """タイル比較（差分検出）"""
    results = {
        'changed': [],
        'unchanged': [],
        'details': {}
    }

    curr_tiles = list_tiles(curr_dir)

    for tile_path in curr_tiles:
        tile_name = os.path.basename(tile_path)
        prev_path = os.path.join(prev_dir, tile_name) if prev_dir else None

        # タイル名からr,c抽出
        import re
        m = re.match(r'tile_r(\d+)_c(\d+)\.png', tile_name)
        if not m:
            continue
        tile_id = f"r{m.group(1)}_c{m.group(2)}"

        curr_img = Image.open(tile_path)
        curr_meta = analyze_tile(tile_path)

        if prev_path and os.path.exists(prev_path):
            prev_img = Image.open(prev_path)

            # dHash比較
            curr_hash = compute_dhash(curr_img)
            prev_hash = compute_dhash(prev_img)
            dhash_diff = hamming_distance(curr_hash, prev_hash)

            # ヒストグラム比較
            curr_hist = compute_histogram(curr_img)
            prev_hist = compute_histogram(prev_img)
            hist_diff = histogram_diff(curr_hist, prev_hist)

            # 変化判定
            is_changed = dhash_diff > dhash_threshold or hist_diff > histogram_threshold

            results['details'][tile_id] = {
                **curr_meta,
                'dhash_diff': dhash_diff,
                'histogram_diff': round(hist_diff, 4),
                'changed': is_changed
            }

            if is_changed:
                results['changed'].append(tile_id)
            else:
                results['unchanged'].append(tile_id)
        else:
            # 前回なし = 新規（変化扱い）
            results['details'][tile_id] = {
                **curr_meta,
                'dhash_diff': None,
                'histogram_diff': None,
                'changed': True,
                'new': True
            }
            results['changed'].append(tile_id)

    return results


def update_cache(curr_dir: str):
    """キャッシュ更新（前回タイル保存）"""
    os.makedirs(TILE_CACHE_DIR, exist_ok=True)

    # 古いキャッシュ削除
    for f in glob.glob(os.path.join(TILE_CACHE_DIR, "*.png")):
        os.remove(f)

    # 新しいタイルをコピー
    for tile_path in list_tiles(curr_dir):
        tile_name = os.path.basename(tile_path)
        shutil.copy2(tile_path, os.path.join(TILE_CACHE_DIR, tile_name))


def generate_report(results: dict, curr_dir: str) -> str:
    """diff_report.md生成"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    report = f"""# 差分レポート
- 時刻: {ts}
- 現在タイル: {curr_dir}
- 変化タイル: {results['changed']}
- 無変化タイル: {len(results['unchanged'])}件

## 変化タイル詳細
"""

    for tile_id in results['changed']:
        detail = results['details'].get(tile_id, {})
        dom_colors = ', '.join(detail.get('dominant_colors', []))
        ratio = detail.get('color_ratio', {})
        brightness = detail.get('brightness', 0)
        dhash = detail.get('dhash_diff', '?')
        hist = detail.get('histogram_diff', '?')

        # 状態推定
        estimation = ""
        if ratio.get('dark', 0) > 0.7:
            estimation = "暗背景（コード/ターミナル領域）"
        elif ratio.get('light', 0) > 0.7:
            estimation = "明背景（ダイアログ/入力欄）"
        if any('FF0000' in c or 'E00000' in c or 'D00000' in c for c in detail.get('dominant_colors', [])):
            estimation += " ⚠️赤色検出（エラー可能性）"

        report += f"""
### {tile_id}
- 差分: dHash={dhash}bit, histogram={hist}
- 支配色: {dom_colors}
- 明暗比: dark={ratio.get('dark', 0)}, light={ratio.get('light', 0)}
- 輝度: {brightness}
- 推定: {estimation or '通常'}
"""

    # 推奨読み込み
    report += f"""
## 推奨読み込み
- 必須: {results['changed'][:5]}
- 任意: {results['changed'][5:] if len(results['changed']) > 5 else 'なし'}
- スキップ: 他{len(results['unchanged'])}件
"""

    return report


def main():
    parser = argparse.ArgumentParser(description='画面差分検知・タイル選択')
    parser.add_argument('--current', '-c', help='現在タイルディレクトリ')
    parser.add_argument('--prev', '-p', help='前回タイルディレクトリ')
    parser.add_argument('--auto', '-a', action='store_true', help='自動で最新2つを比較')
    parser.add_argument('--cache', action='store_true', help='キャッシュと比較')
    parser.add_argument('--json', '-j', action='store_true', help='JSON形式出力')
    parser.add_argument('--dhash-threshold', type=int, default=3, help='dHash閾値')
    parser.add_argument('--hist-threshold', type=float, default=0.05, help='ヒストグラム閾値')
    args = parser.parse_args()

    # ディレクトリ決定
    if args.auto:
        prev_dir, curr_dir = find_tile_dirs()
    elif args.cache:
        curr_dir = args.current
        prev_dir = TILE_CACHE_DIR if os.path.exists(TILE_CACHE_DIR) else None
    else:
        curr_dir = args.current
        prev_dir = args.prev

    if not curr_dir:
        print("❌ タイルディレクトリが指定されていません")
        print("使い方: --auto または --current /path/to/tiles")
        return

    if not os.path.exists(curr_dir):
        print(f"❌ ディレクトリが存在しません: {curr_dir}")
        return

    print(f"📊 差分検知開始")
    print(f"   現在: {curr_dir}")
    print(f"   前回: {prev_dir or 'なし（初回）'}")

    # 比較実行
    results = compare_tiles(
        prev_dir, curr_dir,
        dhash_threshold=args.dhash_threshold,
        histogram_threshold=args.hist_threshold
    )

    # 出力
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f"\n✅ 変化タイル: {len(results['changed'])}件")
        for tile_id in results['changed']:
            detail = results['details'].get(tile_id, {})
            dom = detail.get('dominant_colors', ['?'])[0]
            print(f"   - {tile_id}: 支配色{dom}, 輝度{detail.get('brightness', '?')}")

        print(f"⏭️ 無変化タイル: {len(results['unchanged'])}件（スキップ推奨）")

        # レポート生成
        report = generate_report(results, curr_dir)
        os.makedirs(os.path.dirname(DIFF_REPORT_PATH), exist_ok=True)
        with open(DIFF_REPORT_PATH, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n📝 レポート: {DIFF_REPORT_PATH}")

    # キャッシュ更新
    update_cache(curr_dir)
    print(f"💾 キャッシュ更新: {TILE_CACHE_DIR}")


if __name__ == '__main__':
    main()
