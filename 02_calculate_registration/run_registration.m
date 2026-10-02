function run_registration(image_folder, IHC, reference_index, mask_style, scanner, scanner_manifest, registration_mpp)
% RUN_REGISTRATION Calculate CODA global and elastic transforms on low-res TIFFs.
% Example: run_registration('D:\dataset\2x',0,[],1,'Olympus VS200','',5)
% scanner_manifest: optional CSV with image,scanner columns for mixed scanners.
% registration_mpp: actual low-resolution micrometres/pixel (optional metadata).
% reference_index=[] selects the middle image in MATLAB dir order.
% mask_style=[] lets get_ims create missing masks automatically.
if nargin < 2; IHC = 0; end
if nargin < 3; reference_index = []; end
if nargin < 4; mask_style = []; end
if nargin < 5; scanner = 'unknown'; end
if nargin < 6; scanner_manifest = ''; end
if nargin < 7; registration_mpp = []; end
assert(isempty(registration_mpp) || (isscalar(registration_mpp) && ...
    isfinite(registration_mpp) && registration_mpp>0), 'MPP must be positive.');
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
addpath(here);
timing = PipelineTiming(image_folder,scanner,scanner_manifest,registration_mpp);
timing.Configuration = sprintf('IHC=%g; reference_index=%s; mask_style=%s', ...
    IHC,mat2str(reference_index),mat2str(mask_style));
timed_cleanup = prepare_timed_coda(fullfile(here,'coda')); %#ok<NASGU>
batch_start = tic;
batch_utc = PipelineTiming.utcNow();
try
    cd(fullfile(here, 'coda'));
    addpath(pwd, fullfile(pwd, 'image registration base functions'));
    if ~isempty(mask_style)
        assert(ismember(mask_style, [1 2]), 'mask_style must be 1, 2, or [].');
        timed_masks(image_folder, mask_style, timing);
    end
    timed_coda(image_folder, IHC, reference_index, timing);
    % Export plain numeric matrices so Python can apply new transforms without Engine.
    warps = fullfile(image_folder, 'registered', 'elastic registration', 'save_warps');
    matfiles = dir(fullfile(warps, '*.mat'));
    for k = 1:numel(matfiles)
        filename = fullfile(warps, matfiles(k).name);
        [~,image_name]=fileparts(matfiles(k).name);
        timing.startImage([image_name,'.tif'],'ok','export_transform');
        values = load(filename);
        if isfield(values, 'tform')
            tform_python = values.tform.T; %#ok<NASGU>
            save(filename, 'tform_python', '-append');
        end
        timing.finishImage();
    end
    timing.record('','batch_total','ok',toc(batch_start),batch_utc,'');
catch failure
    timing.finishImage(failure);
    timing.record('','batch_total','error',toc(batch_start),batch_utc,failure.message);
    rethrow(failure);
end
end

function restore_session(folder, search_path)
cd(folder);
path(search_path);
end
