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

function syncNavigation(scroll=false){
  const requested=(location.hash||'#overview').slice(1);
  const sections=[...document.querySelectorAll('main > .section')];
  const activeSection=sections.find(section=>section.id===requested)||document.querySelector('#overview');
  const hash=`#${activeSection.id}`;
  document.body.dataset.route=activeSection.id;
  sections.forEach(section=>{
    const active=section===activeSection;
    section.hidden=!active;
    section.toggleAttribute('aria-hidden',!active);
  });
  document.querySelectorAll('.nav-item').forEach(item=>{
    const active=item.getAttribute('href')===hash;
    item.classList.toggle('active',active);
    if(active)item.setAttribute('aria-current','page');else item.removeAttribute('aria-current');
  });
  if(scroll){
    window.scrollTo({top:0,behavior:'auto'});
  }
}

function syncConnectionState(){
  document.body.classList.toggle('is-offline',!navigator.onLine);
  if(!navigator.onLine)toast('Sem conexão com o Studio. As alterações aguardam o serviço voltar.','error');
}

window.addEventListener('hashchange',()=>syncNavigation(true));
window.addEventListener('load',()=>{
  syncNavigation(true);
});
window.addEventListener('online',syncConnectionState);
window.addEventListener('offline',syncConnectionState);
syncNavigation();
syncConnectionState();
