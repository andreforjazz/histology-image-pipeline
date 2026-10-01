"""Read physical pixel spacing without silently inventing a scanner resolution."""
import math
import xml.etree.ElementTree as ET

import tifffile


def read_tiff_mpp(path):
    """Return (X, Y) micrometres/pixel from OME XML or calibrated TIFF tags."""
    with tifffile.TiffFile(path) as tif:
        if tif.ome_metadata:
            pixels = ET.fromstring(tif.ome_metadata).find('.//{*}Pixels')
            units = {'µm': 1, 'um': 1, 'nm': 0.001, 'mm': 1000, 'm': 1e6}
            if pixels is not None and all('PhysicalSize' + a in pixels.attrib for a in 'XY'):
                values = []
                for axis in 'XY':
                    unit = pixels.get('PhysicalSize' + axis + 'Unit', 'µm')
                    if unit not in units:
                        raise ValueError(f'Unsupported OME physical-size unit: {unit}')
                    values.append(float(pixels.get('PhysicalSize' + axis)) * units[unit])
                return validate_mpp(*values)
        tags = tif.pages[0].tags
        unit = tags.get('ResolutionUnit')
        factor = {2: 25400.0, 3: 10000.0}.get(int(unit.value) if unit else 1)
        if factor and 'XResolution' in tags and 'YResolution' in tags:
            def value(tag):
                v = tag.value
                return float(v[0]) / float(v[1]) if isinstance(v, tuple) else float(v)
            return validate_mpp(factor / value(tags['XResolution']), factor / value(tags['YResolution']))
    raise ValueError(f'No physical pixel spacing in {path}; provide a calibrated TIFF/OME-TIFF.')


def validate_mpp(x, y):
    if not all(math.isfinite(v) and v > 0 for v in (x, y)):
        raise ValueError('Physical pixel spacing must be finite and positive.')
    return float(x), float(y)
