#!/usr/bin/env python3
"""
OCR文字座標抽出ツール - スクショから文字列と座標を抽出

機能:
- screenshots/フォルダの最新N枚を処理
- 各画像でOCR実行（Tesseract）
- 検出文字列 + 中央座標を出力
- 画面座標系（左上0,0、右下1535x863）で返す
- 50%リサイズ画像を2倍して実座標に変換

使用方法:
    python3 ocr_text_coords.py              # 最新1枚を処理
    python3 ocr_text_coords.py --all        # 保持中の全枚（最大5枚）を処理
    python3 ocr_text_coords.py --search "文字列"  # 特定文字列を検索
    python3 ocr_text_coords.py --diff       # 時系列差分表示
"""

import os
import sys
import glob
import json
from datetime import datetime

# 画面解像度（実際のスクリーン）
SCREEN_WIDTH = 1535
SCREEN_HEIGHT = 863

# スクショ保存先
SCREENSHOT_DIR = os.path.expanduser("~/Generalstab/SCA/screenshots")

def get_sorted_screenshots():
    """タイムスタンプ順でスクショ一覧取得（新しい順）"""
    pattern = os.path.join(SCREENSHOT_DIR, "screenshot_*.png")
    files = glob.glob(pattern)
    files.sort(reverse=True)
    return files

def extract_text_coords(image_path):
    """画像からOCRで文字列と座標を抽出"""
    try:
        import pytesseract
        from PIL import Image
        from pytesseract import Output
    except ImportError:
        print("❌ 必要なライブラリがありません")
        print("   pip install pytesseract pillow")
        print("   sudo apt install tesseract-ocr tesseract-ocr-jpn")
        return None

    try:
        img = Image.open(image_path)
        img_width, img_height = img.size

        # スケール係数（50%リサイズ画像→実画面座標）
        scale_x = SCREEN_WIDTH / img_width
        scale_y = SCREEN_HEIGHT / img_height

        # 画像を2倍に拡大（OCR精度向上）
        img_enlarged = img.resize((img_width * 2, img_height * 2), Image.LANCZOS)

        # OCR実行（日本語+英語）
        d = pytesseract.image_to_data(
            img_enlarged,
            output_type=Output.DICT,
            lang='jpn+eng',
            config='--psm 6'  # Assume uniform block of text
        )

        results = []
        n_boxes = len(d['text'])

        for i in range(n_boxes):
            text = d['text'][i].strip()
            conf = d['conf'][i]

            # 空テキストや低信頼度はスキップ
            if not text or conf == -1 or conf < 50:
                continue

            # バウンディングボックス（拡大画像上の座標）
            x = d['left'][i]
            y = d['top'][i]
            w = d['width'][i]
            h = d['height'][i]

            # 中央座標（拡大画像→実画面座標に変換）
            # 拡大画像は2倍なので、2で割って元のスケールに戻す
            center_x = int((x + w / 2) / 2 * scale_x)
            center_y = int((y + h / 2) / 2 * scale_y)

            results.append({
                'text': text,
                'x': center_x,
                'y': center_y,
                'conf': int(conf),
                'width': int(w * scale_x),
                'height': int(h * scale_y)
            })

        return results

    except Exception as e:
        print(f"❌ OCRエラー: {e}")
        return None

def format_results(results, filename):
    """結果をフォーマット出力"""
    print(f"\n📸 {filename}")
    print("-" * 50)

    if not results:
        print("   (文字検出なし)")
        return

    # 座標順にソート（上から下、左から右）
    results.sort(key=lambda r: (r['y'], r['x']))

    for r in results:
        print(f"   \"{r['text']}\" : ({r['x']}, {r['y']})  [conf:{r['conf']}%]")

def search_text(results, query):
    """特定文字列を検索"""
    found = []
    for r in results:
        if query in r['text']:
            found.append(r)
    return found

def show_diff(all_results):
    """時系列差分表示"""
    if len(all_results) < 2:
        print("❌ 差分表示には2枚以上必要")
        return

    print("\n📊 時系列差分")
    print("=" * 50)

    # 各画像の文字列セット
    for i in range(len(all_results) - 1):
        newer = all_results[i]
        older = all_results[i + 1]

        newer_texts = {r['text'] for r in newer['results']}
        older_texts = {r['text'] for r in older['results']}

        added = newer_texts - older_texts
        removed = older_texts - newer_texts

        print(f"\n{newer['file']} vs {older['file']}")
        if added:
            print(f"   追加: {', '.join(added)}")
        if removed:
            print(f"   削除: {', '.join(removed)}")
        if not added and not removed:
            print("   (変化なし)")

def main():
    # オプション解析
    process_all = "--all" in sys.argv
    show_diff_flag = "--diff" in sys.argv
    search_query = None

    if "--search" in sys.argv:
        idx = sys.argv.index("--search")
        if idx + 1 < len(sys.argv):
            search_query = sys.argv[idx + 1]

    if "--help" in sys.argv:
        print(__doc__)
        return

    # スクショ取得
    files = get_sorted_screenshots()
    if not files:
        print("❌ スクリーンショットが見つかりません")
        print(f"   保存先: {SCREENSHOT_DIR}")
        return

    # 処理対象決定
    if process_all or show_diff_flag:
        target_files = files  # 全部（最大5枚）
    else:
        target_files = files[:1]  # 最新1枚

    print(f"🔍 OCR文字座標抽出")
    print(f"   画面解像度: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")
    print(f"   処理対象: {len(target_files)}枚")

    all_results = []

    for filepath in target_files:
        filename = os.path.basename(filepath)
        results = extract_text_coords(filepath)

        if results is None:
            continue

        if search_query:
            # 検索モード
            found = search_text(results, search_query)
            if found:
                print(f"\n📸 {filename} - 「{search_query}」検索結果:")
                for r in found:
                    print(f"   \"{r['text']}\" : ({r['x']}, {r['y']})")
        else:
            # 通常モード
            format_results(results, filename)

        all_results.append({
            'file': filename,
            'results': results
        })

    # 差分表示
    if show_diff_flag and len(all_results) >= 2:
        show_diff(all_results)

    # 簡易JSON出力（他ツール連携用）
    if "--json" in sys.argv and all_results:
        print("\n📋 JSON出力:")
        print(json.dumps(all_results[0]['results'], ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
