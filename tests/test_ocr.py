import unittest
from unittest.mock import patch

import cv2

from nuannuan.config import ROOT, make_config


class OfflineOCRTests(unittest.TestCase):
    def test_local_resources_recognize_supplied_button_without_downloading(self):
        from rapidocr import RapidOCR
        from rapidocr.utils.download_file import DownloadFile

        with patch.object(DownloadFile, 'run', side_effect=AssertionError('OCR attempted a download')):
            engine = RapidOCR(params=make_config()['ocr']['params'])
            image = cv2.imread(str(ROOT / 'ok_templates/ButtonDigAgain.png'))
            result = engine(image)
        self.assertIn('再次挖掘', ''.join(result.txts))
