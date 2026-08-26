const verticalOpenJob=openJob;
openJob=async function(id){
  await verticalOpenJob(id);
  const job=await api(`/api/jobs/${encodeURIComponent(id)}`);
  if(job.status!=='approved')return;
  const actions=document.querySelector('#job-dialog .detail-actions');
  const button=document.createElement('button');
  button.className='primary';
  button.textContent='Criar versão vertical';
  button.onclick=async()=>{
    button.disabled=true;button.textContent='Criando recorte…';
    try{
      await api(`/api/jobs/${encodeURIComponent(id)}/vertical-package`,{method:'POST',body:JSON.stringify({duration:30})});
      toast('Versão vertical validada. Nenhum upload foi feito.');
      document.querySelector('#job-dialog').close();await openJob(id);
    }catch(error){toast(error.message)}finally{button.disabled=false;button.textContent='Criar versão vertical'}
  };
  actions?.append(button);
  if(job.events?.some(event=>event.stage==='repurpose')){
    const link=document.createElement('a');link.className='secondary';link.target='_blank';
    link.href=`/api/jobs/${encodeURIComponent(id)}/artifacts/vertical-short.mp4`;link.textContent='Ver vertical';
    actions?.append(link);
  }
};

