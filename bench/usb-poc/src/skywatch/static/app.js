const $ = id => document.getElementById(id);
let state = null, cameraCount = -1, maskMode = false, settingsInitialized = false;
const cameraImages = new Map();
function text(id, value) { $(id).textContent = value; }
function toast(message) { text('toast', message); $('toast').style.display = 'block'; clearTimeout(toast.timer); toast.timer = setTimeout(() => $('toast').style.display = 'none', 4500); }
async function post(path, body) {
  try {
    const response = await fetch(path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body || {})});
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Invalid settings');
    return result;
  } catch (error) { toast(error.message); return null; }
}
$('settings').addEventListener('submit', async event => { event.preventDefault(); if (await post('/api/settings',{threshold:Number($('threshold').value),min_area:Number($('min-area').value)})) toast('Detection settings applied'); });
$('threshold').oninput = () => text('threshold-value', $('threshold').value);
$('min-area').oninput = () => text('area-value', $('min-area').value + ' px');
$('reset').onclick = async () => { if (await post('/api/reset')) toast('Background reset. Keep cameras still while the scene settles.'); };
$('capture').onclick = async () => { const result = await post('/api/calibration/capture'); if (result) toast('Saved calibration pair ' + result.pair); };
$('mask-toggle').onchange = event => { maskMode = event.target.checked; };
function buildCameras(cameras) {
  $('cameras').replaceChildren();
  cameraImages.clear();
  cameras.forEach(camera => {
    const node = document.createElement('article'); node.className = 'camera';
    node.innerHTML = `<div class="camera-head"><span class="name"></span><span class="health"></span></div><div class="camera-viewport"><img alt="Camera feed with tracked motion overlays"><div class="no-signal">WAITING FOR CAMERA</div><span class="frame-label"></span></div><div class="camera-meta"><span class="resolution"></span><span class="track-info"></span></div>`;
    node.querySelector('.name').textContent = `${String(camera.id + 1).padStart(2,'0')} / ${camera.name}`;
    $('cameras').append(node); cameraImages.set(camera.id,{node,busy:false,url:null});
  }); cameraCount = cameras.length;
}
async function updateFrame(camera) {
  const item = cameraImages.get(camera.id); if (item.busy || !camera.connected) return;
  item.busy = true;
  try {
    const response = await fetch(`/api/cameras/${camera.id}/frame.jpg?mask=${maskMode}&t=${Date.now()}`);
    if (!response.ok) throw new Error('No fresh frame');
    const url = URL.createObjectURL(await response.blob());
    if (item.url) URL.revokeObjectURL(item.url);
    item.url = url; item.node.querySelector('img').src = url;
    item.node.querySelector('.no-signal').classList.add('hidden');
  } catch { item.node.querySelector('.no-signal').classList.remove('hidden'); }
  finally { item.busy = false; }
}
function render(s) {
  state = s;
  const demo = s.mode === 'demo';
  text('mode', demo ? '● SIMULATION' : '● LIVE CAMERAS');
  text('notice', (demo ? 'SIMULATED INPUT · Synthetic camera images run through the real detection pipeline. ' : 'LIVE INPUT · ') + s.status);
  text('camera-count', `${s.cameras.filter(c => c.connected).length} / ${s.cameras.length}`);
  text('camera-caption', demo ? 'Synthetic stereo pair · 3 m baseline' : 'USB / network sources');
  text('track-count', s.cameras.reduce((sum,c) => sum + c.tracks.length, 0));
  const target = s.tracks[0];
  $('range').replaceChildren(document.createTextNode(target ? target.range_m.toFixed(1) : '—'));
  if (target) { const unit = document.createElement('em'); unit.textContent = 'm'; $('range').append(unit); }
  text('range-caption', target ? `1 px sensitivity ≈ ${target.sensitivity_m.toFixed(1)} m${demo ? ' · simulated' : ''}` : 'No accepted two-view estimate');
  text('latency', s.processing_ms + ' ms');
  text('timing', s.pair_timing_ms === null ? 'Pair timing unavailable' : `Pair timing bound · ${s.pair_timing_ms} ms`);
  text('frames', s.frames_total.toLocaleString() + ' frames processed');
  text('voxel-count', s.voxels.length + ' supported cells');
  text('volume-mode', s.calibrated ? (demo ? 'Synthetic calibration' : 'Measured calibration') : 'Calibration required');
  text('uptime', `${Math.floor(s.uptime_s / 60).toString().padStart(2,'0')}:${(s.uptime_s % 60).toString().padStart(2,'0')} uptime`);
  text('event-count', s.events_total);
  $('capture').disabled = demo;
  if (cameraCount !== s.cameras.length) buildCameras(s.cameras);
  s.cameras.forEach(c => {
    const item = cameraImages.get(c.id), n = item.node;
    n.querySelector('.health').textContent = c.connected ? '● ONLINE' : '○ OFFLINE';
    n.querySelector('.health').className = 'health ' + (c.connected ? 'online' : 'offline');
    n.querySelector('.resolution').textContent = c.size ? c.size.join(' × ') + ' · ' + c.type.toUpperCase() : c.type.toUpperCase();
    n.querySelector('.track-info').textContent = c.warming ? 'SETTLING' : `${c.tracks.length} TRACKS`;
    n.querySelector('.frame-label').textContent = demo ? 'SYNTHETIC' : 'CAM ' + (c.id + 1);
    if (!c.connected) { const message = n.querySelector('.no-signal'); message.classList.remove('hidden'); message.textContent = c.error || 'NO FRESH FRAME'; }
    updateFrame(c);
  });
  const body = $('event-body'); body.replaceChildren();
  if (!s.events.length) { const row = document.createElement('tr'); const cell = document.createElement('td'); cell.colSpan = 5; cell.className = 'empty'; cell.textContent = 'Waiting for persistent motion.'; row.append(cell); body.append(row); }
  s.events.slice(0,12).forEach(e => { const row = document.createElement('tr'); [new Date(e.time * 1000).toLocaleTimeString(),e.event,'CAM ' + e.camera,String(e.track).padStart(3,'0'),e.mode === 'demo' ? 'SIMULATED' : 'LIVE'].forEach((value, index) => { const cell = document.createElement('td'); cell.textContent = value; if (index === 4) cell.className = 'event-chip'; row.append(cell); }); body.append(row); });
  if (!settingsInitialized && s.settings) { $('threshold').value = s.settings.threshold; $('min-area').value = s.settings.min_area; $('threshold').oninput(); $('min-area').oninput(); settingsInitialized = true; }
  drawActivity(); drawSpace();
}
async function poll() {
  try {
    const response = await fetch('/api/state'); if (!response.ok) throw new Error();
    const s = await response.json(); if (s.settings) render(s);
    text('connection', '● ENGINE CONNECTED'); $('connection').style.color = 'var(--green)';
  } catch {
    text('connection','○ ENGINE OFFLINE'); $('connection').style.color = 'var(--orange)';
    text('notice','Engine connection lost. Displayed telemetry is stale.'); text('range','—');
    cameraImages.forEach(({node}) => { node.querySelector('.no-signal').classList.remove('hidden'); node.querySelector('.no-signal').textContent = 'ENGINE OFFLINE'; });
  }
  text('clock',new Date().toLocaleTimeString('en-GB') + ' LOCAL'); setTimeout(poll, 250);
}
function fit(canvas) {
  const rect = canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  if (canvas.width !== Math.round(rect.width*dpr) || canvas.height !== Math.round(rect.height*dpr)) { canvas.width = Math.round(rect.width*dpr); canvas.height = Math.round(rect.height*dpr); }
  const ctx = canvas.getContext('2d'); ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,rect.width,rect.height); return [ctx,rect.width,rect.height];
}
function drawActivity() {
  const [c,w,h] = fit($('activity')); if (!state) return;
  const points = state.history || [], max = Math.max(4,...points.map(p => p.motion)), x0 = 38, y0 = 16, bottom = h-28;
  c.font = '9px monospace'; c.lineWidth = 1;
  for (let i=0;i<3;i++) { const y = y0+(bottom-y0)*i/2; c.strokeStyle = '#26333d'; c.beginPath(); c.moveTo(x0,y); c.lineTo(w-18,y); c.stroke(); c.fillStyle='#6d818f'; c.fillText(String(Math.round(max*(1-i/2))),15,y+3); }
  c.fillText('-120s',x0,h-10); c.fillText('now',w-37,h-10);
  if (!points.length) return;
  const xy = points.map((p,i) => [x0 + (w-x0-20)*(120-points.length+i)/119, bottom-p.motion/max*(bottom-y0)]);
  c.beginPath(); xy.forEach(([x,y],i) => i ? c.lineTo(x,y) : c.moveTo(x,y)); c.strokeStyle='#acdf77'; c.lineWidth=1.5; c.stroke(); c.lineTo(xy.at(-1)[0],bottom); c.lineTo(xy[0][0],bottom); c.closePath(); c.fillStyle='#acdf7714'; c.fill();
}
let yaw = -.43, tilt = .61, zoom = 1, dragging = null;
const space = $('space');
space.onpointerdown = e => { dragging = [e.clientX,e.clientY]; space.setPointerCapture(e.pointerId); };
space.onpointermove = e => { if (!dragging) return; yaw += (e.clientX-dragging[0])*.008; tilt = Math.max(.1,Math.min(1.35,tilt+(e.clientY-dragging[1])*.006)); dragging=[e.clientX,e.clientY]; drawSpace(); };
space.onpointerup = space.onpointercancel = () => { dragging=null; };
space.addEventListener('wheel',e => { e.preventDefault(); zoom = Math.max(.5,Math.min(3,zoom*Math.exp(-e.deltaY*.001))); drawSpace(); },{passive:false});
function drawSpace() {
  const [c,w,h] = fit(space); if (!state) return;
  if (!state.calibrated) { c.fillStyle='#869a9c'; c.font='12px monospace'; c.textAlign='center'; c.fillText('Calibrate the camera pair to enable 3D',w/2,h/2); c.textAlign='left'; return; }
  const bounds=state.bounds, midZ=(bounds[2][0]+bounds[2][1])/2, scale=Math.min(w/1.3,h)/Math.max(bounds[2][1],bounds[0][1]-bounds[0][0])*zoom;
  function project(p) { const x=p[0], y=-p[1], z=p[2]-midZ; const rx=x*Math.cos(yaw)-z*Math.sin(yaw), rz=x*Math.sin(yaw)+z*Math.cos(yaw); return [w*.5+rx*scale,h*.52+rz*Math.sin(tilt)*scale-y*Math.cos(tilt)*scale]; }
  function line(a,b,color,width=1) { const p=project(a),q=project(b); c.strokeStyle=color;c.lineWidth=width;c.beginPath();c.moveTo(...p);c.lineTo(...q);c.stroke(); }
  const floor=bounds[1][1], [xmin,xmax]=bounds[0], [zmin,zmax]=bounds[2];
  for(let i=0;i<=10;i++){const x=xmin+(xmax-xmin)*i/10,z=zmin+(zmax-zmin)*i/10;line([x,floor,zmin],[x,floor,zmax],'#29413c88');line([xmin,floor,z],[xmax,floor,z],'#29413c88');}
  for(const x of [xmin,xmax])for(const z of [zmin,zmax])line([x,bounds[1][0],z],[x,floor,z],'#2b443c88');
  c.font='9px monospace'; c.fillStyle='#698779';
  for(const z of [zmin,zmax]){const p=project([xmax,floor,z]);c.fillText(z+' m',p[0]+6,p[1]);}
  for(const v of state.voxels){const p=project(v);c.fillStyle='#a7df7166';const size=Math.max(2,scale*Math.min(...state.voxel_size)*.75);c.fillRect(p[0]-size/2,p[1]-size/2,size,size);}
  (state.camera_positions || []).forEach((pos,i)=>{const p=project(pos);c.fillStyle='#f4ad67';c.fillRect(p[0]-4,p[1]-4,8,8);c.font='9px monospace';c.fillText('C'+(i+1),p[0]+8,p[1]+3);for(const target of state.tracks)line(pos,target.position,'#f4ad6755');});
  for(const target of state.tracks){const p=project(target.position);c.strokeStyle='#c7f799';c.lineWidth=1;c.beginPath();c.arc(p[0],p[1],8,0,Math.PI*2);c.stroke();c.fillStyle='#d6edc3';c.font='10px monospace';c.fillText(target.range_m.toFixed(1)+' m',p[0]+13,p[1]-9);}
}
window.addEventListener('resize',()=>{drawSpace();drawActivity();});
poll();
