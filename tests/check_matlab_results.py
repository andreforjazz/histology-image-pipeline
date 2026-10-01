"""Compare Python warps against fixtures produced by validate_matlab.m."""
import argparse
from pathlib import Path
import sys

import numpy as np
from scipy.io import loadmat

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '03_apply_registration'))
from apply_registration_to_20x_image import transform_image, register_image_elastic


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('fixture', type=Path)
    args = p.parse_args()
    values = loadmat(args.fixture)
    affine = transform_image(values['image'], values['T'], 0, values['cent'].ravel(), tile=7)
    elastic = register_image_elastic(values['image'], values['D'], 1, None, tile=7)
    np.testing.assert_array_equal(affine, values['expected_affine'])
    np.testing.assert_array_equal(elastic, values['expected_elastic'])
    print('MATLAB/Python parity: PASS (affine rotation/translation and constant displacement).')


if __name__ == '__main__':
    main()
