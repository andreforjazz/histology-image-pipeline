# Comparing the original WSI converters

This comparison describes the user-provided copies inspected on 1 October 2026, **before** the fixes in this repository. `WSI2OMEtif.py` had changed since the initial project selection, so conclusions refer to the currently supplied file, not an assumed version history.

## WSI2OMEtif.py

This is a narrower batch converter. Its OpenSlide branch reads the entire image at level 0 and then resizes it with nearest-neighbour sampling. This avoids relying on a scanner-generated lower-resolution pyramid, but can use substantially more memory.

It discovers NDPI, SVS, SCN, TIFF, PNG/JPEG, MRXS, DICOM, QPTIFF and iSyntax extensions. Discovery does not guarantee decoding support: several extensions are sent to OpenSlide, so support depends on that backend. Its VSI/CZI branch explicitly skips those files. It imports `pyvips` and `isyntax` unconditionally; a missing optional package can therefore prevent other formats from running too. `pyvips` is not used by the inspected processing path.

This supplied version already contains SVS ICC conversion, sRGB tagging, and iSyntax support. Those features are not exclusive to the all-file-types version.

Its `WSI2tif` entry point expects a directory. When a separate `outpth` is supplied, it still creates output subdirectories beneath the input directory, which can leave the actual destination missing. Its plain TIFF export does not write calibrated physical-resolution tags, and its generic TIFF reader can fall back to 1 µm/pixel.

## WSI2OMEtif_All_file_types.py

This is the broader routing implementation. The original inspected version adds dedicated VSI and CZI paths, a `wsidicom` path with OpenSlide fallback for DICOM, and additional handling for Roche/Ventana TIFF. It recognizes `.tiff` as well as `.tif`, handles OME-TIFF suffixes, accepts either a file or a directory, and creates folders under the requested output destination.

Optional scanner libraries are imported conditionally. It closes more slide handles explicitly and selects an appropriate source pyramid level for several OpenSlide-backed formats. That can be faster and use less memory than loading level 0. It also means that identical MPP values do not necessarily produce identical pixels between the two scripts.

There were important inconsistencies: the original `load_native_resolution` argument was not honoured by all reader branches, the VSI branch used its own resampling path rather than the dedicated chunked reader, generic TIFF could still assume a resolution, and plain TIFF output omitted physical calibration. Neither original was a complete guarantee of support for every scanner or file variant.

## Choice for this repository

The maintained entry point uses `WSI2OMEtif_All_file_types.py` for the broader routing, with the dedicated VSI/CZI implementations shared rather than duplicated. It fixes calibration handling, the relevant native/pyramid flag behaviour, read-error propagation, and prevents upsampling. The original dedicated scanner algorithms remain the basis of their readers.

`WSI2OMEtif.py` is kept locally as a historical comparator but is not published as another supported entry point. Use `run_conversion.py`; the file name “All_file_types” is historical and should not be read as universal format support.
