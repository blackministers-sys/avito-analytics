const statusEl=document.getElementById('status');
const pageEl=document.getElementById('page');
const itemsEl=document.getElementById('items');
const render=async()=>{
  const data=await chrome.storage.local.get(['apiShapes','pageInfo']);
  const items=data.apiShapes||[];
  pageEl.textContent=data.pageInfo?('Страница: '+data.pageInfo.title+' · '+data.pageInfo.href):'';
  itemsEl.innerHTML='';
  items.slice().reverse().forEach(item=>{
    const div=document.createElement('div');div.className='item';
    const url=document.createElement('div');url.className='url';url.textContent=item.url+' · HTTP '+item.status;
    const shape=document.createElement('div');shape.className='shape';shape.textContent=JSON.stringify(item.responseShape||{noJsonShape:true},null,2);
    div.append(url,shape);itemsEl.append(div);
  });
  if(items.length)statusEl.textContent='Найдено подходящих сетевых ответов: '+items.length+'. Измени город или период на странице Avito, затем проверь, какие ответы появляются.';
};
document.getElementById('check').addEventListener('click',async()=>{
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
  if(!tab?.id){statusEl.textContent='Активная вкладка не найдена.';return;}
  try{
    const info=await chrome.tabs.sendMessage(tab.id,{type:'GET_PAGE_INFO'});
    await chrome.storage.local.set({pageInfo:info});
    statusEl.textContent='Страница доступна для диагностики.';
    await render();
  }catch(e){statusEl.textContent='Не удалось подключиться. Обнови вкладку Avito после установки расширения.';}
});
document.getElementById('clear').addEventListener('click',async()=>{
  await chrome.storage.local.set({apiShapes:[],pageInfo:null});statusEl.textContent='Локальная диагностика очищена.';await render();
});
chrome.runtime.onMessage.addListener(async message=>{
  if(message?.type!=='API_SHAPE')return;
  const data=await chrome.storage.local.get('apiShapes');const items=data.apiShapes||[];
  const key=message.payload.url+'|'+JSON.stringify(message.payload.responseShape);
  if(!items.some(x=>x._key===key)){items.push({...message.payload,_key:key});await chrome.storage.local.set({apiShapes:items.slice(-100)});await render();}
});
render();