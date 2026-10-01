function run_registration(image_folder, IHC, reference_index, mask_style)
% RUN_REGISTRATION Calculate CODA global and elastic transforms on low-res TIFFs.
% Example: run_registration('D:\dataset\2x', 0, [], 1)
% reference_index=[] selects the middle image in MATLAB dir order.
% mask_style=[] lets get_ims create missing masks automatically.
if nargin < 2; IHC = 0; end
if nargin < 3; reference_index = []; end
if nargin < 4; mask_style = []; end
assert(isfolder(image_folder), 'Image folder does not exist.');
[ok, folder_info] = fileattrib(image_folder);
assert(ok, 'Cannot resolve image folder.');
image_folder = folder_info.Name;
files = dir(fullfile(image_folder, '*.tif'));
assert(numel(files) >= 2, 'Provide at least two low-resolution TIFF images.');
if ~isempty(reference_index)
    assert(isscalar(reference_index) && reference_index == fix(reference_index) && ...
        reference_index >= 1 && reference_index <= numel(files), 'Invalid reference index.');
end
here = fileparts(mfilename('fullpath'));
previous_folder = pwd;
previous_path = path;
cleanup = onCleanup(@() restore_session(previous_folder, previous_path)); %#ok<NASGU>
cd(fullfile(here, 'coda'));
addpath(pwd, fullfile(pwd, 'image registration base functions'));
if ~isempty(mask_style)
    assert(ismember(mask_style, [1 2]), 'mask_style must be 1, 2, or [].');
    calculate_tissue_ws(image_folder, mask_style);
end
calculate_image_registration(image_folder, IHC, reference_index);
% Export plain numeric matrices so Python can apply new transforms without Engine.
warps = fullfile(image_folder, 'registered', 'elastic registration', 'save_warps');
matfiles = dir(fullfile(warps, '*.mat'));
for k = 1:numel(matfiles)
    filename = fullfile(warps, matfiles(k).name);
    values = load(filename);
    if isfield(values, 'tform')
        tform_python = values.tform.T; %#ok<NASGU>
        save(filename, 'tform_python', '-append');
    end
end
end

function restore_session(folder, search_path)
cd(folder);
path(search_path);
end
