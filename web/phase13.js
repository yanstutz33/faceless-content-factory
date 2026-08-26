const renderCoreJobDetail=openJob;
let jobDetailSequence=0;

openJob=async function(id){
  const sequence=++jobDetailSequence;
  await renderCoreJobDetail(id);
  const dialog=document.querySelector('#job-dialog');
  if(sequence!==jobDetailSequence||!dialog.open)return;
  try{
    const job=await api(`/api/jobs/${encodeURIComponent(id)}`);
    if(sequence!==jobDetailSequence||!dialog.open)return;
    const context={id,job,dialog,actions:dialog.querySelector('.detail-actions')};
    for(const extension of jobDetailExtensions){
      if(sequence!==jobDetailSequence||!dialog.open)return;
      try{await extension(context)}
      catch(error){
        console.error('Falha em extensão dos detalhes',error);
        toast('Um recurso complementar não pôde ser carregado. O restante continua disponível.','error');
      }
    }
  }catch(error){toast(error.message,'error')}
};

function syncNavigation(){
  const hash=location.hash||'#overview';
  document.querySelectorAll('.nav-item').forEach(item=>{
    const active=item.getAttribute('href')===hash;
    item.classList.toggle('active',active);
    if(active)item.setAttribute('aria-current','page');else item.removeAttribute('aria-current');
  });
}

function syncConnectionState(){
  document.body.classList.toggle('is-offline',!navigator.onLine);
  if(!navigator.onLine)toast('Sem conexão com o Studio. As alterações aguardam o serviço voltar.','error');
}

window.addEventListener('hashchange',syncNavigation);
window.addEventListener('online',syncConnectionState);
window.addEventListener('offline',syncConnectionState);
syncNavigation();
syncConnectionState();
