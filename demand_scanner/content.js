(() => {
  if (window.__avitoDemandScannerInstalled) return;
  window.__avitoDemandScannerInstalled = true;

  const safePageInfo = () => ({
    href: location.origin + location.pathname,
    title: document.title,
    textHints: Array.from(document.querySelectorAll('button,[role="button"],input,[role="combobox"],select'))
      .slice(0, 100)
      .map(el => ({
        tag: el.tagName.toLowerCase(),
        role: el.getAttribute('role') || '',
        aria: (el.getAttribute('aria-label') || '').slice(0, 100),
        placeholder: (el.getAttribute('placeholder') || '').slice(0, 100),
        text: (el.innerText || el.value || '').trim().slice(0, 100)
      }))
      .filter(x => x.aria || x.placeholder || x.text)
  });

  const inject = () => {
    const script = document.createElement('script');
    script.src = chrome.runtime.getURL('page-hook.js');
    script.onload = () => script.remove();
    (document.head || document.documentElement).appendChild(script);
  };
  inject();

  window.addEventListener('message', event => {
    if (event.source !== window || !event.data || event.data.source !== 'avito-demand-scanner') return;
    chrome.runtime.sendMessage({type:'API_SHAPE', payload:event.data.payload}).catch(() => {});
  });

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message?.type === 'GET_PAGE_INFO') sendResponse(safePageInfo());
    if (message?.type === 'PING') sendResponse({ok:true, url:location.origin + location.pathname});
    return true;
  });
})();