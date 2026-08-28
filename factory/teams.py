from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SkillSpec:
    id: str
    name: str
    purpose: str
    shared: bool = False


@dataclass(frozen=True)
class TeamAgentSpec:
    id: str
    name: str
    role: str
    skills: tuple[str, ...]


@dataclass(frozen=True)
class TeamSpec:
    id: str
    name: str
    mission: str
    primary_goal: str
    destinations: tuple[str, ...]
    color: str
    recommended_profile: str
    entrypoint: str
    creation_enabled: bool
    agents: tuple[TeamAgentSpec, ...]


DEFAULT_TEAM_ID = "youtube_ambient"

SKILLS = (
    SkillSpec("rights_guard", "Guarda de direitos", "Bloqueia mídia sem origem ou licença verificável.", True),
    SkillSpec("quality_gate", "Controle de qualidade", "Avalia integridade, clareza e prontidão antes da aprovação.", True),
    SkillSpec("safe_publish", "Publicação segura", "Mantém todo envio em aprovação manual até haver conexão autorizada.", True),
    SkillSpec("audience_research", "Pesquisa de audiência", "Converte tema em intenção, promessa e palavras-chave."),
    SkillSpec("longform_retention", "Retenção de longa duração", "Planeja entrada, estabilidade e microvariações para watch time."),
    SkillSpec("ambient_direction", "Direção ambiente", "Coordena cena fixa, movimento localizado e trilha original."),
    SkillSpec("youtube_package", "Pacote YouTube", "Cria título, descrição, capítulos e thumbnail para vídeo longo."),
    SkillSpec("short_hook", "Gancho vertical", "Entrega a promessa visual nos primeiros segundos."),
    SkillSpec("vertical_pacing", "Ritmo vertical", "Adapta texto, enquadramento e duração para consumo rápido."),
    SkillSpec("experiment_design", "Experimentos rápidos", "Define hipótese e variação mensurável por publicação."),
    SkillSpec("product_truth", "Verdade do produto", "Exige correspondência entre produto, mídia e alegações."),
    SkillSpec("affiliate_disclosure", "Transparência de afiliado", "Inclui aviso de comissão e linguagem comercial responsável."),
    SkillSpec("conversion_package", "Pacote de conversão", "Produz gancho, benefício demonstrável, CTA e distribuição."),
    SkillSpec("zh_localization", "Localização para chinês", "Adapta título e descrição em chinês simplificado."),
    SkillSpec("cultural_review", "Revisão cultural", "Sinaliza traduções literais e referências inadequadas ao público local."),
    SkillSpec("bilibili_package", "Pacote Bilibili", "Organiza metadados, tags e instruções de upload para Bilibili."),
)

SHARED_SKILLS = ("rights_guard", "quality_gate", "safe_publish")

TEAMS = {
    "youtube_ambient": TeamSpec(
        "youtube_ambient", "YouTube Ambient", "Criar sessões longas originais de chill/lo-fi com alta permanência.",
        "watch_time", ("youtube",), "#67D4FF", "youtube_long", "production", True,
        (
            TeamAgentSpec("yt_strategist", "Arquiteto de Sessão", "Estratégia e retenção", ("audience_research", "longform_retention")),
            TeamAgentSpec("yt_director", "Diretor de Atmosfera", "Direção visual e sonora", ("ambient_direction",)),
            TeamAgentSpec("yt_packager", "Editor de Canal", "Descoberta e embalagem", ("youtube_package",)),
        ),
    ),
    "tiktok_experiments": TeamSpec(
        "tiktok_experiments", "Vertical Experiments", "Testar ideias curtas para TikTok, Shorts e Reels com aprendizado rápido.",
        "completion_and_shares", ("tiktok", "shorts", "reels"), "#75D8B8", "vertical_short", "production", True,
        (
            TeamAgentSpec("vertical_scout", "Radar de Gancho", "Pesquisa e abertura", ("audience_research", "short_hook")),
            TeamAgentSpec("vertical_editor", "Editor Vertical", "Ritmo e enquadramento", ("vertical_pacing",)),
            TeamAgentSpec("vertical_analyst", "Analista de Testes", "Hipóteses e aprendizado", ("experiment_design",)),
        ),
    ),
    "affiliate_commerce": TeamSpec(
        "affiliate_commerce", "Affiliate Commerce", "Transformar produtos verificados em pacotes de afiliado honestos e mensuráveis.",
        "qualified_conversion", ("shopee", "pinterest", "tiktok"), "#FFB86B", "vertical_short", "commerce", False,
        (
            TeamAgentSpec("product_analyst", "Analista de Produto", "Evidência e proposta", ("product_truth",)),
            TeamAgentSpec("commerce_writer", "Roteirista Comercial", "Gancho, demonstração e CTA", ("conversion_package",)),
            TeamAgentSpec("commerce_guard", "Guardião Comercial", "Divulgação e conformidade", ("affiliate_disclosure",)),
        ),
    ),
    "bilibili_lab": TeamSpec(
        "bilibili_lab", "Bilibili Lab", "Localizar os melhores conteúdos para Bilibili com revisão cultural.",
        "localized_discovery", ("bilibili",), "#D99BFF", "youtube_long", "production", True,
        (
            TeamAgentSpec("bili_editor", "Editor Bilibili", "Seleção e posicionamento", ("audience_research", "bilibili_package")),
            TeamAgentSpec("bili_localizer", "Localizador ZH", "Adaptação de idioma", ("zh_localization",)),
            TeamAgentSpec("bili_reviewer", "Revisor Cultural", "Contexto e adequação", ("cultural_review",)),
        ),
    ),
}


def get_team(team_id: str | None) -> TeamSpec:
    try:
        return TEAMS[team_id or DEFAULT_TEAM_ID]
    except KeyError as exc:
        raise ValueError("Equipe de agentes inválida") from exc


def skill_catalog() -> list[dict[str, Any]]:
    return [asdict(skill) for skill in SKILLS]


def team_catalog() -> list[dict[str, Any]]:
    result = []
    for team in TEAMS.values():
        item = asdict(team)
        item["shared_skills"] = list(SHARED_SKILLS)
        item["skills"] = list(dict.fromkeys(
            skill for agent in team.agents for skill in agent.skills
        ))
        result.append(item)
    return result


def apply_team_playbook(plan: dict[str, Any], team_id: str | None) -> dict[str, Any]:
    team = get_team(team_id)
    active_skills = [*SHARED_SKILLS, *(skill for agent in team.agents for skill in agent.skills)]
    plan["team"] = {
        "id": team.id, "name": team.name, "mission": team.mission,
        "primary_goal": team.primary_goal, "destinations": list(team.destinations),
        "recommended_profile": team.recommended_profile,
        "agents": [asdict(agent) for agent in team.agents],
        "skills_executed": list(dict.fromkeys(active_skills)),
        "entrypoint": team.entrypoint,
    }
    plan["strategy"]["primary_goal"] = team.primary_goal
    plan["compliance"]["checks"] = list(dict.fromkeys([
        *plan["compliance"]["checks"], "equipe e skills registradas no pacote",
    ]))

    if team.id == "tiktok_experiments":
        plan["strategy"].update({
            "hook": f"Pare por alguns segundos: {plan['strategy']['hook']}",
            "cadence": "gancho imediato, evolução perceptível e encerramento em loop",
            "experiment": "Teste uma única variável: texto inicial, enquadramento ou CTA.",
        })
        plan["script"]["on_screen"] = [plan["strategy"]["hook"], "Salve para voltar depois"]
        plan["review"]["next_action"] = "Validar leitura em tela pequena e os três primeiros segundos."
    elif team.id == "bilibili_lab":
        title = plan["seo"]["title"]
        plan["seo"]["localized"] = {
            "locale": "zh-CN", "title": f"沉浸式氛围｜{title}"[:80],
            "description": "用于学习、专注和放松的原创沉浸式氛围。发布前请人工复核中文。",
            "tags": ["氛围", "学习", "放松", "原创音乐"],
            "human_review_required": True,
        }
        plan["review"]["warnings"].append("Pacote em chinês exige revisão humana antes da publicação.")
    elif team.id == "affiliate_commerce":
        plan["strategy"].update({
            "cadence": "problema verificável, demonstração do produto e CTA transparente",
            "conversion_rule": "Nenhuma alegação sem evidência visual ou especificação confirmada.",
        })
        plan["compliance"]["checks"].extend(["produto corresponde à mídia", "aviso de link afiliado incluído"])
        plan["review"]["next_action"] = "Continuar no Centro de Afiliados e validar produto, preço e direitos da mídia."
    return plan
