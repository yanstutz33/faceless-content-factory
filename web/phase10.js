registerJobDetailExtension(async({job,actions})=>{
  const fingerprint=job.metadata?.creative_fingerprint;
  if(!fingerprint)return;
  const block=document.createElement('div');block.className='agent-output';
  const novelty=fingerprint.novelty||{};const learning=fingerprint.learning||{};
  block.innerHTML=`<h4>DNA CRIATIVO · ${esc(String(novelty.score??'—'))}/100 DE ORIGINALIDADE</h4><p><b>Cena:</b> ${esc(fingerprint.scene||'original')} · <b>Tratamento:</b> ${esc(fingerprint.treatment_label||fingerprint.treatment||'original')} · <b>Composição:</b> ${esc(fingerprint.composition_label||fingerprint.composition||'central')}</p><p><b>Movimento:</b> ${esc(fingerprint.motion_effect||'atmosférico')} · <b>Arranjo:</b> ${esc(fingerprint.music_arrangement||'lo-fi')} · <b>BPM:</b> ${esc(String(fingerprint.bpm||''))} · <b>Textura:</b> ${esc(fingerprint.texture||'suave')}</p><p>${esc(learning.reason||'Exploração criativa ativa.')}${novelty.closest_topic?` Mais próximo de “${esc(novelty.closest_topic)}”, sem cópia integral.`:''}</p>`;
  actions?.before(block);
});
