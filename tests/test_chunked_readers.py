"""Loading-only regressions: chunk bounds, coordinates and unchanged pixels."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '01_conversion_downsampling'))
import chunked_readers as readers
import WSI2OMEtif_All_file_types as multi


def pixels(width=53, height=37):
    y, x = np.indices((height, width))
    return np.stack((x * 3 % 256, y * 5 % 256, (x + y) * 7 % 256), -1).astype('uint8')


class ChunkedReaderTests(unittest.TestCase):
    def test_regions_cover_odd_edges_without_changing_rgb(self):
        data = pixels()
        calls = []
        def read(xy, size):
            calls.append((xy, size))
            x, y = xy
            w, h = size
            return Image.fromarray(data[y:y+h, x:x+w]).convert('RGBA')
        result = readers.read_rgb_chunks((53, 37), read, 16)
        np.testing.assert_array_equal(result, data)
        self.assertEqual(len(calls), 12)
        self.assertEqual(calls[-1], ((48, 32), (5, 5)))
        self.assertTrue(all(max(size) <= 16 for _, size in calls))

    def test_openslide_level_zero_coordinates(self):
        data = pixels()
        for downsample in (1, 4, 2.5):
            calls = []
            def read(xy, level, size):
                calls.append((xy, size))
                x, y = (int(v / downsample) for v in xy)
                w, h = size
                return Image.fromarray(data[y:y+h, x:x+w])
            slide = SimpleNamespace(level_dimensions=[(53, 37)],
                                    level_downsamples=[downsample], read_region=read)
            np.testing.assert_array_equal(readers.read_openslide_chunks(slide, 0, 16), data)
            self.assertEqual(calls[1][0], (int(16 * downsample), 0))

    def test_tiff_tiles_strips_and_orientation_match_pillow(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'image.tif'
            for storage in ({'tile': (16, 16)}, {'rowsperstrip': 7}):
                for grey in (False, True):
                    for orientation in (1, 2, 3, 4, 5, 6, 7, 8):
                        data = pixels()
                        if grey:
                            data = data[..., 0]
                        tifffile.imwrite(path, data, compression='deflate',
                                         extratags=[(274, 'H', 1, orientation, False)], **storage)
                        with Image.open(path) as source:
                            expected = np.array(source.convert('RGB'))
                        # No full-page decode may be used for supported TIFFs.
                        with patch.object(tifffile.TiffPage, 'asarray', side_effect=AssertionError('full read')):
                            actual = readers.read_tiff_chunks(path)
                        np.testing.assert_array_equal(actual, expected)

    def test_real_openslide_tiled_pyramid_matches_full_read(self):
        from openslide import OpenSlide
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'pyramid.tif'
            with tifffile.TiffWriter(path) as tif:
                tif.write(pixels(128, 96), tile=(16, 16), photometric='rgb', compression='deflate')
                tif.write(pixels(64, 48), tile=(16, 16), photometric='rgb', compression='deflate', subfiletype=1)
            with OpenSlide(str(path)) as slide:
                self.assertEqual(slide.level_count, 2)
                for level in range(slide.level_count):
                    expected = slide.read_region((0, 0), level, slide.level_dimensions[level]).convert('RGB')
                    np.testing.assert_array_equal(readers.read_openslide_chunks(slide, level, 16), expected)

    def test_isyntax_chunks_and_closes_on_success_or_failure(self):
        data = pixels()
        for failed in (False, True):
            def read(x, y, w, h, level):
                if failed:
                    raise RuntimeError('decode failed')
                return data[y:y+h, x:x+w]
            slide = SimpleNamespace(level_dimensions=[(106, 74), (53, 37)],
                                    level_downsamples=[1, 2], read_region=Mock(side_effect=read), close=Mock())
            backend = SimpleNamespace(ISyntax=SimpleNamespace(open=Mock(return_value=slide)))
            with patch.object(multi, 'isyntax', backend), patch.object(multi, 'isyntax_wsi_mpp', return_value=(.5, .5)), \
                 patch.object(multi, 'isyntax_decodes', return_value=True), patch.object(readers, 'READ_CHUNK_SIZE', 16):
                if failed:
                    with self.assertRaisesRegex(RuntimeError, 'decode failed'):
                        multi.read_isyntax('fake.isyntax', 1, 0)
                else:
                    image, mx, my = multi.read_isyntax('fake.isyntax', 1, 0)
                    np.testing.assert_array_equal(image, data)
                    self.assertEqual((mx, my), (1, 1))
                    self.assertEqual(slide.read_region.call_count, 12)
            slide.close.assert_called_once()

    def test_dicom_sparse_level_uses_level_coordinates(self):
        data = pixels()
        lvl = SimpleNamespace(level=3, size=SimpleNamespace(width=53, height=37),
                              mpp=SimpleNamespace(width=2, height=2))
        calls = []
        def read(xy, level, size):
            self.assertEqual(level, 3)
            calls.append((xy, size))
            x, y = xy
            w, h = size
            return Image.fromarray(data[y:y+h, x:x+w])
        slide = SimpleNamespace(size=lvl.size, mpp=lvl.mpp, levels=[lvl], read_region=read, close=Mock())
        backend = SimpleNamespace(WsiDicom=SimpleNamespace(open=Mock(return_value=slide)))
        with tempfile.TemporaryDirectory() as tmp, patch.object(multi, 'wsidicom', backend), \
             patch.object(readers, 'READ_CHUNK_SIZE', 16), contextlib.redirect_stdout(io.StringIO()):
            (Path(tmp) / 'out').mkdir()
            multi.process_images(tmp, ['out'], ['fake.dcm'], [2], [0])
            np.testing.assert_array_equal(tifffile.imread(Path(tmp) / 'out' / 'fake.tif'), data)
        self.assertEqual(len(calls), 12)
        slide.close.assert_called_once()

    def test_isyntax_probe_also_reads_in_parts(self):
        slide = SimpleNamespace(level_dimensions=[(4101, 2)], read_region=Mock(), close=Mock())
        backend = SimpleNamespace(ISyntax=SimpleNamespace(open=Mock(return_value=slide)))
        with patch.dict(sys.modules, {'isyntax': backend}), patch.object(sys, 'argv', ['probe', 'fake', '0']):
            exec(multi._ISYNTAX_PROBE, {})
        self.assertEqual(slide.read_region.call_count, 2)
        slide.read_region.assert_any_call(0, 0, 4096, 2, 0)
        slide.read_region.assert_any_call(4096, 0, 5, 2, 0)
        slide.close.assert_called_once()

    def test_unusual_tiff_layout_preserves_existing_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rgba.tif'
            data = np.concatenate((pixels(), np.full((37, 53, 1), 127, dtype='uint8')), axis=-1)
            tifffile.imwrite(path, data, photometric='rgb', extrasamples='unassalpha')
            with Image.open(path) as source:
                expected = np.array(source.convert('RGB'))
                source.close()
            with self.assertWarnsRegex(RuntimeWarning, 'existing Pillow reader'):
                actual = readers.read_tiff_chunks(path)
            np.testing.assert_array_equal(actual, expected)


if __name__ == '__main__':
    unittest.main()
