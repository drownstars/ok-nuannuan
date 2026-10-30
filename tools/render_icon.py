"""Render the editable app icon to PNG and a multi-resolution Windows ICO."""
import json
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QRectF
from PySide6.QtGui import QGuiApplication, QIcon, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]


def main():
    app = QGuiApplication.instance() or QGuiApplication([])
    source = ROOT / 'assets/app.svg'
    renderer = QSvgRenderer(str(source))
    assert renderer.isValid(), 'Invalid app icon SVG'
    output = ROOT / 'logs/verification/icon'
    output.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    for size in [*sizes, 1024]:
        pixels = QImage(size, size, QImage.Format_ARGB32)
        pixels.fill(0)
        painter = QPainter(pixels)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        target = ROOT / 'assets/app.png' if size == 1024 else output / f'icon-{size}.png'
        assert pixels.save(str(target))
        assert pixels.pixelColor(0, 0).alpha() == 0, 'Icon corners must remain transparent'
        assert pixels.pixelColor(size//2, size//2).alpha() == 255
    icon_path = ROOT / 'assets/app-momo.ico'
    with Image.open(ROOT / 'assets/app.png') as pixels:
        pixels.save(icon_path, sizes=[(size, size) for size in sizes])
    with Image.open(icon_path) as icon:
        assert icon.ico.sizes() == {(size, size) for size in sizes}
    svg_icon, windows_icon = QIcon(str(source)), QIcon(str(icon_path))
    assert not svg_icon.isNull() and not windows_icon.isNull()
    for size in sizes:
        assert not svg_icon.pixmap(size, size).isNull()
        assert not windows_icon.pixmap(size, size).isNull()
    result = {'passed': True, 'svg': str(source), 'png': str(ROOT/'assets/app.png'),
              'ico': str(icon_path), 'sizes': sizes}
    (output / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
