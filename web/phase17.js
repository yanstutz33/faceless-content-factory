(() => {
  const e = value => esc(String(value ?? ''));
  async function loadCreativeLab() {
    try {
      const data = await api('/api/creative-system');
      const catalog = data.catalog;
      const learning = data.learning;
      document.querySelector('#creative-lab').innerHTML = `<article class="creative-lab-main"><div><span class="tag">MOTOR ${e(data.engine)}</span><h3>Escala criativa com memória</h3><p>Antes de renderizar, o Studio compara 48 candidatos com o histórico e escolhe o melhor equilíbrio entre novidade e evidência.</p></div><div class="novelty-orb"><b>${e(data.average_novelty ?? '—')}</b><small>originalidade média</small></div></article><div class="creative-kpis"><article><b>${Number(catalog.candidate_space).toLocaleString('pt-BR')}</b><span>combinações-base</span></article><article><b>${e(catalog.music_arrangements)}</b><span>arranjos musicais</span></article><article><b>${e(catalog.motions)}</b><span>movimentos localizados</span></article><article><b>${e(learning.evidence_count)}</b><span>resultados aprendidos</span></article></div><article class="learning-strip ${learning.mode}"><span>↗</span><div><b>${learning.mode==='measured'?'Aprendizado automático ativo':'Exploração inteligente ativa'}</b><p>${e(learning.reason)}</p></div><small>Cortes inteligentes · disponíveis nos vídeos aprovados</small></article>`;
    } catch (error) {
      document.querySelector('#creative-lab').innerHTML = `<div class="empty">${e(error.message)}</div>`;
    }
  }
  loadCreativeLab();
})();
