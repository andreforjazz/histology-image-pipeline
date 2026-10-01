"""Synthetic regression tests. No patient images, network or MATLAB licence needed."""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
from scipy.io import savemat
import tifffile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / '01_conversion_downsampling'), str(ROOT / '03_apply_registration')]
import WSI2OMEtif_All_file_types as multi
import apply_registration_to_20x_image as registration
from image_metadata import read_tiff_mpp


def pattern(height=48, width=64):
    y, x = np.indices((height, width))
    return np.stack(((x*7) % 230, (y*11) % 230, (x+y)*3 % 230), -1).astype('uint8')


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_calibrated_tiff_resolution(self):
        f = self.folder / 'sample.tif'
        tifffile.imwrite(f, pattern(), resolution=(20000, 10000), resolutionunit='CENTIMETER')
        self.assertEqual(read_tiff_mpp(f), (0.5, 1.0))

    def test_unknown_resolution_is_rejected(self):
        f = self.folder / 'sample.tif'
        tifffile.imwrite(f, pattern())
        with self.assertRaises(ValueError):
            read_tiff_mpp(f)

    def test_ome_pyramid_roundtrip(self):
        multi.save_ome_tif(pattern(), str(self.folder), '.', 'sample', 0.5)
        f = self.folder / 'sample.ome.tif'
        self.assertEqual(read_tiff_mpp(f), (0.5, 0.5))
        with tifffile.TiffFile(f) as tif:
            self.assertTrue(tif.is_ome)
            self.assertEqual(tif.pages[0].shape, (48, 64, 3))
            self.assertGreater(len(tif.series[0].levels), 1)
            self.assertEqual(tif.series[0].levels[1].shape[:2], (24, 32))
            self.assertIn(34675, tif.pages[0].tags)
            self.assertLess(np.abs(tif.asarray().astype(float)-pattern()).mean(), 12)

    def test_multiformat_downsample_plain_tiff(self):
        source = self.folder / 'slide.01.TIF'
        tifffile.imwrite(source, pattern(), resolution=(20000, 20000), resolutionunit='CENTIMETER')
        multi.WSI2tif(str(source), ['2x'], [2], [0], outpth=str(self.folder))
        output = self.folder / '2x/slide.01.tif'
        with Image.open(output) as im:
            self.assertEqual(im.size, (16, 12))
            pixels = np.array(im)
        self.assertEqual(read_tiff_mpp(output), (2, 2))
        np.testing.assert_array_equal(pixels, np.array(Image.fromarray(pattern()).resize((16, 12), Image.Resampling.NEAREST)))

    def test_no_upsampling(self):
        source = self.folder / 'input.tif'
        tifffile.imwrite(source, pattern(), resolution=(20000, 20000), resolutionunit='CENTIMETER')
        multi.WSI2tif(str(source), ['fine'], [0.1], [0], outpth=str(self.folder))
        with Image.open(self.folder / 'fine/input.tif') as im:
            self.assertEqual(im.size, (64, 48))
        self.assertEqual(read_tiff_mpp(self.folder / 'fine/input.tif'), (0.5, 0.5))

    def test_affine_identity_and_translation(self):
        image = pattern()
        np.testing.assert_array_equal(registration.transform_image(image, np.eye(3), 0, tile=7), image)
        matrix = np.eye(3)
        matrix[2, :2] = [3, 2]
        out = registration.transform_image(image, matrix, 0, tile=7)
        np.testing.assert_array_equal(out[2:, 3:], image[:-2, :-3])
        self.assertTrue(np.all(out[:2] == 241))

    def test_matlab_one_based_rotation_centre(self):
        image = pattern(8, 10)
        matrix = np.diag([-1., -1., 1.])
        out = registration.transform_image(image, matrix, 0, cent=(5.5, 4.5), tile=3)
        np.testing.assert_array_equal(out, image[::-1, ::-1])

    def test_flip(self):
        image = pattern()
        np.testing.assert_array_equal(registration.transform_image(image, np.eye(3), 1), image[::-1])

    def test_elastic_identity_translation_and_outside(self):
        image = pattern()
        field = np.zeros((48, 64, 2), np.float32)
        np.testing.assert_array_equal(registration.register_image_elastic(image, field, 1, None, tile=7), image)
        field[..., 0] = 2
        moved = registration.register_image_elastic(image, field, 1, None, tile=7)
        np.testing.assert_array_equal(moved[:, :-2], image[:, 2:])
        self.assertTrue(np.all(moved[:, -2:] == 241))
        field[:] = 1000
        self.assertTrue(np.all(registration.register_image_elastic(image, field, 1, None, tile=7) == 241))

    def test_padding(self):
        image = pattern(3, 4)
        padded = registration.pad_image(image, [5, 8], 2)
        self.assertEqual(padded.shape, (9, 12, 3))
        np.testing.assert_array_equal(padded[3:6, 4:8], image)

    def test_dotted_image_name(self):
        self.assertEqual(registration.remove_extension('slide.01.ome.tif'), 'slide.01')

    def test_reference_first_and_numeric_moving_transform(self):
        warps = self.folder / 'registered/elastic registration/save_warps'
        (warps / 'D').mkdir(parents=True)
        image = pattern(8, 10)
        savemat(warps / 'a.reference.mat', {'zc': 1})
        savemat(warps / 'b.moving.mat', {'szz': [8, 10], 'padall': 0, 'f': 0,
                'cent': [5.5, 4.5], 'tform_python': np.eye(3)})
        savemat(warps / 'D/b.moving.mat', {'D': np.zeros((8, 10, 2))})
        for name in ['a.reference', 'b.moving']:
            Image.fromarray(image).save(warps.parent / (name + '.jpg'))
            out, _ = registration.apply_CODA_registration(image, name, str(warps), 1, 0)
            np.testing.assert_array_equal(out, image)

    def test_conversion_cli_reports_read_failure(self):
        bad = self.folder / 'bad.tif'
        bad.write_text('not a TIFF')
        result = subprocess.run([sys.executable, str(ROOT / '01_conversion_downsampling/run_conversion.py'),
            '--format', 'other', '--input', str(bad), '--output', str(self.folder / 'out'),
            '--folder', '2x', '--mpp', '5'], capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_application_batch_includes_reference_without_D(self):
        source = self.folder / 'images'
        source.mkdir()
        warps = self.folder / 'registered/elastic registration/save_warps'
        (warps / 'D').mkdir(parents=True)
        image = pattern(8, 10)
        savemat(warps / 'a.mat', {'zc': 1})
        savemat(warps / 'b.mat', {'szz': [8, 10], 'padall': 0, 'f': 0,
                'cent': [5.5, 4.5], 'tform_python': np.eye(3)})
        savemat(warps / 'D/b.mat', {'D': np.zeros((8, 10, 2))})
        for name in ['a', 'b']:
            tifffile.imwrite(source / (name+'.tif'), image, resolution=(20000, 20000), resolutionunit='CENTIMETER')
            Image.fromarray(image).save(warps.parent / (name+'.jpg'))
        out = self.folder / 'output'
        registration.apply_registration_to_20x(str(source), str(warps), 0.5, out_folder=str(out))
        self.assertEqual(len(list(out.glob('*.ome.tif'))), 2)
        self.assertEqual(read_tiff_mpp(out / 'a.ome.tif'), (0.5, 0.5))

    def test_resolution_scaling_10x_20x_40x(self):
        for scale in (5, 10, 20):
            with self.subTest(scale=scale):
                image = pattern(4*scale, 6*scale)
                transform = np.eye(3)
                transform[2, 0] = 1
                moved = registration.transform_image(image, transform, 0, scale=scale, tile=13)
                np.testing.assert_array_equal(moved[:, scale:], image[:, :-scale])
                self.assertTrue(np.all(moved[:, :scale] == 241))
                field = np.zeros((4, 6, 2), np.float32)
                field[..., 0] = 1
                elastic = registration.register_image_elastic(image, field, scale, None, tile=13)
                np.testing.assert_array_equal(elastic[:, :-scale], image[:, scale:])

    def test_real_czi_reader_with_generated_file(self):
        try:
            from pylibCZIrw import czi
            from CZI2OMEtif import read_czi
        except ImportError:
            self.skipTest('Install requirements/scanners.txt to test the CZI reader.')
        source = self.folder / 'generated.czi'
        image = pattern()
        with czi.create_czi(str(source)) as writer:
            writer.write(np.ascontiguousarray(image[..., ::-1]), location=(-10, -20), plane={'C': 0})
            # This writer writes the supplied values into CZI's metre-valued scaling XML.
            writer.write_metadata(scale_x=0.5e-6, scale_y=0.5e-6)
        result, mppx, mppy = read_czi(str(source), 1, 1)
        self.assertAlmostEqual(mppx, 1)
        self.assertAlmostEqual(mppy, 1)
        np.testing.assert_array_equal(np.asarray(result), np.asarray(Image.fromarray(image).resize((32,24), Image.Resampling.NEAREST)))

    def test_vsi_native_reader_with_simulated_scene(self):
        try:
            import vsi2ometif as vsi
        except ImportError:
            self.skipTest('Install requirements/scanners.txt to test the VSI adapter.')
        image = pattern()
        class Scene:
            rect = (0, 0, 64, 48)
            resolution = (0.5e-6, 0.5e-6)
            def read_block(self, rect, size=None):
                x,y,w,h = rect
                part = image[y:y+h,x:x+w]
                return np.array(Image.fromarray(part).resize(size)) if size else part
        class Slide:
            num_scenes = 1
            raw_metadata = ''
            def get_scene(self, index):
                return Scene()
        with patch.object(vsi.slideio, 'open_slide', return_value=Slide()):
            result, x, y = vsi.read_vsi('simulated.vsi', 1, 1)
        self.assertEqual((x, y), (1, 1))
        np.testing.assert_array_equal(np.asarray(result), image[1::2,1::2])

    def test_hdf5_matlab_numeric_array_orientation(self):
        try:
            import h5py
        except ImportError:
            self.skipTest('h5py is required for MATLAB v7.3 numeric arrays.')
        f = self.folder / 'numeric.mat'
        expected = np.arange(8*10*2).reshape(8,10,2).astype(float)
        with h5py.File(f, 'w') as h5:
            dataset = h5.create_dataset('D', data=expected.transpose(2,1,0))
            dataset.attrs['MATLAB_class'] = np.bytes_('double')
        np.testing.assert_array_equal(registration.load_mat_file(f)['D'], expected)


if __name__ == '__main__':
    unittest.main()
