function validate_matlab(output_folder)
% Optional integration check using only generated synthetic RGB data.
root = fileparts(fileparts(mfilename('fullpath')));
addpath(fullfile(root, '02_calculate_registration'));
addpath(genpath(fullfile(root, '02_calculate_registration', 'coda')));
if ~isfolder(output_folder); mkdir(output_folder); end
[x,y] = meshgrid(0:63,0:47);
image = uint8(cat(3,mod(x*7,230),mod(y*11,230),mod((x+y)*3,230)));
T = [cosd(17) sind(17) 0; -sind(17) cosd(17) 0; 3 -2 1];
cent = [32.5 24.5];
expected_affine = register_global_im(image, affine2d(T), cent, 0, [241 241 241]);
D = zeros(48,64,2); D(:,:,1) = 2; D(:,:,2) = -3;
expected_elastic = imwarp(image,D,'nearest','FillValues',[241 241 241]);
save(fullfile(output_folder,'matlab_reference.mat'),'image','T','cent','D','expected_affine','expected_elastic');

% Exercise the actual CODA entry point on two identical tissue-like sections.
folder = fullfile(output_folder,'synthetic_2x');
if ~isfolder(folder); mkdir(folder); end
rng(12);
[x,y] = meshgrid(1:256,1:256);
mask = ((x-120).^2/85^2 + (y-130).^2/95^2 < 1);
im = uint8(241*ones(256,256,3));
for channel = 1:3
    layer = im(:,:,channel);
    texture = uint8(70 + channel*30 + 30*rand(256));
    layer(mask) = texture(mask);
    im(:,:,channel) = layer;
end
imwrite(im, fullfile(folder,'a.tif'));
imwrite(im, fullfile(folder,'b.tif'));
run_registration(folder,0,1,[]);
warps = fullfile(folder,'registered','elastic registration','save_warps');
v = load(fullfile(warps,'b.mat'));
assert(isfield(v,'tform_python'), 'Numeric transform export missing.');
assert(isfile(fullfile(warps,'D','b.mat')), 'Elastic transform missing.');
assert(isfile(fullfile(folder,'registered','elastic registration','b.jpg')));
disp('MATLAB transform fixtures and synthetic CODA integration: PASS');
end
