# VLM Grid Focus Toolkit
**Improve VLM Image Recognition Accuracy with Dynamic Grid Focus**

> Two-stage recognition: Overview first, then detailed focus
> Same approach as human visual cognition to enhance VLM accuracy

[日本語README](./README.md)

---

## What This Toolkit Solves

- **VLM Recognition Accuracy**: See details invisible in full-screen images via grid focus
- **CLI/Automation Ready**: Specify tile numbers programmatically
- **Differential Detection**: Automatically focus on changed areas

---

## The Problem: Full-Screen Images Miss Details

When you show VLMs (GPT-4V, Claude, etc.) a 1920x1080 full-screen:
- Small button text is unreadable
- Fine UI elements go unrecognized
- VLM knows "where things are" but not "what they say"

**Humans work the same way.** You can't read small text by glancing at the whole screen. You need to focus on specific areas.

### Solution: Two-Stage Recognition

1. **Overview**: One full-screen image to understand layout
2. **Grid Selection**: Choose tile numbers for areas needing detail
3. **Focused Recognition**: 2-3 focused tiles for detailed understanding

```
Full-screen only → Blurry recognition
Full-screen + 2-3 focused tiles → Detailed recognition
```

**Note**: This increases the number of images sent (more cost), but significantly improves recognition accuracy.

---

## 24-Grid Division

Screen divided into 6x4 = 24 tiles. Specify regions by tile number.

```
+------+------+------+------+------+------+
|  1   |  2   |  3   |  4   |  5   |  6   |
+------+------+------+------+------+------+
|  7   |  8   |  9   | 10   | 11   | 12   |
+------+------+------+------+------+------+
| 13   | 14   | 15   | 16   | 17   | 18   |
+------+------+------+------+------+------+
| 19   | 20   | 21   | 22   | 23   | 24   |
+------+------+------+------+------+------+
```

1 tile = 320x270px (for 1920x1080 screen)

---

## Components

### 1. Screen Capture 24Grid (`screen_capture_24grid.py`)
**Purpose**: Divide screen into 24 tiles, capture specified ones

**Features**:
- Tile number specification (top-left=1, bottom-right=24)
- Single or multiple tile selection
- Optional overview image output

**Usage**:
```bash
# Overview + tiles 8,9 (upper center) for detail
python screen_capture_24grid.py --overview --tiles 8,9
```

### 2. Screen Diff Detector (`screen_diff_detector.py`)
**Purpose**: Detect changes from previous screenshot, auto-select changed tiles

**Features**:
- Detect differences in 24-tile units
- Extract only changed tiles
- Auto-focus on "what changed"

**Usage**:
```bash
# Detect changes, focus on changed areas
python screen_diff_detector.py --threshold 0.05
```

### 3. OCR Text Locator (`ocr_text_locator.py`)
**Purpose**: Get text coordinates and identify which tile contains it

**Features**:
- OCR text detection
- Get screen coordinates of text
- Auto-identify "which tile has the Submit button"

**Usage**:
```bash
# Find which tile contains "Submit"
python ocr_text_locator.py --text "Submit"
```

---

## Design Philosophy: Human Visual Cognition

### Why 24 Tiles?

- **Human visual cognition**: Limited recognition area at once
- **Eye-tracking research**: Focus area is ~10-20% of screen
- **F-pattern**: Left-top → right → left-bottom scanning

VLMs work the same. Specifying "look here" gives better accuracy than showing everything.

### CLI/Automation Design

- **Number-based**: "Show tiles 8,9" in one command
- **Diff detection**: "Show only changed parts" automatically
- **Pipeline integration**: Combine with other CLI tools

---

## Practical Examples

### Case 1: Form Input Detail Recognition
```bash
# 1. Overview
python screen_capture_24grid.py --overview

# 2. VLM: "Form is in center (tiles 13, 14)"

# 3. Detailed focus
python screen_capture_24grid.py --tiles 13,14

# 4. VLM: "Name field placeholder is 'John Doe'"
#    (Detail invisible in full-screen now visible)
```

### Case 2: Auto-Focus on Changes
```bash
# 1. Detect diff
python screen_diff_detector.py --threshold 0.05

# 2. Output: "Tiles 14, 15 changed"

# 3. Focus on changes only
python screen_capture_24grid.py --tiles 14,15
```

### Case 3: Text-Specific Detail Check
```bash
# 1. Locate "Submit" button
python ocr_text_locator.py --text "Submit"

# Output: Found in tile 18

# 2. Detail check
python screen_capture_24grid.py --tiles 18

# 3. VLM: "Submit button is enabled (not grayed out)"
```

---

## Installation

### Requirements
- Python 3.8+
- macOS / Linux / Windows

### Dependencies
```bash
pip install pillow numpy opencv-python pytesseract
```

### Tesseract OCR Installation (for OCR usage)
```bash
# macOS
brew install tesseract

# Ubuntu/Debian
sudo apt-get install tesseract-ocr

# Windows
# Install from https://github.com/UB-Mannheim/tesseract/wiki
```

---

## License

MIT License

---

## Contributing

Issues and Pull Requests welcome.

---

**Developer**: TAKAWASI
**Site**: https://takawasi-social.com/tech/vlm-token-optimization.html

---

*"Overview first, then focus on details. Just like human eyes."*
