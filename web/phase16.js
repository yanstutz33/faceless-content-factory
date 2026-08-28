(() => {
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const skillIndex = new Map();

  function renderTeam(team) {
    const agentNames = team.agents.map(agent => agent.name).join(' · ');
    const status = team.creation_enabled ? 'Disponível na produção' : 'Opera no Centro de Afiliados';
    return `<article class="team-card" style="--team:${escapeHtml(team.color)}"><div class="team-card-top"><span class="team-dot"></span><span>${escapeHtml(team.destinations.join(' · '))}</span></div><h3>${escapeHtml(team.name)}</h3><p>${escapeHtml(team.mission)}</p><div class="team-goal"><small>OBJETIVO</small><b>${escapeHtml(team.primary_goal.replaceAll('_',' '))}</b></div><p class="team-agents">${escapeHtml(agentNames)}</p><span class="team-status">${escapeHtml(status)}</span></article>`;
  }

  async function loadTeams() {
    const response = await fetch('/api/agent-teams');
    if (!response.ok) throw new Error('Não foi possível carregar as equipes');
    const data = await response.json();
    data.skills.forEach(skill => skillIndex.set(skill.id, skill));
    document.querySelector('#team-grid').innerHTML = data.teams.map(renderTeam).join('');
    document.querySelector('#skill-library').innerHTML = data.skills.map(skill => `<span class="skill-chip ${skill.shared ? 'shared' : ''}" title="${escapeHtml(skill.purpose)}">${skill.shared ? '✓ ' : ''}${escapeHtml(skill.name)}</span>`).join('');
    const select = document.querySelector('#production-team');
    const available = data.teams.filter(team => team.creation_enabled);
    select.innerHTML = available.map(team => `<option value="${escapeHtml(team.id)}">${escapeHtml(team.name)}</option>`).join('');
    select.value = data.default_team;
    const help = document.querySelector('#production-team-help');
    const updateHelp = () => {
      const team = available.find(item => item.id === select.value);
      if (team) {
        help.textContent = `${team.mission} Destino: ${team.destinations.join(', ')}.`;
        const profile = document.querySelector(`#profiles input[value="${team.recommended_profile}"]`);
        if (profile) profile.checked = true;
      }
    };
    select.addEventListener('change', updateHelp);
    updateHelp();
  }

  registerJobDetailExtension(({job, actions}) => {
    const team = job.metadata?.agents?.team;
    if (!team) return;
    const skills = (team.skills_executed || []).map(id => skillIndex.get(id)?.name || id);
    const section = document.createElement('section');
    section.className = 'agent-output team-execution';
    section.innerHTML = `<h4>EQUIPE · ${escapeHtml(team.name)}</h4><p>${escapeHtml(team.mission)}</p><p><b>Agentes:</b> ${team.agents.map(agent => escapeHtml(agent.name)).join(' · ')}</p><div class="skill-chips">${skills.map(name => `<span class="skill-chip">${escapeHtml(name)}</span>`).join('')}</div>`;
    actions?.before(section);
  });

  loadTeams().catch(error => {
    document.querySelector('#team-grid').innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  });
})();
