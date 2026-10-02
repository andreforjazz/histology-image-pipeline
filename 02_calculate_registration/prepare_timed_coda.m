function cleanup = prepare_timed_coda(coda_folder)
% Add timers to temporary copies; external CODA source files stay unchanged.
% Exact, unique anchors deliberately reject incompatible CODA revisions.
folder=tempname;
mkdir(folder);
cleanup=onCleanup(@() remove_temporary(folder));
s=fileread(fullfile(coda_folder,'calculate_image_registration.m'));
s=replace_once(s,'function calculate_image_registration(pth,IHC,zc,regE)', ...
    'function timed_coda(pth,IHC,zc,timing,regE)');
s=replace_once(s,'% set up center image',sprintf([ ...
    'timing.startImage(imlist(zc).name,''reference'');\n%% set up center image']));
s=replace_once(s,'img=imzcg;TA=TAzc;',sprintf('timing.finishImage();\nimg=imzcg;TA=TAzc;'));
s=replace_once(s,'    t1=tic;',sprintf([ ...
    '    t1=tic;\n    timingStatus=''ok'';\n' ...
    '    if exist([matpth,''D\\'',imlist(mv(kk)).name(1:end-3),''mat''],''file''); timingStatus=''reused''; end\n' ...
    '    timing.startImage(imlist(mv(kk)).name,timingStatus);']));
s=replace_once(s,'    toc(t1);',sprintf('    toc(t1);\n    timing.finishImage();'));
write_source(fullfile(folder,'timed_coda.m'),s);

s=fileread(fullfile(coda_folder,'calculate_tissue_ws.m'));
s=replace_once(s,'function calculate_tissue_ws(pth,calc_style)', ...
    'function timed_masks(pth,calc_style,timing)');
s=replace_once(s,'    nm=imlist(k).name;',sprintf([ ...
    '    nm=imlist(k).name;\n    timing.startImage(nm,''ok'',''mask'');']));
s=replace_once(s,"disp('  already done');continue;", ...
    "disp('  already done'); timing.Active.status='skipped_existing'; timing.finishImage(); continue;");
s=replace_once(s,"    disp('  done');",sprintf('    timing.finishImage();\n    disp(''  done'');'));
write_source(fullfile(folder,'timed_masks.m'),s);
addpath(folder,'-begin');
end

function s=replace_once(s,old,new)
assert(numel(strfind(s,old))==1, ...
    'Unsupported CODA source revision: timing anchor is missing or ambiguous: %s',old);
s=strrep(s,old,new);
end

function write_source(filename,s)
fid=fopen(filename,'w','n','UTF-8');
assert(fid>=0,'Cannot create temporary timed CODA function.');
cleanup=onCleanup(@() fclose(fid)); %#ok<NASGU>
fprintf(fid,'%s',s);
end

function remove_temporary(folder)
if contains([path,pathsep],[folder,pathsep]); rmpath(folder); end
clear timed_coda timed_masks
for name={'timed_coda.m','timed_masks.m'}
    filename=fullfile(folder,name{1});
    if isfile(filename); delete(filename); end
end
if isfolder(folder); rmdir(folder); end
end
