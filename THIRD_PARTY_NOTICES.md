# Attribution and third-party components

## CODA

The registration calculation uses CODA by Ashley Lynn Kiemen and collaborators. Original source: https://github.com/ashleylk/CODA, `update 12-13-2023`. Source headers and the original local README are retained in the local dependency installation.

Reference: Kiemen et al., *Nature Methods* (2022), https://doi.org/10.1038/s41592-022-01650-9.

The public repository distributes integration code and an installation manifest, not the CODA MATLAB implementation. Obtain that implementation from the authors/upstream project. No repository-wide open-source licence is assigned here because the inherited research scripts and third-party components have separate provenance. Public availability is not an assertion that all components may be relicensed.

## Python libraries

NumPy, Pillow, tifffile, imagecodecs, OpenSlide, SlideIO, pylibCZIrw, SciPy, OpenCV, h5py, matplotlib, and optional scanner backends remain subject to their respective licences. They are installed as dependencies and their binaries are not bundled.

## Provenance

The starting Python research scripts were provided by the repository owner. The original content hashes are recorded in `docs/python_sources.json`; subsequent integration and correctness changes are described in `docs/SELECTION.md`. This repository makes no claim that the CODA algorithm or scanner-decoding libraries were authored by its maintainer.


The timing wrapper creates temporary copies of the locally installed CODA registration and mask functions with elapsed-time hooks. It checks for the expected source anchors, preserves the original local files, and removes the temporary copies afterwards. This instrumentation does not claim authorship of the CODA algorithm; its original notices remain in the temporary copies.
