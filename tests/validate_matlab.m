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
manifest=fullfile(output_folder,'scanners.csv');
fid=fopen(manifest,'w');
fprintf(fid,'image,scanner\na,Synthetic scanner A\nb,Synthetic scanner B\n');
fclose(fid);
run_registration(folder,0,1,1,'fallback',manifest,5);
warps = fullfile(folder,'registered','elastic registration','save_warps');
v = load(fullfile(warps,'b.mat'));
assert(isfield(v,'tform_python'), 'Numeric transform export missing.');
assert(isfile(fullfile(warps,'D','b.mat')), 'Elastic transform missing.');
assert(isfile(fullfile(folder,'registered','elastic registration','b.jpg')));
logs=dir(fullfile(folder,'timings','calculate_registration_*.csv'));
assert(numel(logs)==1,'Use a fresh output folder for this validation.');
logfile=fullfile(logs(1).folder,logs(1).name);
tab=readtable(logfile,'TextType','string','Delimiter',',','ReadVariableNames',true);
assert(sum(tab.phase=="image_total")==2);
assert(sum(tab.phase=="mask" & tab.status=="ok")==2);
assert(all(tab.seconds>=0));
assert(tab.scanner(tab.phase=="image_total" & tab.image=="a")=="Synthetic scanner A");
assert(tab.status(tab.phase=="image_total" & tab.image=="a")=="reference");
assert(tab.status(tab.phase=="image_total" & tab.image=="b")=="ok");

% Compare instrumented output with unchanged CODA on the same generated inputs.
baseline=fullfile(output_folder,'baseline_2x');
mkdir(baseline);
copyfile(fullfile(folder,'*.tif'),baseline);
previous=pwd;
restore=onCleanup(@() cd(previous)); %#ok<NASGU>
cd(fullfile(root,'02_calculate_registration','coda'));
calculate_tissue_ws(baseline,1);
calculate_image_registration(baseline,0,1);
baseline_warps=fullfile(baseline,'registered','elastic registration','save_warps');
v0=load(fullfile(baseline_warps,'b.mat'));
d0=load(fullfile(baseline_warps,'D','b.mat'));
d1=load(fullfile(warps,'D','b.mat'));
assert(isequal(v.tform_python,v0.tform.T));
assert(isequal(d0.D,d1.D));
assert(isequal(imread(fullfile(baseline,'registered','elastic registration','b.jpg')), ...
    imread(fullfile(folder,'registered','elastic registration','b.jpg'))));
cd(previous);

% Reruns must record reused transforms and skipped masks, not fresh computation.
run_registration(folder,0,1,1,'fallback',manifest,5);
newlogs=dir(fullfile(folder,'timings','calculate_registration_*.csv'));
assert(numel(newlogs)==2);
second=newlogs(~strcmp({newlogs.name},logs(1).name));
reused=readtable(fullfile(second.folder,second.name),'TextType','string','Delimiter',',','ReadVariableNames',true);
assert(sum(reused.phase=="image_total" & reused.status=="reused")==1);
assert(sum(reused.phase=="mask" & reused.status=="skipped_existing")==2);
disp('MATLAB timing, unchanged CODA outputs, reuse labels and transform fixtures: PASS');
end
