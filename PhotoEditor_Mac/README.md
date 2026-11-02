# Photos Editor for macOS

A native, hardware-accelerated macOS image editing application reverse-engineered and ported from the Windows 11 Microsoft Photos app package (`Microsoft.Windows.Photos` 2026.11090.22001.0).

---

## 🌟 Features Ported & Re-Engineered

- **Crop & Rotate**:
  - Freeform and fixed aspect ratios: `1:1 Square`, `16:9`, `9:16`, `4:3`, `3:4`, `3:2`, `2:3`, `5:4`, `4:5`, `5:7`, `7:5`.
  - Fine-angle straighten slider with visual alignment grid.
  - 90° Clockwise / Counter-Clockwise rotation and horizontal/vertical flipping.
- **Adjustments (WebGL Shader Pipeline)**:
  - Exposure & Brightness
  - Contrast
  - Highlights & Shadows
  - Vignette
  - Warmth (Color Temperature) & Tint
  - Saturation & Clarity
- **Preset Filters**:
  - Auto Enhance (Contrast stretching and histogram equalization)
  - Vivid, Warm, Cool, B&W (Monochrome), and Film (ACES filmic tone curve).
- **Markup & Inking**:
  - Ballpoint Pen, Calligraphy Brush, Translucent Highlighter, and Eraser with full palette and stroke size controls.
- **Retouch / Spot Fix (WebAssembly)**:
  - Runs the original C++ texture inpainting engine compiled to WebAssembly (`completion.wasm.bin`) inside a dedicated Web Worker (`SpotFix.worker.worker.js`).
  - Seamlessly erases blemishes, spots, and unwanted objects without degrading photo resolution.
- **Resize Dialog**:
  - Custom pixel resolution or percentage scaling with aspect ratio locking.
- **Undo / Redo History**:
  - Complete multi-step undo and redo state stack.

---

## 🖥️ macOS Native Integration

- **Native AppKit Shell**:
  - Full-size content view with transparent title bar matching macOS Dark Mode.
  - Native macOS Menu Bar:
    - **File**: *Open Photo...* (`⌘O`), *Save* (`⌘S`), *Save As Copy...* (`⇧⌘S`), *Close Window* (`⌘W`)
    - **Edit**: *Undo* (`⌘Z`), *Redo* (`⇧⌘Z`)
    - **View**: *Actual Size 100%* (`⌘1`), *Fit to Window* (`⌘0`), *Zoom In* (`⌘=`), *Zoom Out* (`⌘-`), *Full Screen* (`⌘F`)
- **Drag & Drop**:
  - Drag and drop any image file directly into the app window or onto the Dock icon.
- **Broad Format Support via CoreGraphics**:
  - Apple HEIC / HEIF, DSLR Camera RAW (`.cr2`, `.cr3`, `.nef`, `.arw`, `.dng`), WebP, PNG, JPEG, TIFF, BMP, and GIF.
- **Memory Footprint**:
  - Extremely lightweight (~80 MB RAM vs 300+ MB for Electron).

---

## 🚀 How to Run

Double-click `Photos Editor.app` in Finder, or run from Terminal:

```bash
open "Photos Editor.app"
```

To open an image directly:

```bash
open -a "Photos Editor.app" /path/to/your/photo.jpg
```

---

## 🛠️ Rebuilding the App

If you make any changes to the Swift app or Web layer, rebuild with:

```bash
./PhotoEditor_Mac/build.sh
```
