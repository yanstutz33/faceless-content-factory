registerJobDetailExtension(async({id,job,actions})=>{
  if(job.status!=='approved')return;
  const button=document.createElement('button');
  button.className='primary';button.textContent='Criar versão vertical';
  button.onclick=async()=>{
    button.disabled=true;button.textContent='Criando recorte…';
    try{
      await api(`/api/jobs/${encodeURIComponent(id)}/vertical-package`,{method:'POST',body:JSON.stringify({duration:30}),timeoutMs:120000});
      toast('Versão vertical validada. Nenhum upload foi feito.');document.querySelector('#job-dialog').close();await openJob(id);
    }catch(error){toast(error.message,'error')}finally{button.disabled=false;button.textContent='Criar versão vertical'}
  };
  actions?.append(button);
  if(job.events?.some(event=>event.stage==='repurpose')){
    const link=document.createElement('a');link.className='secondary';link.target='_blank';link.rel='noopener';
    link.href=`/api/jobs/${encodeURIComponent(id)}/artifacts/vertical-short.mp4`;link.textContent='Ver vertical';actions?.append(link);
  }
});
