chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== 'API_SHAPE' || !message.payload) return;
  chrome.storage.local.get('apiShapes').then(data => {
    const items = data.apiShapes || [];
    const item = message.payload;
    const key = item.url + '|' + JSON.stringify(item.responseShape);
    if (!items.some(x => x._key === key)) {
      items.push({...item, _key:key});
      return chrome.storage.local.set({apiShapes:items.slice(-100)});
    }
  }).catch(() => {});
});
