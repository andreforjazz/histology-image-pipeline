"""Apply existing CODA transforms at any supported image resolution."""
import argparse
import math
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description='Apply CODA transforms to calibrated high-resolution images.')
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--warps', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--registration-mpp', type=float, required=True,
                   help='Micrometres/pixel of the images used to CALCULATE registration (sx)')
    p.add_argument('--view', action='store_true')
    p.add_argument('--scanner', default='unknown', help='Original scanner/model')
    p.add_argument('--scanner-manifest', type=Path, help='Optional CSV: image,scanner')
    args = p.parse_args()
    if not args.input.is_dir() or not args.warps.is_dir() or not (args.warps / 'D').is_dir():
        p.error('Provide an image directory and a save_warps directory containing D.')
    if not math.isfinite(args.registration_mpp) or args.registration_mpp <= 0:
        p.error('registration-mpp must be finite and positive.')
    if args.input.resolve() == args.output.resolve():
        p.error('Choose an output directory different from the input directory.')
    from apply_registration_to_20x_image import apply_registration_to_20x
    from pipeline_timing import timing_settings
    with timing_settings(args.scanner, args.scanner_manifest):
        apply_registration_to_20x(str(args.input.resolve()), str(args.warps.resolve()),
                                 args.registration_mpp, int(args.view), str(args.output.resolve()), ome=1)


if __name__ == '__main__':
    main()
