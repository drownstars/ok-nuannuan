"""Read-only dependency, asset, target-process, and local OCR diagnostics."""
import importlib.metadata
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import cv2
    import ok
    import psutil
    from PySide6 import QtCore
    from rapidocr import RapidOCR
    from nuannuan.config import make_config

    config = make_config()
    engine = RapidOCR(params=config['ocr']['params'])
    image = cv2.imread(str(ROOT / 'ok_templates/ButtonDigAgain.png'))
    result = engine(image)
    texts = list(result.txts or [])
    assert any('再次挖掘' in text for text in texts), f'OCR did not recognize supplied button: {texts}'
    data = {
        'python': sys.version.split()[0], 'framework': ok.__file__,
        'framework_version': importlib.metadata.version('ok-script'),
        'opencv': cv2.__version__, 'qt': QtCore.__version__,
        'ocr_local_model_test': texts,
        'game_running': any((p.info['name'] or '').lower() == 'x6game-win64-shipping.exe'
                            for p in psutil.process_iter(['name'])),
    }
    output = ROOT / 'logs/verification/doctor.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
