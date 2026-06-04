from __future__ import annotations

import argparse
import ctypes
import io
import random
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QPoint, Qt, Signal
from PySide6.QtGui import QAction, QColor, QDragEnterEvent, QDropEvent, QFont, QIcon, QImage, QMouseEvent, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    from PIL import Image, ImageDraw, ImageOps
except ImportError as exc:
    raise SystemExit(
        "Playlist Cover Stitcher needs Pillow. Install it with: python -m pip install Pillow"
    ) from exc


APP_NAME = "Playlist Cover Stitcher"
APP_ICON = "assets/PlaylistCoverStitcher.ico"
ABOUT_TEXT = """Playlist Cover Stitcher
© 2026 strailico5327

Stitch four album covers into one image for local music players.

Licensed under GNU GPLv3."""
PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_SIZE = 1000
OUTPUT_TILE = OUTPUT_SIZE // 2
PREVIEW_TILE = 260
PREVIEW_SIZE = PREVIEW_TILE * 2
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
SUPPORTED_TYPES = "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff);;PNG (*.png);;JPEG (*.jpg *.jpeg);;All files (*.*)"


def resource_path(relative_path: str) -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_path / relative_path


def enable_high_dpi_support() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def is_image_path(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def collect_image_paths(paths: list[Path]) -> list[Path]:
    collected = []
    seen = set()
    for path in paths:
        if not path.exists():
            continue
        candidates = sorted(path.rglob("*")) if path.is_dir() else [path]
        for candidate in candidates:
            if not candidate.is_file() or not is_image_path(candidate):
                continue
            resolved = candidate.resolve()
            if resolved not in seen:
                collected.append(candidate)
                seen.add(resolved)
    return collected


def center_crop_square(image: Image.Image) -> Image.Image:
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    return image.crop((left, top, left + side, top + side))


def prepare_tile_from_image(image: Image.Image, tile_size: int = OUTPUT_TILE) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    image = center_crop_square(image)
    image = image.convert("RGBA")
    return image.resize((tile_size, tile_size), Image.Resampling.LANCZOS)


def prepare_tile(path: Path, tile_size: int = OUTPUT_TILE) -> Image.Image:
    with Image.open(path) as image:
        return prepare_tile_from_image(image, tile_size)


def compose_grid(tiles: list[Image.Image | None], output_path: Path) -> None:
    if len(tiles) != 4 or any(tile is None for tile in tiles):
        raise ValueError("Four images are required before exporting.")
    output = Image.new("RGBA", (OUTPUT_SIZE, OUTPUT_SIZE), (255, 255, 255, 255))
    positions = ((0, 0), (OUTPUT_TILE, 0), (0, OUTPUT_TILE), (OUTPUT_TILE, OUTPUT_TILE))
    for tile, position in zip(tiles, positions):
        output.paste(tile, position)
    output.save(output_path, "PNG")


def image_to_pixmap(image: Image.Image) -> QPixmap:
    image = image.convert("RGBA")
    data = image.tobytes("raw", "RGBA")
    qimage = QImage(data, image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimage.copy())


def qimage_to_pil(image: QImage) -> Image.Image:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    data = bytes(buffer.data())
    buffer.close()
    return Image.open(io.BytesIO(data)).copy()


class GridCanvas(QWidget):
    tile_clicked = Signal(int)
    tiles_swapped = Signal(int, int)
    menu_requested = Signal(int, QPoint)

    def __init__(self, owner: "PlaylistCoverStitcher") -> None:
        super().__init__()
        self.owner = owner
        self.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self.setAcceptDrops(True)
        self.drag_start_index: int | None = None
        self.drag_start_xy: QPoint | None = None

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        palette = self.palette()
        base_color = palette.color(QPalette.ColorRole.Base)
        empty_color = palette.color(QPalette.ColorRole.AlternateBase)
        border_color = palette.color(QPalette.ColorRole.Mid)
        muted_color = palette.color(QPalette.ColorRole.Mid)
        text_color = palette.color(QPalette.ColorRole.Text)

        painter.fillRect(self.rect(), base_color)
        painter.setPen(QPen(border_color, 1))
        pixel_ratio = max(self.devicePixelRatioF(), 1.0)
        render_tile = max(PREVIEW_TILE, int(PREVIEW_TILE * pixel_ratio))

        for index in range(4):
            row = index // 2
            col = index % 2
            x = col * PREVIEW_TILE
            y = row * PREVIEW_TILE
            rect = self.rect().adjusted(x, y, x - (PREVIEW_SIZE - PREVIEW_TILE), y - (PREVIEW_SIZE - PREVIEW_TILE))

            tile = self.owner.tiles[index]
            if tile is not None:
                preview = tile.resize((render_tile, render_tile), Image.Resampling.LANCZOS)
                pixmap = image_to_pixmap(preview)
                pixmap.setDevicePixelRatio(pixel_ratio)
                painter.drawPixmap(x, y, pixmap)
                painter.drawRect(x, y, PREVIEW_TILE, PREVIEW_TILE)
                continue

            painter.fillRect(x, y, PREVIEW_TILE, PREVIEW_TILE, empty_color)
            painter.drawRect(x, y, PREVIEW_TILE, PREVIEW_TILE)
            number_font = QFont("Segoe UI Variable Display", 26, QFont.Weight.Bold)
            painter.setFont(number_font)
            painter.setPen(muted_color)
            painter.drawText(rect.adjusted(0, -36, 0, -18), Qt.AlignmentFlag.AlignCenter, str(index + 1))
            label_font = QFont("Segoe UI Variable Text", 11)
            painter.setFont(label_font)
            painter.setPen(text_color)
            painter.drawText(rect.adjusted(0, 22, 0, 0), Qt.AlignmentFlag.AlignCenter, "Click, drop, or paste")
            painter.setPen(QPen(border_color, 1))

    def cell_from_xy(self, x: int, y: int) -> int | None:
        if not (0 <= x < PREVIEW_SIZE and 0 <= y < PREVIEW_SIZE):
            return None
        return int((y // PREVIEW_TILE) * 2 + (x // PREVIEW_TILE))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_index = self.cell_from_xy(int(event.position().x()), int(event.position().y()))
            self.drag_start_xy = event.position().toPoint()
        elif event.button() == Qt.MouseButton.RightButton:
            index = self.cell_from_xy(int(event.position().x()), int(event.position().y()))
            if index is not None:
                self.menu_requested.emit(index, event.globalPosition().toPoint())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        start_index = self.drag_start_index
        start_xy = self.drag_start_xy
        self.drag_start_index = None
        self.drag_start_xy = None
        if start_index is None or start_xy is None:
            return
        end_index = self.cell_from_xy(int(event.position().x()), int(event.position().y()))
        if end_index is None:
            return
        moved = abs(event.position().x() - start_xy.x()) + abs(event.position().y() - start_xy.y())
        if moved >= 16 and end_index != start_index:
            self.tiles_swapped.emit(start_index, end_index)
            return
        self.tile_clicked.emit(start_index)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            position = event.position().toPoint()
            self.owner.handle_drop(paths, position.x(), position.y())
            event.acceptProposedAction()
        else:
            event.ignore()


class PlaylistCoverStitcher(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(720, 800)
        self.setMinimumSize(660, 780)
        self.setAcceptDrops(True)

        self.tiles: list[Image.Image | None] = [None, None, None, None]
        self.paths: list[Path | None] = [None, None, None, None]
        self.context_index = 0

        self._build_ui()
        self._apply_styles()
        self.status_label.setText("Click, drag files, right-click paste, or press Ctrl+V.")

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(32, 24, 32, 12)
        main_layout.setSpacing(12)

        title = QLabel(APP_NAME)
        title.setObjectName("titleLabel")
        main_layout.addWidget(title)

        center = QHBoxLayout()
        center.addStretch()
        self.canvas = GridCanvas(self)
        self.canvas.tile_clicked.connect(self.pick_image)
        self.canvas.tiles_swapped.connect(self.swap_grid_tiles)
        self.canvas.menu_requested.connect(self.show_context_menu)
        center.addWidget(self.canvas)
        center.addStretch()
        main_layout.addLayout(center)

        controls = QHBoxLayout()
        export_button = QPushButton("Export PNG")
        export_button.setObjectName("actionButton")
        export_button.clicked.connect(self.export_png)
        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(self.clear)
        shuffle_button = QPushButton("Shuffle")
        shuffle_button.clicked.connect(self.shuffle_grid)
        controls.addWidget(export_button)
        controls.addWidget(clear_button)
        controls.addWidget(shuffle_button)
        controls.addStretch()
        main_layout.addLayout(controls)

        main_layout.addStretch()
        self.status_label = QLabel()
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)

        footer_controls = QHBoxLayout()
        self.about_button = QPushButton("ⓘ")
        self.about_button.setObjectName("aboutButton")
        self.about_button.setToolTip("About")
        self.about_button.clicked.connect(self.show_about)
        footer_controls.addStretch()
        footer_controls.addWidget(self.about_button)
        main_layout.addLayout(footer_controls)

        paste_action = QAction(self)
        paste_action.setShortcut("Ctrl+V")
        paste_action.triggered.connect(self.paste_shortcut)
        self.addAction(paste_action)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: palette(window);
                color: palette(window-text);
                font-family: "Segoe UI Variable Text", "Segoe UI";
                font-size: 10pt;
            }
            QLabel#titleLabel {
                font-family: "Segoe UI Variable Display", "Segoe UI";
                font-size: 22pt;
                font-weight: 700;
            }
            GridCanvas {
                background: palette(base);
                border: 1px solid palette(mid);
            }
            QPushButton {
                padding: 8px 16px;
            }
            QPushButton#actionButton {
                font-weight: 700;
            }
            QPushButton#aboutButton {
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
                padding: 0;
                border-radius: 14px;
                font-size: 13pt;
            }
            QLabel#statusLabel {
                color: palette(window-text);
            }
            """
        )

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.random_fill_empty_tiles(collect_image_paths([Path(path) for path in paths]))
            event.acceptProposedAction()
        else:
            event.ignore()

    def pick_image(self, index: int) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, f"Choose image for grid {index + 1}", "", SUPPORTED_TYPES)
        if file_path:
            self.load_image(Path(file_path), index)

    def show_context_menu(self, index: int, global_position: QPoint) -> None:
        self.context_index = index
        menu = QMenu(self)
        paste_action = menu.addAction(f"Paste into Grid {index + 1}")
        delete_action = menu.addAction(f"Delete Grid {index + 1}")
        selected = menu.exec(global_position)
        if selected == paste_action:
            self.paste_context_tile()
        elif selected == delete_action:
            self.delete_context_tile()

    def paste_context_tile(self) -> None:
        items = self.clipboard_items()
        if not items:
            self.status_label.setText("Clipboard has no image or copied image file.")
            return
        self.load_clipboard_item(items[0], self.context_index)

    def delete_context_tile(self) -> None:
        index = self.context_index
        if self.tiles[index] is None:
            self.status_label.setText(f"Grid {index + 1} is already empty.")
            return
        self.tiles[index] = None
        self.paths[index] = None
        self.status_label.setText(f"Deleted image from Grid {index + 1}.")
        self.canvas.update()

    def paste_shortcut(self) -> None:
        items = self.clipboard_items()
        if not items:
            self.status_label.setText("Clipboard has no image or copied image file.")
            return
        pointer = self.canvas.mapFromGlobal(self.cursor().pos())
        index = self.canvas.cell_from_xy(pointer.x(), pointer.y())
        if index is None:
            self.status_label.setText("Move the mouse over a grid tile, then press Ctrl+V.")
            return
        self.load_clipboard_item(items[0], index)

    def clipboard_items(self) -> list[Path | Image.Image]:
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime.hasImage():
            image = clipboard.image()
            if not image.isNull():
                return [qimage_to_pil(image)]
        if mime.hasUrls():
            return [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile() and is_image_path(Path(url.toLocalFile()))]
        text = clipboard.text()
        return [Path(line.strip().strip('"')) for line in text.splitlines() if is_image_path(Path(line.strip().strip('"')))]

    def load_clipboard_item(self, item: Path | Image.Image, index: int) -> bool:
        try:
            if isinstance(item, Image.Image):
                tile = prepare_tile_from_image(item)
                label = "clipboard image"
                path = None
            else:
                tile = prepare_tile(item)
                label = item.name
                path = item
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not paste image:\n{exc}")
            return False
        self.tiles[index] = tile
        self.paths[index] = path
        self.status_label.setText(f"Grid {index + 1} pasted: {label}")
        self.canvas.update()
        return True

    def handle_drop(self, paths: list[str], canvas_x: int, canvas_y: int) -> None:
        image_paths = collect_image_paths([Path(path) for path in paths])
        if not image_paths:
            self.status_label.setText("No supported image files were dropped.")
            return
        if len(image_paths) > 1:
            self.random_fill_empty_tiles(image_paths)
            return

        index = self.canvas.cell_from_xy(canvas_x, canvas_y)
        if index is None:
            index = self.first_empty_index()
        if index is None:
            self.status_label.setText("All four grid tiles are filled.")
            return
        self.load_image(image_paths[0], index)

    def random_fill_empty_tiles(self, image_paths: list[Path]) -> int:
        if not image_paths:
            self.status_label.setText("No supported image files were dropped.")
            return 0
        empty_slots = [index for index, tile in enumerate(self.tiles) if tile is None]
        if not empty_slots:
            self.status_label.setText("All four grid tiles are filled. Clear a tile or click Shuffle.")
            return 0
        random.shuffle(empty_slots)
        random.shuffle(image_paths)
        loaded = 0
        for index, path in zip(empty_slots, image_paths):
            if self.load_image(path, index, redraw=False, show_errors=False):
                loaded += 1
        self.canvas.update()
        self.status_label.setText(f"Randomly placed {loaded} image(s) into empty grid tiles.")
        return loaded

    def first_empty_index(self) -> int | None:
        for index, tile in enumerate(self.tiles):
            if tile is None:
                return index
        return None

    def load_image(self, path: Path, index: int, redraw: bool = True, show_errors: bool = True) -> bool:
        try:
            tile = prepare_tile(path)
        except Exception as exc:
            if show_errors:
                QMessageBox.critical(self, APP_NAME, f"Could not load image:\n{path}\n\n{exc}")
            return False
        self.tiles[index] = tile
        self.paths[index] = path
        self.status_label.setText(f"Grid {index + 1} loaded: {path.name}")
        if redraw:
            self.canvas.update()
        return True

    def swap_grid_tiles(self, first_index: int, second_index: int) -> None:
        if self.tiles[first_index] is None or self.tiles[second_index] is None:
            self.status_label.setText("Drag between two filled grid tiles to swap them.")
            return
        self.tiles[first_index], self.tiles[second_index] = self.tiles[second_index], self.tiles[first_index]
        self.paths[first_index], self.paths[second_index] = self.paths[second_index], self.paths[first_index]
        self.status_label.setText(f"Swapped Grid {first_index + 1} and Grid {second_index + 1}.")
        self.canvas.update()

    def shuffle_grid(self) -> None:
        if any(tile is None for tile in self.tiles):
            self.status_label.setText("Load all four grid images before shuffling.")
            return
        combined = list(zip(self.tiles, self.paths))
        original_paths = [path for _, path in combined]
        random.shuffle(combined)
        if [path for _, path in combined] == original_paths:
            combined = combined[1:] + combined[:1]
        self.tiles = [tile for tile, _ in combined]
        self.paths = [path for _, path in combined]
        self.status_label.setText("Shuffled all four grid images.")
        self.canvas.update()

    def export_png(self) -> None:
        if any(tile is None for tile in self.tiles):
            self.status_label.setText("Upload all four images before exporting.")
            QMessageBox.warning(self, APP_NAME, "Upload all four images before exporting.")
            return
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save playlist cover",
            "playlist-cover.png",
            "PNG (*.png)",
        )
        if not output_path:
            return
        compose_grid(self.tiles, Path(output_path))
        self.status_label.setText(f"Exported 1000x1000 PNG: {Path(output_path).name}")

    def clear(self) -> None:
        self.tiles = [None, None, None, None]
        self.paths = [None, None, None, None]
        self.status_label.setText("Cleared. Click, drag files, right-click paste, or press Ctrl+V.")
        self.canvas.update()

    def show_about(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(APP_NAME)
        dialog.setModal(True)
        dialog.setMinimumWidth(360)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(16)

        text = QLabel(ABOUT_TEXT)
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        ok_button = QPushButton("OK")
        ok_button.clicked.connect(dialog.accept)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(ok_button)
        button_row.addStretch()

        layout.addWidget(text)
        layout.addLayout(button_row)

        dialog.exec()

    def run(self) -> None:
        self.show()
        QApplication.instance().exec()


def run_self_test() -> Path:
    output_dir = PROJECT_ROOT / "smoke_test_output"
    output_dir.mkdir(exist_ok=True)
    specs = [
        ((3000, 4000), "#e9573f", "3000x4000"),
        ((4200, 3000), "#2f80ed", "4200x3000"),
        ((1800, 1800), "#27ae60", "1800x1800"),
        ((1200, 2000), "#f2c94c", "1200x2000"),
    ]
    paths = []
    for index, (size, color, label) in enumerate(specs, start=1):
        image = Image.new("RGB", size, color)
        draw = ImageDraw.Draw(image)
        draw.rectangle((size[0] // 4, size[1] // 4, size[0] * 3 // 4, size[1] * 3 // 4), outline="white", width=24)
        draw.text((80, 80), f"Tile {index}\n{label}", fill="white")
        path = output_dir / f"sample_{index}.png"
        image.save(path, "PNG")
        paths.append(path)

    output_path = output_dir / "playlist-cover-smoke.png"
    compose_grid([prepare_tile(path) for path in paths], output_path)
    with Image.open(output_path) as output:
        if output.size != (OUTPUT_SIZE, OUTPUT_SIZE):
            raise AssertionError(f"Expected {OUTPUT_SIZE}x{OUTPUT_SIZE}, got {output.size}")
    return output_path


def check_dnd() -> None:
    print(f"Python: {sys.executable}")
    print("Qt drag-drop: built in")


def main() -> None:
    enable_high_dpi_support()
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--self-test", action="store_true", help="generate sample inputs and a test PNG")
    parser.add_argument("--check-dnd", action="store_true", help="check drag-drop availability")
    args = parser.parse_args()
    if args.self_test:
        print(f"Smoke test OK: {run_self_test()}")
        return
    if args.check_dnd:
        check_dnd()
        return
    app = QApplication(sys.argv)
    app_icon = QIcon(str(resource_path(APP_ICON)))
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    window = PlaylistCoverStitcher()
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
