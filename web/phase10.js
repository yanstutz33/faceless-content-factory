registerJobDetailExtension(async({job,actions})=>{
  const fingerprint=job.metadata?.creative_fingerprint;
  if(!fingerprint)return;
  const block=document.createElement('div');block.className='agent-output';
  block.innerHTML=`<h4>IDENTIDADE CRIATIVA · SEM REPETIÇÃO CEGA</h4><p><b>Cena:</b> ${esc(fingerprint.scene||'original')} · <b>Arranjo:</b> ${esc(fingerprint.music_arrangement||'lo-fi')} · <b>Seed:</b> ${esc(String(fingerprint.music_seed||''))}</p>`;
  actions?.before(block);
});
