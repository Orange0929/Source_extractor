-- Source Extractor receiver. Run inside the intended REAPER instance.
-- ROOT is supplied by the app when preparing the stable launcher script.
local version = 2
local session = reaper.genGuid(''):gsub('[^%w%-]', '')
local folder = ROOT .. '/' .. session
reaper.RecursiveCreateDirectory(folder, 0)
local ext_key = ROOT
local previous = reaper.GetExtState('SourceExtractorReceivers', ext_key)
if previous ~= '' and previous:match('^[%w%-]+$') then
  for _,name in ipairs({'heartbeat.json','heartbeat-0.json','heartbeat-1.json'}) do os.remove(ROOT..'/'..previous..'/'..name) end
end
reaper.SetExtState('SourceExtractorReceivers', ext_key, session, false)
local function json(value)
  if type(value) == 'table' then
    local fields={}
    for k,v in pairs(value) do fields[#fields+1]=json(k)..':'..json(v) end
    return '{'..table.concat(fields, ',')..'}'
  elseif type(value)=='number' or type(value)=='boolean' then return tostring(value) end
  return '"'..tostring(value):gsub('[%z\1-\31\\"]',function(c) return string.format('\\u%04x',string.byte(c)) end)..'"'
end
local function write_json(path,value)
  local f=io.open(path..'.tmp','wb')
  if not f then return false end
  f:write(json(value));f:close()
  os.remove(path)
  return os.rename(path..'.tmp',path)
end
local function project_id(proj,create)
  local _,id=reaper.GetProjExtState(proj,'SourceExtractor','project_id')
  if id=='' and create then
    id=reaper.genGuid('')
    reaper.SetProjExtState(proj,'SourceExtractor','project_id',id)
  end
  return id
end
local function project_name(proj)
  local name=reaper.GetProjectName(proj)
  return name~='' and name or '(저장 안 된 프로젝트)'
end
local function track_name(track)
  local _,name=reaper.GetTrackName(track)
  return tostring(math.floor(reaper.GetMediaTrackInfo_Value(track,'IP_TRACKNUMBER'))) .. ' · ' .. name
end
local function snapshot()
  local projects={}
  local index=0
  while true do
    local proj=reaper.EnumProjects(index)
    if not proj then break end
    local id=project_id(proj,false)
    if id~='' then projects[id]=true end
    index=index+1
  end
  local active=reaper.EnumProjects(-1)
  return {protocol=version, session=session, updated=os.time(), projects=projects,
          connect_token=CONNECT_TOKEN or '', window_key=WINDOW_KEY or '',
          active_project=active and project_name(active) or '(프로젝트 없음)'}
end
local function perform(req)
  if tonumber(req.expires or '0') < os.time() then error('요청 시간이 지났습니다. 다시 전송하세요.',0) end
  if req.action=='capture' then
    local proj,path=reaper.EnumProjects(-1)
    local track=proj and reaper.GetSelectedTrack(proj,0)
    if not track then error('REAPER에서 받을 프로젝트와 트랙을 먼저 선택하세요.',0) end
    -- Duplicated RPP files may share the persisted marker. Capturing an ambiguous
    -- tab assigns a fresh identity to that tab instead of using its path/pointer.
    local id=project_id(proj,true)
    local index=0
    while true do
      local other=reaper.EnumProjects(index)
      if not other then break end
      if other~=proj and project_id(other,false)==id then
        id=reaper.genGuid('');reaper.SetProjExtState(proj,'SourceExtractor','project_id',id);break
      end
      index=index+1
    end
    return {ok=true,target={project_id=id, instance=session, project_path=path or '',
            track_guid=reaper.GetTrackGUID(track),project_name=project_name(proj),track_name=track_name(track)}}
  end
  local proj,track
  local matches=0
  local index=0
  while true do
    local candidate=reaper.EnumProjects(index)
    if not candidate then break end
    if project_id(candidate,false)==req.project_id then
      matches=matches+1;proj=candidate
    end
    index=index+1
  end
  if matches>1 then error('같은 연결 ID의 프로젝트가 여러 개 열려 있습니다. 받을 탭에서 대상을 다시 지정하세요.',0) end
  if not proj then error('지정한 프로젝트가 닫혀 있습니다. 해당 프로젝트를 다시 열어주세요.',0) end
  for i=0,reaper.CountTracks(proj)-1 do
    local candidate=reaper.GetTrack(proj,i)
    if reaper.GetTrackGUID(candidate)==req.track_guid then track=candidate;break end
  end
  if not track then error('지정한 트랙이 삭제됐습니다. 전송 대상을 다시 지정하세요.',0) end
  local source=reaper.PCM_Source_CreateFromFile(req.media)
  if not source then error('전송 오디오를 열 수 없습니다.',0) end
  local duration,is_qn=reaper.GetMediaSourceLength(source)
  if duration<=0 or is_qn then reaper.PCM_Source_Destroy(source);error('오디오 길이를 확인할 수 없습니다.',0) end
  local cursor=reaper.GetCursorPositionEx(proj)
  reaper.Undo_BeginBlock2(proj)
  local item,attached
  local ok,err=pcall(function()
    item=reaper.AddMediaItemToTrack(track)
    if not item then error('아이템을 만들 수 없습니다.',0) end
    local take=reaper.AddTakeToMediaItem(item)
    if not take then error('테이크를 만들 수 없습니다.',0) end
    if not reaper.SetMediaItemTake_Source(take,source) then error('오디오를 연결할 수 없습니다.',0) end
    attached=true
    reaper.SetMediaItemInfo_Value(item,'D_POSITION',cursor)
    reaper.SetMediaItemInfo_Value(item,'D_LENGTH',duration)
    reaper.GetSetMediaItemTakeInfo_String(take,'P_NAME',req.name or '',true)
  end)
  if not ok then
    if item then reaper.DeleteTrackMediaItem(track,item) end
    if not attached then reaper.PCM_Source_Destroy(source) end
  else reaper.SetEditCurPos2(proj,cursor+duration,false,false) end
  reaper.Undo_EndBlock2(proj,'Source Extractor: insert selected audio',-1)
  reaper.UpdateArrange()
  if not ok then error(err,0) end
  return {ok=true,project_name=project_name(proj),track_name=track_name(track)}
end
local function decode_request(path)
  local f=io.open(path,'rb')
  if not f then error('요청 파일을 읽을 수 없습니다.',0) end
  local text=f:read('*a');f:close()
  if #text>262144 then error('요청이 너무 큽니다.',0) end
  local req={}
  for line in text:gmatch('[^\n]+') do
    local clean_line=line:gsub('\r$','')
    local key,hex=clean_line:match('^([a-z_]+)=([0-9a-f]*)$')
    if not key or #hex%2~=0 then error('요청 파일 형식이 올바르지 않습니다.',0) end
    req[key]=hex:gsub('..',function(pair) return string.char(tonumber(pair,16)) end)
  end
  return req
end
local function process_requests()
  reaper.EnumerateFiles(folder,-1) -- invalidate REAPER's cached directory listing
  local files={}
  local index=0
  while true do
    local name=reaper.EnumerateFiles(folder,index)
    if not name then break end
    if name:match('^[a-f0-9]+%.req$') then files[#files+1]=name end
    index=index+1
  end
  table.sort(files)
  for _,name in ipairs(files) do
    local path=folder..'/'..name
    local processing=path..'.processing'
    if os.rename(path,processing) then
      local ok,result=pcall(function() return perform(decode_request(processing)) end)
      write_json(folder..'/'..name:gsub('%.req$','.json'),ok and result or {error=tostring(result)})
      os.remove(processing)
    end
  end
end
local last_poll,last_heartbeat=-1,-1
local sequence=0
local function loop()
  if reaper.GetExtState('SourceExtractorReceivers',ext_key)~=session then return end
  local now=reaper.time_precise()
  if now-last_poll>.1 then process_requests();last_poll=now end
  if now-last_heartbeat>.5 then
    sequence=sequence+1
    local state=snapshot();state.sequence=sequence
    write_json(folder..'/heartbeat-'..tostring(sequence%2)..'.json',state)
    last_heartbeat=now
  end
  reaper.defer(loop)
end
reaper.atexit(function()
  os.remove(folder..'/heartbeat-0.json');os.remove(folder..'/heartbeat-1.json')
end)
loop()
