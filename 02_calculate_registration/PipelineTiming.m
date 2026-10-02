classdef PipelineTiming < handle
    % Per-run CSV logger shared by the instrumented CODA wrapper.
    properties
        Filename
        RunId
        Scanner
        Scanners
        ImageFolder
        Resolution
        Mpp
        Configuration = ''
        Active = []
    end
    methods
        function obj = PipelineTiming(folder, scanner, manifest, mpp)
            obj.ImageFolder = folder;
            obj.Scanner = char(scanner);
            if isempty(obj.Scanner); obj.Scanner = 'unknown'; end
            obj.Scanners = containers.Map('KeyType','char','ValueType','char');
            if ~isempty(manifest)
                tab = readtable(manifest, 'TextType','string', 'VariableNamingRule','preserve', ...
                    'Delimiter',',','ReadVariableNames',true);
                assert(all(ismember({'image','scanner'},tab.Properties.VariableNames)), ...
                    'Scanner manifest requires image,scanner columns.');
                for k=1:height(tab)
                    key = PipelineTiming.imageId(char(tab.image(k)));
                    value = char(tab.scanner(k));
                    assert(~isempty(key) && ~ismissing(tab.scanner(k)) && ...
                        ~isempty(strtrim(value)) && ~isKey(obj.Scanners,key), ...
                        'Scanner manifest needs unique image IDs and nonempty scanners.');
                    obj.Scanners(key) = value;
                end
            end
            [~,obj.Resolution] = fileparts(folder);
            obj.Mpp = '';
            if ~isempty(mpp); obj.Mpp = num2str(mpp,17); end
            obj.RunId = char(java.util.UUID.randomUUID());
            out = fullfile(folder,'timings');
            if ~isfolder(out); mkdir(out); end
            obj.Filename = fullfile(out,['calculate_registration_',obj.RunId,'.csv']);
            fid = fopen(obj.Filename,'w','n','UTF-8');
            assert(fid>=0,'Cannot create timing log.');
            cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
            fprintf(fid,['run_id,started_utc,computer,scanner,image,source,pipeline,' ...
                'phase,resolution,mpp,status,seconds,detail\n']);
            fprintf('Timing log: %s\n',obj.Filename);
        end
        function startImage(obj, name, status, phase)
            if nargin<4; phase='image_total'; end
            assert(isempty(obj.Active),'Previous image timer is still active.');
            obj.Active = struct('name',name,'status',status,'phase',phase, ...
                'started',PipelineTiming.utcNow(),'clock',tic);
        end
        function finishImage(obj, failure)
            if isempty(obj.Active); return; end
            row=obj.Active;
            elapsed=toc(row.clock);
            obj.Active=[];
            detail=obj.Configuration;
            if nargin>1; row.status='error'; detail=failure.message; end
            obj.record(row.name,row.phase,row.status,elapsed,row.started,detail);
        end
        function record(obj,name,phase,status,seconds,started,detail)
            scanner=obj.Scanner;
            key=PipelineTiming.imageId(name);
            if isKey(obj.Scanners,key); scanner=obj.Scanners(key); end
            source='';
            if ~isempty(name); source=fullfile(obj.ImageFolder,name); end
            computer=getenv('COMPUTERNAME');
            if isempty(computer); computer=getenv('HOSTNAME'); end
            fields={obj.RunId,started,computer,scanner,key,source, ...
                'calculate_registration',phase,obj.Resolution,obj.Mpp,status, ...
                sprintf('%.6f',seconds),detail};
            % Quote every field, including embedded quotes/newlines in names/errors.
            fields=cellfun(@(x) ['"',strrep(char(x),'"','""'),'"'],fields,'UniformOutput',false);
            fid=fopen(obj.Filename,'a','n','UTF-8');
            assert(fid>=0,'Cannot append timing log.');
            cleanup=onCleanup(@() fclose(fid)); %#ok<NASGU>
            fprintf(fid,'%s\n',strjoin(fields,','));
            fprintf('Time for %s (%s): %.3f s [%s]\n',name,phase,seconds,status);
        end
    end
    methods (Static)
        function key=imageId(name)
            if isempty(name); key=''; return; end
            [~,stem,extension]=fileparts(name);
            key=[stem,extension];
            suffixes={'.ome.tiff','.ome.tif','.tiff','.tif','.vsi','.czi','.svs', ...
                '.ndpi','.ndp','.scn','.mrxs','.dcm','.qptiff','.isyntax','.i2syntax'};
            for k=1:numel(suffixes)
                if endsWith(lower(key),suffixes{k}); key=key(1:end-length(suffixes{k})); return; end
            end
        end
        function value=utcNow()
            value=char(datetime('now','TimeZone','UTC', ...
                'Format',"yyyy-MM-dd'T'HH:mm:ss.SSSXXX"));
        end
    end
end
