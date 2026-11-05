/* Host-side capabilities. The authored iframe keeps its opaque sandbox origin. */
(() => {
  const frame = document.querySelector('iframe[data-resource]');
  const capabilities = new Set(JSON.parse(frame?.dataset.capabilities || '[]'));
  if (!frame || !capabilities.size) return;
  let stream, audio, interval, generation = 0, pending, exporting = false;
  const send = data => frame.contentWindow?.postMessage(data, '*');
  const reply = (id, value, error) => send({ type:'nos-resource-capability-result', id, ok:!error, value, error:error ? {name:error.name || 'Error',message:error.message || String(error)} : undefined });
  const button = document.createElement('button');
  button.hidden = true; button.type = 'button';
  button.textContent = '允许本资源使用麦克风（仅本机音量分析）';
  document.querySelector('header').append(button);
  function stop(notify = true) {
    generation++;
    clearInterval(interval); interval = undefined;
    stream?.getTracks().forEach(track => track.stop()); stream = undefined;
    if (audio && audio.state !== 'closed') void audio.close(); audio = undefined;
    if (pending) { reply(pending.id, null, new DOMException('麦克风请求已取消','AbortError')); pending = undefined; }
    button.hidden = true;
    if (notify) send({type:'nos-resource-microphone',stopped:true});
  }
  button.addEventListener('click', async event => {
    if (!event.isTrusted) return;
    if (stream) { stop(); return; }
    if (!pending) return;
    const request = pending; pending = undefined;
    const token = ++generation;
    button.disabled = true;
    let context, acquired;
    try {
      const Constructor = window.AudioContext || window.webkitAudioContext;
      context = new Constructor(); audio = context;
      const resumed = context.resume().then(()=>null,error=>error);
      acquired = await navigator.mediaDevices.getUserMedia({audio:{deviceId:request.deviceId ? {exact:request.deviceId} : undefined,echoCancellation:false,noiseSuppression:false,autoGainControl:false},video:false});
      const resumeError = await resumed; if (resumeError) throw resumeError;
      if (token !== generation) { acquired.getTracks().forEach(track=>track.stop()); void context.close(); reply(request.id,null,new DOMException('请求已取消','AbortError')); return; }
      stream = acquired;
      const analyser = context.createAnalyser(); analyser.fftSize = 2048;
      context.createMediaStreamSource(acquired).connect(analyser);
      const values = new Float32Array(analyser.fftSize);
      const track = acquired.getAudioTracks()[0];
      track.onended = stop;
      interval = setInterval(() => {
        if (context.state !== 'running' || track.muted) return;
        analyser.getFloatTimeDomainData(values);
        let power = 0; for (const value of values) power += value * value;
        send({type:'nos-resource-microphone',power:power / values.length});
      },100);
      const devices = (await navigator.mediaDevices.enumerateDevices()).filter(device=>device.kind==='audioinput').map(({deviceId,label,kind,groupId})=>({deviceId,label,kind,groupId}));
      reply(request.id,{devices,microphone:track.label || '当前麦克风'});
      button.textContent = '停止麦克风'; button.hidden = false;
    } catch (error) {
      acquired?.getTracks().forEach(track=>track.stop());
      if (context && context.state !== 'closed') void context.close();
      stream = undefined; audio = undefined; button.hidden = true;
      reply(request.id,null,error);
    } finally { button.disabled = false; }
  });
  async function png(data) {
    if (exporting) throw new Error('图片正在导出，请稍后');
    if (!Number.isInteger(data.width) || !Number.isInteger(data.height) || data.width<1 || data.height<1 || data.width*data.height>10000000 || typeof data.svg!=='string' || data.svg.length>2000000) throw new Error('图片尺寸或内容超出限制');
    exporting = true;
    let url;
    try {
      const document = new DOMParser().parseFromString(data.svg,'image/svg+xml');
      if (document.querySelector('parsererror') || document.documentElement.localName!=='svg') throw new Error('SVG 格式无效');
      const allowed = new Set(['svg','g','path','rect','circle','ellipse','line','polyline','polygon','text','tspan','defs','linearGradient','radialGradient','stop','clipPath','mask','pattern','title','desc']);
      for (const node of document.querySelectorAll('*')) {
        if (!allowed.has(node.localName)) throw new Error('SVG 含不支持的元素');
        for (const attr of Array.from(node.attributes)) {
          if (attr.name==='xmlns' && attr.value==='http://www.w3.org/2000/svg') continue;
          if (attr.name==='xmlns:xlink' && attr.value==='http://www.w3.org/1999/xlink') continue;
          if (/^on/i.test(attr.name) || /href/i.test(attr.name) || /(?:https?:|data:|javascript:|@import)/i.test(attr.value) || /url\(\s*['"]?(?!#)/i.test(attr.value)) throw new Error('SVG 不得包含外部内容');
        }
      }
      url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(document)],{type:'image/svg+xml'}));
      const image = new Image(); await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(new Error('图片渲染失败'));image.src=url;});
      const canvas = window.document.createElement('canvas'); canvas.width=data.width; canvas.height=data.height;
      canvas.getContext('2d').drawImage(image,0,0);
      const blob = await new Promise((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(new Error('PNG 导出失败')),'image/png'));
      return {bytes:await blob.arrayBuffer()};
    } finally { if(url)URL.revokeObjectURL(url); exporting=false; }
  }
  window.addEventListener('message', async event => {
    const data = event.data;
    if (event.source!==frame.contentWindow || event.origin!=='null' || data?.type!=='nos-resource-capability' || typeof data.id!=='string' || data.id.length>100) return;
    try {
      if (data.op==='mic-start' && capabilities.has('microphone')) {
        stop(false); pending={id:data.id,deviceId:typeof data.deviceId==='string'?data.deviceId.slice(0,256):''};
        button.textContent='允许本资源使用麦克风（仅本机音量分析）';button.hidden=false;
      } else if (data.op==='mic-stop' && capabilities.has('microphone')) { stop();reply(data.id,{}); }
      else if (data.op==='png' && capabilities.has('png-export')) reply(data.id,await png(data));
      else throw new Error('此资源未声明该能力');
    } catch (error) { reply(data.id,null,error); }
  });
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
  window.addEventListener('pagehide',stop);
  frame.addEventListener('load',stop);
})();
