(() => {
  if (window.__avitoDemandScannerHooked) return;
  window.__avitoDemandScannerHooked = true;

  const relevant = url => /demand|search|analytics|stat|query|suggest|location|geo/i.test(url || '');
  const shapeOf = (value, depth = 0) => {
    if (depth > 4) return typeof value;
    if (Array.isArray(value)) return {type:'array', length:value.length, sample:value.length ? shapeOf(value[0], depth + 1) : null};
    if (value && typeof value === 'object') {
      const out = {};
      Object.keys(value).slice(0, 80).forEach(key => { out[key] = shapeOf(value[key], depth + 1); });
      return out;
    }
    if (value === null) return 'null';
    return typeof value;
  };
  const publish = (url, status, contentType, body) => {
    if (!relevant(url)) return;
    let shape = null;
    if (typeof body === 'string' && /json/i.test(contentType || '')) {
      try { shape = shapeOf(JSON.parse(body)); } catch (_) { shape = {parseError:true}; }
    }
    window.postMessage({source:'avito-demand-scanner', payload:{
      url: String(url).slice(0, 500),
      status: Number(status) || 0,
      contentType: String(contentType || '').slice(0, 100),
      responseShape: shape,
      capturedAt: new Date().toISOString()
    }}, '*');
  };

  const originalFetch = window.fetch;
  window.fetch = async function(...args) {
    const response = await originalFetch.apply(this, args);
    try {
      const url = typeof args[0] === 'string' ? args[0] : args[0]?.url;
      if (relevant(url)) {
        const clone = response.clone();
        clone.text().then(body => publish(url, response.status, response.headers.get('content-type'), body.slice(0, 500000))).catch(() => {});
      }
    } catch (_) {}
    return response;
  };

  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this.__avitoDemandUrl = url;
    return originalOpen.call(this, method, url, ...rest);
  };
  XMLHttpRequest.prototype.send = function(...args) {
    if (relevant(this.__avitoDemandUrl)) {
      this.addEventListener('load', () => {
        try { publish(this.__avitoDemandUrl, this.status, this.getResponseHeader('content-type'), typeof this.responseText === 'string' ? this.responseText.slice(0, 500000) : ''); } catch (_) {}
      }, {once:true});
    }
    return originalSend.apply(this, args);
  };
})();