"""Bounded decoding for the existing conversion readers.

The assembled RGB image is still held in memory. Only decoding is changed;
resolution selection, downstream resizing, colour correction and saving stay
with their existing callers.
"""
from fractions import Fraction
import warnings

import numpy as np
from PIL import Image
import tifffile


READ_CHUNK_SIZE = 4096


def read_rgb_chunks(size, read_region, chunk_size=None):
    """Assemble RGB regions; callback coordinates are in the selected level."""
    chunk_size = READ_CHUNK_SIZE if chunk_size is None else chunk_size
    if chunk_size < 1:
        raise ValueError('Read chunk size must be positive.')
    width, height = size
    image = Image.new('RGB', (width, height))
    for y in range(0, height, chunk_size):
        for x in range(0, width, chunk_size):
            region_size = (min(chunk_size, width - x), min(chunk_size, height - y))
            part = read_region((x, y), region_size)
            if not isinstance(part, Image.Image):
                part = Image.fromarray(part)
            if part.size != region_size:
                raise ValueError(f'Reader returned {part.size}; expected {region_size}.')
            image.paste(part.convert('RGB'), (x, y))
    return image


def read_openslide_chunks(slide, level, chunk_size=None):
    """OpenSlide locations use level-0 pixels, but sizes use level pixels."""
    chunk_size = READ_CHUNK_SIZE if chunk_size is None else chunk_size
    if chunk_size < 1:
        raise ValueError('Read chunk size must be positive.')
    downsample = slide.level_downsamples[level]
    # Align boundaries to integral level-0 coordinates where possible, avoiding
    # a fractional-pixel shift when the level downsample is not an integer.
    denominator = Fraction(float(downsample)).limit_denominator(chunk_size).denominator
    chunk_size = max(denominator, chunk_size // denominator * denominator)
    return read_rgb_chunks(
        slide.level_dimensions[level],
        lambda xy, size: slide.read_region(
            (round(xy[0] * downsample), round(xy[1] * downsample)), level, size),
        chunk_size,
    )


def read_tiff_chunks(path):
    """Decode standard 8-bit RGB/grayscale TIFFs one stored tile/strip at a time.

    A strip's dimensions are set by the source file, not by this reader. A TIFF
    stored as one compressed strip can still require a large decoder buffer.
    Unusual photometric modes keep Pillow's existing conversion semantics.
    """
    with Image.open(path) as source, tifffile.TiffFile(path) as tif:
        page = tif.pages[0]
        supported = (page.dtype == np.dtype('uint8') and
                     page.planarconfig == 1 and page.imagedepth == 1 and
                     ((page.photometric == 2 and page.samplesperpixel == 3) or
                      (page.photometric == 1 and page.samplesperpixel == 1)))
        if not supported:
            warnings.warn('This TIFF pixel layout uses the existing Pillow reader; '
                          'bounded tile/strip decoding is unavailable for this layout.',
                          RuntimeWarning, stacklevel=2)
            result = source.convert('RGB')
            source.close()
            return result

        image = Image.new('RGB', (page.imagewidth, page.imagelength))
        for segment, position, shape in page.segments(maxworkers=1, buffersize=4 << 20):
            _, _, y, x, _ = position
            if segment is None:
                continue  # Empty TIFF segments decode as zero, like the new buffer.
            height = min(shape[1], page.imagelength - y)
            width = min(shape[2], page.imagewidth - x)
            pixels = segment[0, :height, :width]
            if page.samplesperpixel == 1:
                pixels = pixels[..., 0]
            image.paste(Image.fromarray(pixels).convert('RGB'), (x, y))

        # Pillow applies TIFF orientation during load; reproduce that behaviour.
        orientation = page.tags.get('Orientation')
        transforms = {2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180,
                      4: Image.Transpose.FLIP_TOP_BOTTOM, 5: Image.Transpose.TRANSPOSE,
                      6: Image.Transpose.ROTATE_270, 7: Image.Transpose.TRANSVERSE,
                      8: Image.Transpose.ROTATE_90}
        if orientation is not None and orientation.value in transforms:
            image = image.transpose(transforms[orientation.value])
        return image
