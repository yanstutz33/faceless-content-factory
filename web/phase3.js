registerJobDetailExtension(async({id,job,dialog,actions})=>{
  const variants=job.metadata?.thumbnail_variants||[];
  if(!variants.length)return;
  const selected=job.metadata?.selected_thumbnail||job.thumbnail_variant||'a';
  const section=document.createElement('section');
  section.className='thumbnail-test';
  section.innerHTML=`<div><h4>TESTE A/B · CAPA DO VÍDEO</h4><small>Escolha a capa que acompanha o pacote final.</small></div><div class="thumbnail-choices">${variants.map(item=>`<button class="thumbnail-choice ${selected===item.id?'selected':''}" data-thumbnail-variant="${esc(item.id)}"><img src="/api/jobs/${encodeURIComponent(id)}/artifacts/${esc(item.file)}" alt="Variação ${esc(item.id.toUpperCase())}"><span>Variação ${esc(item.id.toUpperCase())}</span></button>`).join('')}</div>`;
  actions?.before(section);
  section.addEventListener('click',async event=>{
    const button=event.target.closest('[data-thumbnail-variant]');
    if(!button)return;
    button.disabled=true;
    try{
      await api(`/api/jobs/${encodeURIComponent(id)}/thumbnail`,{method:'POST',body:JSON.stringify({variant:button.dataset.thumbnailVariant})});
      section.querySelectorAll('.thumbnail-choice').forEach(choice=>choice.classList.toggle('selected',choice===button));
      const poster=dialog.querySelector('video');
      if(poster)poster.poster=`/api/jobs/${encodeURIComponent(id)}/artifacts/thumbnail.jpg?t=${Date.now()}`;
      toast(`Variação ${button.dataset.thumbnailVariant.toUpperCase()} selecionada.`);
    }catch(error){toast(error.message,'error')}finally{button.disabled=false}
  });
});
