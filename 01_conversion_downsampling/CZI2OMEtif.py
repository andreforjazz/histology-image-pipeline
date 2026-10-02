import os
import re
import glob
import tifffile
import numpy as np
from PIL import Image, ImageCms
from pipeline_timing import TimingLog

from pylibCZIrw import czi as pyczi

# Exports carry an explicit sRGB tag so color-managed viewers (ImageScope,
# Photoshop) display the pixels as-is.
SRGB_PROFILE = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
# ICC tag written via extratags, which every tifffile version supports
# (the iccprofile= keyword only exists in tifffile >= 2023.7)
SRGB_EXTRATAG = (34675, 7, len(SRGB_PROFILE), SRGB_PROFILE, True)

# Apply the display gamma stored in the czi's DisplaySetting metadata to the
# pixels (1 = on). Zeiss brightfield scans store the camera's linear values and
# ZEN brightens them on screen through this gamma curve (typically 0.45); raw
# exports therefore look dark. Burning it in reproduces the ZEN appearance.
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


def read_czi(slide_path, target_um, load_native_resolution=1):
    """Reads a Zeiss .czi mosaic as an RGB image using pylibCZIrw.

        load_native_resolution = 1: the FULL RESOLUTION mosaic is decoded - the
        lower resolution pyramid levels stored inside the file are never used -
        and the image is downsampled to target_um with nearest neighbor sampling
        (same pixel center convention as Image.NEAREST). Slower (~1 min per
        gigapixel) but every output pixel is a true native pixel.
        load_native_resolution = 0: reads the file's own pyramid at the
        resolution closest to (but never coarser than) target_um; libCZI serves
        this from the finest stored layer with enough resolution and only ever
        scales DOWN, never up. Much faster, but the pyramid layers themselves
        were downsampled by the scanner software, not by nearest neighbor; only
        the final resize to each requested resolution uses nearest neighbor.

        Decoding happens in bounded chunks so files of any size (>90 GB) are
        never held in memory at full resolution. CZI stores BGR pixels on a
        stage coordinate grid that can start at negative values; both are
        handled here. Unscanned regions are filled white
        """

    with pyczi.open_czi(slide_path) as slide:
        # pixel size in microns from the scaling metadata (stored in meters)
        md = slide.raw_metadata
        mx = re.search(r'<Distance Id="X">.*?<Value>([\d.eE+-]+)</Value>', md, re.S)
        my = re.search(r'<Distance Id="Y">.*?<Value>([\d.eE+-]+)</Value>', md, re.S)
        mpp0 = float(mx.group(1)) * 1e6
        mpp0_y = float(my.group(1)) * 1e6 if my else mpp0

        # display rendering from the DisplaySetting metadata: ZEN shows the
        # image through out = ((v - low) / (high - low)) ^ gamma
        lut = None
        if APPLY_DISPLAY_GAMMA:
            block = re.search(r"<DisplaySetting>.*?</DisplaySetting>", md, re.S)
            block = block.group(0) if block else ""
            gm = re.search(r"<Gamma>([\d.eE+-]+)</Gamma>", block)
            lo = re.search(r"<Low>([\d.eE+-]+)</Low>", block)
            hi = re.search(r"<High>([\d.eE+-]+)</High>", block)
            gamma = float(gm.group(1)) if gm else 1.0
            low = float(lo.group(1)) if lo else 0.0
            high = float(hi.group(1)) if hi else 1.0
            if gamma != 1.0 or low != 0.0 or high != 1.0:
                print(f"       ...applying ZEN display rendering (gamma {gamma}"
                      + (f", window {low}-{high}" if lo or hi else "") + ")", flush=True)
                x = np.clip((np.arange(256) / 255.0 - low) / (high - low), 0, 1)
                lut = (np.power(x, gamma) * 255.0 + 0.5).astype(np.uint8)

        rect = slide.total_bounding_rectangle
        if 0 < target_um < max(mpp0, mpp0_y):
            print(f"       ...requested {target_um} um/px is finer than the scan "
                  f"({mpp0:.4f} um/px) - loading native resolution, never upsampling", flush=True)
            target_um = 0

        if not load_native_resolution and target_um > 0:
            # fast path: read the pyramid at the closest power-of-two zoom that
            # is still finer than the requested resolution
            zoom_pow = 0
            while max(mpp0, mpp0_y) * (2 << zoom_pow) <= target_um:
                zoom_pow += 1
            zoom = 1.0 / (1 << zoom_pow)
            mppx, mppy = mpp0 / zoom, mpp0_y / zoom
            w = int(rect.w * zoom)
            h = int(rect.h * zoom)
            print(f"       ...reading the file pyramid at zoom 1/{1 << zoom_pow} "
                  f"({w} x {h} at {mppx:.4f} um/px)", flush=True)
            buffer = np.empty((h, w, 3), np.uint8)
            strip_native = 4096 * (1 << zoom_pow)
            row = 0
            for y0 in range(0, rect.h, strip_native):
                native_h = min(strip_native, rect.h - y0)
                part = slide.read(roi=(rect.x, rect.y + y0, rect.w, native_h),
                                  zoom=zoom, plane={'C': 0},
                                  background_pixel=(255, 255, 255))
                part = part[:, :, ::-1]  # CZI is BGR; flip to RGB
                if lut is not None:
                    part = lut[part]
                rows = min(part.shape[0], h - row)
                buffer[row:row + rows] = part[:rows, :w]
                row += rows
                print(f"          ...read rows {row} of {h} ({100 * row // h}%)", flush=True)
            return Image.fromarray(buffer[:row]), mppx, mppy

        factor_x = target_um / mpp0 if target_um > 0 else 1.0
        factor_y = target_um / mpp0_y if target_um > 0 else 1.0
        out_w = int(np.ceil(rect.w / factor_x))
        out_h = int(np.ceil(rect.h / factor_y))
        mppx = rect.w * mpp0 / out_w      # effective resolution after rounding
        mppy = rect.h * mpp0_y / out_h

        # nearest neighbor source index for every output row and column
        col_idx = np.minimum(((np.arange(out_w) + 0.5) * rect.w / out_w).astype(np.int64), rect.w - 1)
        row_idx = np.minimum(((np.arange(out_h) + 0.5) * rect.h / out_h).astype(np.int64), rect.h - 1)

        chunk = 12288  # native pixels per chunk side (~450 MB per read)
        print(f"       ...decoding the full {rect.w} x {rect.h} native mosaic in "
              f"{chunk} px chunks -> {out_w} x {out_h} at {mppx:.4f} um/px", flush=True)
        print(f"       ...full resolution decode of {rect.w * rect.h / 1e9:.1f} gigapixels: "
              f"expect roughly {rect.w * rect.h / 20e6 / 60:.0f} minutes", flush=True)

        buffer = np.empty((out_h, out_w, 3), np.uint8)
        for y0 in range(0, rect.h, chunk):
            oy0 = int(np.searchsorted(row_idx, y0, 'left'))
            oy1 = int(np.searchsorted(row_idx, min(y0 + chunk, rect.h), 'left'))
            if oy1 == oy0:
                continue  # no output row samples this band
            native_h = int(row_idx[oy1 - 1]) - y0 + 1
            for x0 in range(0, rect.w, chunk):
                ox0 = int(np.searchsorted(col_idx, x0, 'left'))
                ox1 = int(np.searchsorted(col_idx, min(x0 + chunk, rect.w), 'left'))
                if ox1 == ox0:
                    continue
                native_w = int(col_idx[ox1 - 1]) - x0 + 1
                part = slide.read(roi=(rect.x + x0, rect.y + y0, native_w, native_h),
                                  plane={'C': 0}, background_pixel=(255, 255, 255))
                part = part[:, :, ::-1]  # CZI is BGR; flip to RGB
                if lut is not None:
                    part = lut[part]
                buffer[oy0:oy1, ox0:ox1] = part[row_idx[oy0:oy1] - y0][:, col_idx[ox0:ox1] - x0]
            print(f"          ...decoded native rows {min(y0 + chunk, rect.h)} of {rect.h} "
                  f"({100 * min(y0 + chunk, rect.h) // rect.h}%)", flush=True)
        image = Image.fromarray(buffer)

    return image, mppx, mppy


def process_images(pth, output_names, image_list, umpix, save_ome, load_native_resolution=1, outpth=None):
    """Process missing images by converting .czi files to .tif or .ome.tif."""

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

    timing = TimingLog(outpth, "conversion")
    with timing.measure(phase="batch_total"):
        for idx, image_in_list in enumerate(image_list):
            with timing.measure(os.path.join(pth, image_in_list)) as image_timing:
                image_timing["detail"] = f"native={load_native_resolution}; folders={output_names}; requested_mpp={umpix}; ome={save_ome}"
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
                    image_timing["status"] = "skipped_existing"
                    print(f"    ...already saved this file")
                    continue

                # Read the image at the finest resolution any output needs
                slide_path = os.path.join(pth, image_in_list)
                with timing.measure(slide_path, "read") as read_timing:
                    try:
                        print(f"    ...reading {slide_path} with pylibCZIrw")
                        finest_um = (0 if 0 in umpix else min(umpix))
                        image0, mppx, mppy = read_czi(slide_path, finest_um, load_native_resolution)
                        w, h = image0.size[:2]

                        read_timing["mpp"] = mppx
                        print(f"       ...image read successfully - file parameters: resolution of {mppx} and size of ({w}, {h})")

                    except Exception as e:
                        print(f"       ...ERROR reading {image_in_list}: {e}")
                        raise

                # Save the image at each desired resolution
                for folder_name, um, ome in zip(output_names, umpix, save_ome):
                    with timing.measure(slide_path, "resolution_total", folder_name, um) as output_timing:
                        output_name = os.path.join(outpth, folder_name, image_name + '.tif')
                        if um == 0 or um < mppx:
                            if 0 < um < mppx:
                                print(f"          ...requested {um} um/px is finer than the loaded image "
                                      f"({mppx:.4f} um/px) - saving at {mppx:.4f} instead, never upsampling")
                            um = mppx

                        output_timing["mpp"] = um
                        # resize the image
                        factor_x, factor_y = um / mppx, um / mppy
                        resize_dimension = (int(np.ceil(w / factor_x)), int(np.ceil(h / factor_y)))
                        with timing.measure(slide_path, "resize", folder_name, um):
                            image = image0.resize(resize_dimension, resample=Image.NEAREST)
                        print(f"          ...saving {folder_name} image at a resolution of {um} - resized to {resize_dimension}")

                        with timing.measure(slide_path, "save", folder_name, um):
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


def CZI2tif(pth, output_names, umpix, save_ome=0, load_native_resolution=1, outpth=None):
    print('Making down-sampled images:')

    for folder in output_names:
        pthim = os.path.join(outpth if outpth is not None else pth, f'{folder}')

        # Ensure the image directory exists
        if not os.path.isdir(pthim):
            os.makedirs(pthim)

    # Get the .czi image names, sorted alphabetically
    patterns = ['*.czi']
    image_list = [file for pattern in patterns for file in [str(f) for f in __import__('pathlib').Path(pth).iterdir() if f.is_file() and f.name.lower().endswith(pattern[1:])]]
    image_list = sorted(image_list)
    image_list = [os.path.basename(file) for file in image_list]
    if not image_list:
        print("  No .czi files found.")
        return

    # process the images
    process_images(pth, output_names, image_list, umpix, save_ome,
                   load_native_resolution, outpth)


if __name__ == '__main__':
    raise SystemExit('Use run_conversion.py --help for explicit input and output paths.')
