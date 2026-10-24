-- Generated request header supplies req. Only this script is sent to REAPER;
-- media files are never passed to the application as files to open.
local function json(value)
  if type(value) == 'table' then
    local fields = {}
    for key, val in pairs(value) do fields[#fields+1] = json(key)..':'..json(val) end
    return '{'..table.concat(fields, ',')..'}'
  elseif type(value) == 'boolean' or type(value) == 'number' then return tostring(value)
  end
  local escaped = tostring(value):gsub('[%z\1-\31\\"]', function(c)
    return string.format('\\u%04x', string.byte(c))
  end)
  return '"'..escaped..'"'
end
local function reply(data)
  local f = io.open(req.response, 'wb')
  if f then f:write(json(data)); f:close() end
end
local function session_id()
  local id = reaper.GetExtState('SourceExtractor', 'session')
  if id == '' then
    id = reaper.genGuid('')
    reaper.SetExtState('SourceExtractor', 'session', id, false)
  end
  return id
end
local function project_label(proj)
  local name = reaper.GetProjectName(proj)
  return name ~= '' and name or '(저장 안 된 프로젝트)'
end
local function track_label(track)
  local _, name = reaper.GetTrackName(track)
  return tostring(math.floor(reaper.GetMediaTrackInfo_Value(track, 'IP_TRACKNUMBER')))..' · '..name
end
local function run()
  -- A dialog blocking REAPER must not cause insertion after the app timed out.
  if os.time() > req.expires then error('요청 시간이 지났습니다. 다시 전송하세요.') end
  local session = session_id()
  if req.action == 'capture' then
    local proj, path = reaper.EnumProjects(-1, '')
    local track = proj and reaper.GetSelectedTrack(proj, 0)
    if not track then error('REAPER에서 받을 프로젝트와 일반 트랙을 먼저 선택하세요.') end
    return {ok=true, target={project_path=path or '', project_pointer=tostring(proj),
      session=session, track_guid=reaper.GetTrackGUID(track), project_name=project_label(proj), track_name=track_label(track)}}
  end
  local proj, track
  local index = 0
  while true do
    local candidate, path = reaper.EnumProjects(index, '')
    if not candidate then break end
    local same_session = session == req.session and tostring(candidate) == req.project_pointer
    local same_path = session ~= req.session and req.project_path ~= '' and (path or ''):lower() == req.project_path:lower()
    if same_session or same_path then
      for i=0,reaper.CountTracks(candidate)-1 do
        local tr = reaper.GetTrack(candidate, i)
        if reaper.GetTrackGUID(tr) == req.track_guid then proj=candidate; track=tr; break end
      end
    end
    if track then break end
    index = index+1
  end
  if not track then error('지정한 프로젝트가 닫혔거나 트랙이 없습니다. 전송 대상을 다시 지정하세요.') end
  local source = reaper.PCM_Source_CreateFromFile(req.media)
  if not source then error('전송 오디오를 열 수 없습니다.') end
  local duration, is_qn = reaper.GetMediaSourceLength(source)
  if duration <= 0 or is_qn then
    reaper.PCM_Source_Destroy(source)
    error('전송 오디오 길이를 확인할 수 없습니다.')
  end
  local cursor = reaper.GetCursorPositionEx(proj)
  reaper.Undo_BeginBlock2(proj)
  local item, attached
  local ok, err = pcall(function()
    item = reaper.AddMediaItemToTrack(track)
    if not item then error('아이템을 만들 수 없습니다.') end
    local take = reaper.AddTakeToMediaItem(item)
    if not take then error('테이크를 만들 수 없습니다.') end
    if not reaper.SetMediaItemTake_Source(take, source) then error('오디오를 연결할 수 없습니다.') end
    attached = true
    reaper.SetMediaItemInfo_Value(item, 'D_POSITION', cursor)
    reaper.SetMediaItemInfo_Value(item, 'D_LENGTH', duration)
    reaper.GetSetMediaItemTakeInfo_String(take, 'P_NAME', req.name, true)
  end)
  if not ok then
    if item then reaper.DeleteTrackMediaItem(track, item) end
    if not attached then reaper.PCM_Source_Destroy(source) end
  else
    reaper.SetEditCurPos2(proj, cursor+duration, false, false)
  end
  reaper.Undo_EndBlock2(proj, 'Source Extractor: insert selected audio', -1)
  reaper.UpdateArrange()
  if not ok then error(err) end
  return {ok=true, project_name=project_label(proj), track_name=track_label(track)}
end
local ok, result = pcall(run)
if ok then reply(result) else reply({error=tostring(result)}) end
