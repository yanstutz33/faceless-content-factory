const phaseApi=api;
let phaseSeries=[];
const phaseEsc=esc;
const activeCalendarStatuses=new Set(['planned','starting','producing','ready','approved']);

function renderSeries(series){
  document.querySelector('#series-grid').innerHTML=series.map(item=>`
    <article class="series-card" style="--series:${item.color}">
      <img class="series-cover" src="/api/template-covers/${encodeURIComponent(item.cover_asset)}" alt="" loading="lazy">
      <span class="series-dot"></span>
      <h3>${phaseEsc(item.name)}</h3>
      <p>${phaseEsc(item.description)}</p>
      <button data-series-batch="${phaseEsc(item.id)}">Criar coleção <span>→</span></button>
    </article>`).join('');
  document.querySelector('#batch-series').innerHTML=series.map(item=>
    `<option value="${phaseEsc(item.id)}">${phaseEsc(item.name)}</option>`
  ).join('');
}

function renderCalendar(calendar){
  const labels={planned:'planejado',starting:'iniciando',producing:'em produção',ready:'para revisar',approved:'aprovado'};
  const currentSeriesIds=new Set(phaseSeries.map(item=>item.id));
  const visible=calendar.filter(item=>activeCalendarStatuses.has(item.status)&&(!item.series_id||currentSeriesIds.has(item.series_id))).slice(0,8);
  const root=document.querySelector('#calendar-list');
  root.innerHTML=visible.length?visible.map(item=>{
    const date=new Date(item.scheduled_for);
    return `<article class="calendar-item">
      <div class="calendar-date"><div><small>${date.toLocaleDateString('pt-BR',{month:'short'}).replace('.','').toUpperCase()}</small>${String(date.getDate()).padStart(2,'0')}</div></div>
      <div><h3>${phaseEsc(item.topic)}</h3><p>${date.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})} · ${phaseEsc(labels[item.status]||item.status)}</p></div>
      ${item.job_id?'':`<button type="button" data-produce="${item.id}">Produzir</button>`}
    </article>`;
  }).join(''):'<div class="calendar-empty"><b>Agenda livre.</b><span>Planeje o próximo conteúdo quando quiser.</span></div>';
}

async function loadPhase2(){
  try{
    const [series,calendar]=await Promise.all([phaseApi('/api/series'),phaseApi('/api/calendar')]);
    phaseSeries=series;
    renderSeries(series);
    renderCalendar(calendar);
  }catch(error){toast(error.message)}
}

document.querySelector('#new-batch').onclick=()=>document.querySelector('#batch-dialog').showModal();
document.querySelector('#new-calendar-item').onclick=()=>{
  const field=document.querySelector('#calendar-form [name=scheduled_for]');
  if(!field.value){
    const date=new Date(Date.now()+86400000);
    date.setMinutes(date.getMinutes()-date.getTimezoneOffset());
    field.value=date.toISOString().slice(0,16);
  }
  document.querySelector('#calendar-dialog').showModal();
};
document.querySelector('#series-grid').addEventListener('click',event=>{
  const button=event.target.closest('[data-series-batch]');
  if(!button)return;
  document.querySelector('#batch-series').value=button.dataset.seriesBatch;
  document.querySelector('#batch-dialog').showModal();
});
document.querySelector('#batch-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const data=new FormData(event.currentTarget);
  const topics=String(data.get('topics')||'').split('\n').map(value=>value.trim()).filter(Boolean);
  try{
    const result=await phaseApi('/api/batches',{method:'POST',body:JSON.stringify({series_id:data.get('series_id'),topics})});
    document.querySelector('#batch-dialog').close();
    toast(`${result.count} produções adicionadas à fila.`);
    location.hash='production';
    load();
  }catch(error){toast(error.message)}
});
document.querySelector('#calendar-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const form=event.currentTarget;
  const data=new FormData(form);
  try{
    await phaseApi('/api/calendar',{method:'POST',body:JSON.stringify({topic:data.get('topic'),scheduled_for:data.get('scheduled_for'),profile:data.get('profile'),team_id:data.get('team_id'),duration:Number(data.get('duration'))})});
    document.querySelector('#calendar-dialog').close();
    form.reset();
    toast('Conteúdo adicionado à agenda.');
    loadPhase2();
  }catch(error){toast(error.message)}
});
document.querySelector('#calendar-list').addEventListener('click',async event=>{
  const button=event.target.closest('[data-produce]');
  if(!button)return;
  try{
    await phaseApi(`/api/calendar/${button.dataset.produce}/produce`,{method:'POST',body:'{}'});
    toast('Produção iniciada.');
    loadPhase2();
    load();
  }catch(error){toast(error.message)}
});
loadPhase2();
