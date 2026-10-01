import os
import re
import glob
import json
import tifffile
import numpy as np
from PIL import Image, ImageCms

import slideio

# Exports carry an explicit sRGB tag so color-managed viewers (ImageScope,
# Photoshop) display the pixels as-is.
SRGB_PROFILE = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
# ICC tag written via extratags, which every tifffile version supports
# (the iccprofile= keyword only exists in tifffile >= 2023.7)
SRGB_EXTRATAG = (34675, 7, len(SRGB_PROFILE), SRGB_PROFILE, True)

# Apply the display gamma stored in the vsi metadata to the pixels (1 = on).
# Olympus/Evident scanners normally store display-ready pixels with
# "Gamma correction" = 1.0 (no ICC profile), in which case nothing is applied;
# if a file declares a different gamma it is burned in so exports match the
# OlyVIA viewer.
APPLY_DISPLAY_GAMMA = 1

Image.MAX_IMAGE_PIXELS = None  # Disable the limit


def save_ome_tif(image, pth, folder_name, image_name, pixelsize):
    """Exports an image in ome-tif format with metadata compatible with Qupath.

        Each ome-tif file will contain pyramidal copies saved at downsample factors of
        [1, 2, 4, 8, 16, 32] and tiled at a size of [1024 x 1024] for rapid loading
        """

    output_name = os.path.join(pth, folder_name, image_name + '.ome.tif')

    # some settings for the ome-tif file
    tile_size = 1024
    compression_quality = 95
    scale_factors = [int(1), int(2), int(4), int(8), int(16), int(32), int(64)]  # Define downsampling factors to save in each ome-tif

    # Ensure shape matches expected format (Y, X, Channels)
    image = np.array(image)
    shape = image.shape
    axes = 'YXS' if shape[-1] == 1 else 'YXC'  # 'YXC' for RGB, 'YXS' for single-channel

    metadata = {
        'axes': axes,
        'SignificantBits': 8,
        'PhysicalSizeX': pixelsize,
        'PhysicalSizeXUnit': 'µm',
        'PhysicalSizeY': pixelsize,
        'PhysicalSizeYUnit': 'µm',
        'Software': 'tifffile',
    }

    options = dict(
        photometric='rgb' if shape[-1] == 3 else 'minisblack',
        tile=(tile_size, tile_size),
        compression='jpeg',
        compressionargs={"level": compression_quality},
        resolutionunit=3,  # 3 = Centimeter
    )

    with tifffile.TiffWriter(output_name, bigtiff=True) as tif:
        subifds_data = []  # List to store downsampled images for SubIFDs

        # Generate downsampled images
        for scale in scale_factors[1:]:  # Start from the second level (skip 1x)
            new_size = (shape[1] // scale, shape[0] // scale)
            if min(new_size) < 1:
                break  # Stop if downsampling is too small

            downsampled = Image.fromarray(image).resize(new_size, resample=Image.Resampling.LANCZOS)
            subifds_data.append(np.array(downsampled, dtype=np.uint8))

        # Save main image with SubIFDs for pyramidal TIFF structure
        tif.write(
            image.astype(np.uint8),
            subifds=len(subifds_data),  # Define how many SubIFDs will follow
            resolution=(1e4 / pixelsize, 1e4 / pixelsize),
            metadata=metadata,
            extratags=[SRGB_EXTRATAG],
            **options
        )

        # Write the SubIFDs (pyramidal levels)
        for idx, sub_image in enumerate(subifds_data):
            scale = scale_factors[idx + 1]  # Get scale factor
            res_val = 1e4 / scale / pixelsize

            tif.write(
                sub_image,
                subfiletype=1,  # Mark as pyramid level
                resolution=(res_val, res_val),
                **options
            )

        # Add a thumbnail image for QuPath and ImageScope
        thumbnail = image[::8, ::8]  # Downsample by factor of 8
        tif.write(thumbnail.astype(np.uint8), metadata={'Name': 'thumbnail'})

    #print(f"Saved: {output_name}")


def read_vsi(slide_path, target_um, load_native_resolution=1):
    """Reads an Olympus/Evident .vsi slide as an RGB image using slideio.

        load_native_resolution = 1: native FULL RESOLUTION blocks are always
        decoded - the lower resolution pyramid levels inside the file are never
        used - and the image is downsampled to target_um with nearest neighbor
        sampling (same pixel center convention as Image.NEAREST). Decoding
        happens in bounded 2D chunks so files of any size are never held in
        memory at full resolution.
        load_native_resolution = 0: lets slideio resample from the file's own
        pyramid at the requested size. Much faster, but the pyramid levels were
        downsampled by the scanner software, not by nearest neighbor.

        The scene with the most pixels is used (vsi files also carry macro and
        overview images). Requires the companion _<name>_ folder next to the
        .vsi file, which holds the actual pixel data
        """

    slide = slideio.open_slide(slide_path, "VSI")

    # pick the scene with the most pixels (the whole slide image)
    scene = max((slide.get_scene(i) for i in range(slide.num_scenes)),
                key=lambda sc: sc.rect[2] * sc.rect[3])
    x0, y0, w0, h0 = scene.rect
    mpp0 = scene.resolution[0] * 1e6
    mpp0_y = scene.resolution[1] * 1e6

    # display gamma from the metadata; Olympus files normally store 1.0
    lut = None
    if APPLY_DISPLAY_GAMMA:
        gm = re.search(r'"Gamma correction"[^}]*?"value":"([\d.eE+-]+)"', slide.raw_metadata)
        gamma = float(gm.group(1)) if gm else 1.0
        if gamma != 1.0:
            print(f"       ...applying display gamma {gamma} from the vsi metadata", flush=True)
            x = np.arange(256) / 255.0
            lut = (np.power(x, gamma) * 255.0 + 0.5).astype(np.uint8)

    if 0 < target_um < max(mpp0, mpp0_y):
        print(f"       ...requested {target_um} um/px is finer than the scan "
              f"({mpp0:.4f} um/px) - loading native resolution, never upsampling", flush=True)
        target_um = 0

    factor_x = target_um / mpp0 if target_um > 0 else 1.0
    factor_y = target_um / mpp0_y if target_um > 0 else 1.0
    out_w = int(np.ceil(w0 / factor_x))
    out_h = int(np.ceil(h0 / factor_y))
    mppx = w0 * mpp0 / out_w          # effective resolution after rounding
    mppy = h0 * mpp0_y / out_h

    if not load_native_resolution and target_um > 0:
        # fast path: let slideio resample from the file's pyramid
        print(f"       ...reading the file pyramid resampled to {out_w} x {out_h} "
              f"at {mppx:.4f} um/px", flush=True)
        buffer = scene.read_block((x0, y0, w0, h0), size=(out_w, out_h))
        if lut is not None:
            buffer = lut[buffer]
        return Image.fromarray(buffer), mppx, mppy

    # nearest neighbor source index for every output row and column
    col_idx = np.minimum(((np.arange(out_w) + 0.5) * w0 / out_w).astype(np.int64), w0 - 1)
    row_idx = np.minimum(((np.arange(out_h) + 0.5) * h0 / out_h).astype(np.int64), h0 - 1)

    chunk = 12288  # native pixels per chunk side (~450 MB per read)
    print(f"       ...decoding the full {w0} x {h0} native image in "
          f"{chunk} px chunks -> {out_w} x {out_h} at {mppx:.4f} um/px", flush=True)
    print(f"       ...full resolution decode of {w0 * h0 / 1e9:.1f} gigapixels: "
          f"expect roughly {w0 * h0 / 80e6 / 60:.0f} minutes", flush=True)

    buffer = np.empty((out_h, out_w, 3), np.uint8)
    for cy0 in range(0, h0, chunk):
        oy0 = int(np.searchsorted(row_idx, cy0, 'left'))
        oy1 = int(np.searchsorted(row_idx, min(cy0 + chunk, h0), 'left'))
        if oy1 == oy0:
            continue  # no output row samples this band
        native_h = int(row_idx[oy1 - 1]) - cy0 + 1
        for cx0 in range(0, w0, chunk):
            ox0 = int(np.searchsorted(col_idx, cx0, 'left'))
            ox1 = int(np.searchsorted(col_idx, min(cx0 + chunk, w0), 'left'))
            if ox1 == ox0:
                continue
            native_w = int(col_idx[ox1 - 1]) - cx0 + 1
            part = scene.read_block((x0 + cx0, y0 + cy0, native_w, native_h))
            if lut is not None:
                part = lut[part]
            buffer[oy0:oy1, ox0:ox1] = part[row_idx[oy0:oy1] - cy0][:, col_idx[ox0:ox1] - cx0]
        print(f"          ...decoded native rows {min(cy0 + chunk, h0)} of {h0} "
              f"({100 * min(cy0 + chunk, h0) // h0}%)", flush=True)
    image = Image.fromarray(buffer)

    return image, mppx, mppy


def process_images(pth, output_names, image_list, umpix, save_ome, load_native_resolution=1, outpth=None):
    """Process missing images by converting .vsi files to .tif or .ome.tif."""

    if outpth is None:
        outpth = pth

    if not isinstance(save_ome, list):
        save_ome = [save_ome] * (len(output_names) if isinstance(output_names, list) else 1)

    if not isinstance(umpix, list):
        umpix = [umpix]

    if not isinstance(output_names, list):
        output_names = [output_names]

    if not (len(output_names) == len(umpix) == len(save_ome)):
        raise ValueError('Output folders, resolutions and formats must have equal lengths.')
    if not all(np.isfinite(um) and um >= 0 for um in umpix):
        raise ValueError('Resolutions must be finite and nonnegative.')

    for idx, image_in_list in enumerate(image_list):
        print(f"  Starting image {idx + 1} of {len(image_list)}: {image_in_list}...")

        # check if the image is already downsampled
        image_name = image_in_list.rsplit('.', 1)[0]
        image_done = 1
        for folder_name, ome in zip(output_names, save_ome):
            ft = '.ome.tif' if ome == 1 else '.tif'
            output_name = os.path.join(outpth, folder_name, image_name + ft)
            if not os.path.exists(output_name):
                image_done = 0
                break
        if image_done == 1:
            print(f"    ...already saved this file")
            continue

        # Read the image at the finest resolution any output needs
        slide_path = os.path.join(pth, image_in_list)
        try:
            print(f"    ...reading {slide_path} with slideio")
            finest_um = (0 if 0 in umpix else min(umpix))
            image0, mppx, mppy = read_vsi(slide_path, finest_um, load_native_resolution)
            w, h = image0.size[:2]

            print(f"       ...image read successfully - file parameters: resolution of {mppx} and size of ({w}, {h})")

        except Exception as e:
            print(f"       ...ERROR reading {image_in_list}: {e}")
            raise

        # Save the image at each desired resolution
        for folder_name, um, ome in zip(output_names, umpix, save_ome):
            output_name = os.path.join(outpth, folder_name, image_name + '.tif')
            if um == 0 or um < mppx:
                if 0 < um < mppx:
                    print(f"          ...requested {um} um/px is finer than the loaded image "
                          f"({mppx:.4f} um/px) - saving at {mppx:.4f} instead, never upsampling")
                um = mppx

            # resize the image
            factor_x, factor_y = um / mppx, um / mppy
            resize_dimension = (int(np.ceil(w / factor_x)), int(np.ceil(h / factor_y)))
            image = image0.resize(resize_dimension, resample=Image.NEAREST)
            print(f"          ...saving {folder_name} image at a resolution of {um} - resized to {resize_dimension}")

            # save the file as either a normal or an ome-tif
            if ome == 1:
                print("             ...saving as an ome tif")
                save_ome_tif(image, outpth, folder_name, image_name, um)
            else:
                try: # save as normal tif
                    image.save(output_name, resolution=1e4 / um, resolution_unit=3, quality=100, compression=None, icc_profile=SRGB_PROFILE)
                except Exception as e: # save as ome-tif
                    save_ome_tif(image, outpth, folder_name, image_name, um)
                    print(f"          ...error saving {image_in_list} as tif: {e}, try saving this image as an ome-tif")
                    continue

        print("  Image save successful!")
        print("  ")


def VSI2tif(pth, output_names, umpix, save_ome=0, load_native_resolution=1, outpth=None):
    print('Making down-sampled images:')

    for folder in output_names:
        pthim = os.path.join(outpth if outpth is not None else pth, f'{folder}')

        # Ensure the image directory exists
        if not os.path.isdir(pthim):
            os.makedirs(pthim)

    # Get the .vsi image names, sorted alphabetically
    patterns = ['*.vsi']
    image_list = [file for pattern in patterns for file in [str(f) for f in __import__('pathlib').Path(pth).iterdir() if f.is_file() and f.name.lower().endswith(pattern[1:])]]
    image_list = sorted(image_list)
    image_list = [os.path.basename(file) for file in image_list]
    if not image_list:
        print("  No .vsi files found.")
        return

    # process the images
    process_images(pth, output_names, image_list, umpix, save_ome,
                   load_native_resolution, outpth)


if __name__ == '__main__':
    raise SystemExit('Use run_conversion.py --help for explicit input and output paths.')
