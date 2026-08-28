# Faceless Content Factory — Studio MVP 2.0

Uma fábrica local e automatizada para transformar um tema em um pacote de vídeo de ambientação: roteiro, metadados, paisagem sonora, imagem, vídeo MP4, thumbnail, legenda e checklist de publicação. O MVP não envia nada para plataformas; a fila termina em aprovação para upload manual.

## O que já funciona

- Tema digitado, sugerido pelos agentes ou recebido pela linha de comando
- Oito agentes locais: pesquisa, estratégia, roteiro, direção, SEO, conformidade, crítica e reaproveitamento
- Roteiro, título, descrição, tags, capítulos, direção visual/sonora e score de qualidade
- Oito cenas-mestre lo-fi originais incluídas, com a linha opcional Anime Nights totalmente autoral
- Seleção automática da cena conforme o tema quando nenhum asset próprio é informado
- Loop visual ambiente de 12 segundos com câmera fixa e efeitos atmosféricos localizados
- Fumaça sobre a xícara, chuva ou estrelas pulsantes conforme o perfil, codificadas no MP4 em vez de GIF pesado
- Música chill/lo-fi original gerada localmente com acordes, beat, BPM e variação determinística por tema
- Chuva apenas como camada discreta nos temas correspondentes; cozy, cosmic e focus não recebem chuva
- Ingestão opcional de JPG/PNG/WebP próprio com enquadramento automático
- Perfis YouTube longo (16:9), vertical (9:16) e prévia rápida
- Renderização H.264/AAC com FFmpeg
- Legenda SRT opcional e thumbnail JPG
- Fila assíncrona persistente em SQLite: a interface não fica bloqueada durante a renderização
- Progresso, prioridade, histórico, revisão, aprovação/rejeição, repetição e métricas
- Retomada automática de produções interrompidas ao reiniciar o estúdio
- Streaming de vídeo por partes, sem carregar arquivos longos inteiros na memória
- Certificação técnica de duração, faixas de vídeo/áudio e decodificação de amostra
- Manifesto SHA-256 para comprovar a integridade de cada pacote
- Diagnóstico contínuo de ferramentas, fila e espaço em disco
- Cinco templates de séries, geração em lote e calendário editorial
- Início automático dos itens vencidos do calendário, com fila resiliente e publicação ainda manual
- Biblioteca de assets com licença, confirmação de direitos e composição multicena
- Duas thumbnails editoriais por vídeo, comparação A/B e seleção persistente da capa final
- Direcionamento editorial alimentado pelas métricas mais recentes de cada plataforma
- CTR por capa, retenção média, impressões, cliques, conversões e receita por snapshot
- Recomendação da capa vencedora por série sem troca automática arriscada
- Agentes enriquecíveis pela OpenAI Responses API, sempre com fallback local reproduzível
- Pacote `youtube-upload.json` privado e revisável, sem executar upload
- Pacote Bilibili bilíngue com capa neutra, metadados e legendas em chinês simplificado e inglês
- Centro de publicação com auditoria unificada de aprovação, qualidade técnica e direitos de mídia
- Preparação combinada de YouTube privado e recortes para Shorts, Reels e TikTok, sempre sem upload
- Diagnóstico pré-login para YouTube, TikTok, Reels e Shopee sem expor chaves no navegador
- Cofre OAuth criptografado, estado anti-CSRF, PKCE, desconexão local e callbacks preparados
- Fila de pré-envio persistente, log de auditoria sem segredos e retentativa exponencial limitada
- Backup diário e manual do SQLite com verificação de integridade e retenção configurável
- Pacote comercial Shopee com produto exato, divulgação de comissão, fontes e direitos obrigatórios
- Central Comercial separada com catálogo Shopee, campanhas, cliques, conversões, comissão, custo, lucro e ROI
- Geração do pacote comercial vinculada somente a produtos validados e produções aprovadas
- API com erros estruturados, código de solicitação e proteção contra vazamento de exceções internas
- Frontend modular com um único registro de extensões, evitando dependência frágil da ordem dos scripts
- Manifesto final de lançamento e fila visual de pacotes liberados, completos ou bloqueados
- Validador comercial que bloqueia produto divergente, publicidade oculta e mídia sem direitos
- Piloto automático semanal com séries, cadência, horário e duração configuráveis
- Reposição inteligente do calendário sem repetir temas já produzidos ou planejados
- Pausa automática por fila de revisão, trabalhos ativos ou pouco espaço em disco
- Painel responsivo para desktop e celular, sem Node e sem build
- Pacote isolado por vídeo em `data/jobs/<id>/`

Narração é opcional. `--narration` usa voz neural em português e tenta a voz local do Windows como fallback quando ela estiver realmente instalada. Neste computador nenhuma voz SAPI está disponível; por isso o diagnóstico informa essa ausência e o padrão seguro conclui o vídeo com música lo-fi.

## Imagem e música automáticas

Produções antigas não são modificadas retroativamente. Os primeiros testes sem asset usavam apenas um fundo procedural escuro e ruídos ambientais; por isso pareciam não ter imagem e soavam semelhantes. Todo pacote novo agora recebe uma cena ilustrada real do starter pack e uma trilha lo-fi original. O perfil `rain` adiciona chuva baixa atrás da música, enquanto `cozy`, `cosmic` e `focus` usam somente variações musicais e textura leve.

A série opcional `Anime Nights original` usa uma personagem adulta criada exclusivamente para o projeto, sem copiar franquias, personagens ou artistas. Ela só é escolhida quando o tema menciona explicitamente anime ou personagem; as demais séries continuam sem personagens.

A câmera permanece completamente fixa. O renderizador cria um ciclo visual suave de 12 segundos apenas em uma camada atmosférica localizada: fumaça sobre a xícara nos perfis cozy/focus, chuva no perfil rain e pontos de luz no cosmic. É o efeito de um GIF ambiente, mas entregue diretamente no vídeo MP4/H.264 para preservar qualidade. Perfil, atmosfera e efeitos usados ficam registrados no campo `motion` de `metadata.json`.

O loop musical é sintetizado pelo próprio projeto e não copia gravações ou músicas externas. Tema e perfil determinam seed, progressão, BPM e melodia. Os detalhes ficam em `metadata.json` no campo `music`.

## Início rápido (Windows / PowerShell)

Requisitos: Python 3.11+ e FFmpeg. Esta cópia local contém uma instalação portátil em `.tools/ffmpeg/bin` (a pasta não vai para o GitHub). FFprobe é usado quando estiver disponível; sem ele, a fábrica valida metadados e decodifica uma amostra diretamente com FFmpeg. O setup instala voz neural e o cofre criptografado no ambiente isolado.

Em um checkout novo, o caminho mais simples é:

```powershell
.\scripts\setup.ps1
.\scripts\start.ps1
```

O setup cria um ambiente Python isolado, instala a voz opcional, procura FFmpeg e prepara `.env`. Se a execução de scripts estiver bloqueada no Windows, use os comandos manuais abaixo.

```powershell
Copy-Item .env.example .env
python app.py serve
```

Abra `http://127.0.0.1:8787`, clique em **Nova produção** e escolha o formato. Para usar a linha de comando:

```powershell
python app.py generate --topic "Biblioteca chuvosa à noite" --duration 3600 --profile youtube_long
python app.py generate --topic "Cabana na neve" --duration 45 --profile vertical_short --narration
python app.py generate --topic "Café ao amanhecer" --duration 12 --profile preview --asset "C:\Assets\cafe.jpg" --confirm-asset-rights
python app.py doctor
python app.py integrations
python app.py backup
python app.py commerce-overview
python app.py commerce-pinterest-package ID_DA_CAMPANHA --board-name "Achados úteis"
python app.py bilibili-package ID_DA_PRODUCAO
```

O tempo e o espaço de renderização crescem com a duração. Faça uma prévia antes de iniciar vídeos de várias horas.

## Como os agentes trabalham

O Studio 2.0 organiza os agentes em equipes por objetivo e adiciona um diretor criativo com memória, sem criar sistemas duplicados:

- **YouTube Ambient:** pesquisa, retenção de longa duração, direção de atmosfera e pacote de canal.
- **Vertical Experiments:** gancho, ritmo para tela vertical e hipótese de teste para TikTok, Shorts e Reels.
- **Affiliate Commerce:** verdade do produto, transparência de afiliado e pacote de conversão; opera exclusivamente pelo Centro de Afiliados.
- **Bilibili Lab:** seleção editorial, localização em chinês simplificado e revisão cultural obrigatória.

Todas compartilham as skills de direitos, controle de qualidade e publicação segura. Cada produção salva `team_id`, agentes participantes e `skills_executed` em `agents.json` e `metadata.json`, deixando a decisão auditável. A API `GET /api/agent-teams` expõe o catálogo usado pela interface.

Cada produção salva `agents.json` com entregas auditáveis:

1. **Radar** identifica público, intenção e palavras-chave.
2. **Norte** define promessa, objetivo de retenção e cadência.
3. **Roteirista** prepara introdução, texto falado e capítulos.
4. **Direção** define paleta, movimento, som e briefing de asset.
5. **Descoberta** cria título, descrição e tags.
6. **Guardião** verifica direitos, riscos e modo de publicação.
7. **Crítica** gera score, alertas e próxima ação.

Hoje eles funcionam localmente com regras reproduzíveis. As interfaces estão separadas para permitir substituir um agente por LLM ou outro provedor sem reescrever fila e renderização.

## Séries, lotes e calendário

- **Lugares sob chuva**, **Mundos acolhedores**, **Foco cósmico** e **Momentos verticais** vêm prontos como pontos de partida.
- **Gerar lote** aceita até 20 temas e coloca tudo em uma fila serial para preservar a responsividade do computador.
- O calendário guarda tema, formato, duração e data. Na hora marcada, o item entra automaticamente na fila; também pode ser iniciado antes sem redigitação.
- O agendador verifica os itens a cada 15 segundos por padrão (`CALENDAR_POLL_SECONDS`) e sobrevive a falhas temporárias sem liberar publicação automática.
- O cartão **Piloto automático** permite escolher séries, ritmo semanal, horário e duração. Ativado, ele mantém sete dias de conteúdo planejados e repõe os próximos itens conforme os anteriores avançam.
- **Só planejar esta semana** cria o calendário sem deixar a reposição contínua ligada.
- Os templates ficam em `factory/templates.py` e podem ser adaptados sem alterar o pipeline.

### Limites do piloto automático

Por padrão, o piloto pausa somente os itens automáticos quando existem 12 pacotes aguardando revisão, dois trabalhos ativos ou menos de 3 GB livres. Conteúdos manuais continuam disponíveis. Os limites podem ser ajustados com `AUTOPILOT_MAX_REVIEW`, `AUTOPILOT_MAX_ACTIVE` e `AUTOPILOT_MIN_FREE_GB` no `.env`.

## Operação de baixo esforço

1. Escolha uma oportunidade sugerida ou informe tema, perfil e duração.
2. Continue usando o painel enquanto a fila renderiza em segundo plano.
3. Abra a produção, assista à prévia, compare as capas A/B e confira direção, score e metadados.
4. Aprove ou peça ajustes; falhas e revisões podem ser executadas novamente.
5. Faça o upload manual pelo YouTube Studio enquanto a API não estiver configurada.

Uma produção aprovada também pode gerar, pelo painel, uma versão vertical de 30 segundos. A fábrica preserva o quadro horizontal no centro, usa um fundo desfocado para completar 9:16 e cria `vertical-package.json` com textos separados para Shorts, Reels e TikTok. Nenhum desses pacotes é enviado automaticamente.

```powershell
python app.py vertical-package ID_DA_PRODUCAO --duration 30
```
6. Registre resultados para formar histórico de aprendizado:

```powershell
python app.py metrics ID_DO_TRABALHO --views 1200 --likes 84 --watch-minutes 530
```

## Estrutura

```text
app.py                 comandos e inicialização
factory/config.py      ambiente e modo seguro
factory/agents.py      equipe digital, perfis e sugestões
factory/pipeline.py    planejamento, assets e renderização
factory/store.py       fila, eventos e métricas SQLite
factory/web.py         API e servidor local
factory/commercial_center.py  catálogo, campanhas e resultados de afiliados
web/                   painel operacional
tests/                 agentes, banco, API e renderização real
data/jobs/             pacotes gerados (ignorado pelo Git)
```

## Assets próprios

O fluxo gera placeholders originais por padrão. Em **Biblioteca de assets**, registre nome, arquivo, licença, origem e observações e confirme os direitos comerciais. Em **Opções avançadas**, selecione até 12 imagens aprovadas; a fábrica divide o vídeo entre elas, aplica movimento suave e salva `asset-manifest.json` no pacote.

Um caminho avulso ainda pode ser informado para testes rápidos, mas exige confirmação explícita de direitos na interface ou a opção `--confirm-asset-rights` na linha de comando. A biblioteca é o fluxo recomendado porque mantém a rastreabilidade. Não reutilize vídeos de outros canais sem permissão.

## Testes

```powershell
python -m unittest discover -s tests -v
```

A suíte cobre agentes, validação, migração/estado da fila, trava de render entre processos, retomada após reinício, calendário com equipe especializada, insights por snapshot, catálogo de licenças, domínios oficiais, segurança da API, cancelamentos de formulários, streaming por faixa, fallback de voz, thumbnails A/B, renderização simples, checksums e composição multicena real com FFmpeg. A interface também é validada em desktop e viewport móvel.

Cada pacote novo inclui `render-report.json`, com o resultado técnico da mídia, e `artifact-manifest.json`, com tamanho e SHA-256 dos arquivos principais. Esses relatórios não publicam nada; servem para detectar pacotes incompletos antes da sua aprovação.

## Estado do roadmap

0. **Operação noturna:** turno configurável, execução antecipada de até cinco itens do calendário, uma rodada por noite, recuperação após reinício e pausa automática por fila, espaço ou trabalhos ativos.
0. **Escala criativa:** o diretor avalia 48 receitas por produção e combina cenas originais, oito tratamentos, cinco composições, 16 movimentos localizados, oito arranjos musicais, quatro progressões e cinco texturas. Cada pacote registra um DNA criativo reproduzível.
0. **Detector de repetição:** compara cena, imagem, composição, movimento, música, progressão, textura, BPM e proximidade temática com todo o histórico; a novidade pesa 80% da decisão.
0. **Aprendizado automático seguro:** retenção, CTR e engajamento alimentam preferências com peso de 20%, preservando exploração e evitando que um vencedor transforme toda a fábrica em cópias.
0. **Quality gate automático:** cada render é amostrado e bloqueado antes da aprovação se houver tela preta, ausência de movimento, câmera não fixa, áudio inaudível/clipping, duração ou decodificação inválida.
0. **Reaproveitamento vertical:** produções aprovadas agora geram um recorte 9:16 validado e pacotes manuais para Shorts, Reels e TikTok, sem upload automático.
0. **Centro de publicação segura:** reúne vídeos aprovados, bloqueia mídia sem direitos ou auditoria e prepara os pacotes de YouTube/vertical com um clique, sem acessar contas.
0. **Prontidão de integrações:** a área Conexões diagnostica YouTube, TikTok, Reels e Shopee sem transferir credenciais ao frontend e mostra o próximo passo manual de cada plataforma.
0. **Hardening do Studio:** respostas da API possuem código rastreável, erros internos não são expostos e as extensões do modal passam por um único carregador tolerante a falhas.

1. **Conector opcional de LLM:** implementado com Responses API, Structured Outputs, `store=false` e fallback local. Só ativa com `OPENAI_API_KEY`.
2. **Microvariações sonoras:** implementadas por seed, BPM, progressão, melodia e perfil.
3. **CTR e capas:** implementados no banco, API e painel; a fábrica recomenda vencedoras por série sem fazer trocas cegas.
4. **YouTube:** pacote privado oficial preparado após aprovação. O upload real depende do arquivo OAuth da conta e continuará exigindo confirmação humana.
5. **Retenção:** captura e ranking implementados. A coleta automática depende da autorização da conta/plataforma.
6. **Voz offline:** fallback implementado e diagnosticado, mas este Windows não possui uma voz SAPI instalada. A ambientação segura continua funcionando.
7. **Shopee + Pinterest:** trilha comercial aprovada para transformar produtos oficiais em vídeos próprios e publicar Video Pins rastreáveis; Pinterest nunca será fonte automática de mídia de terceiros.
8. **Bilibili:** pacote localizado entregue no Studio 1.8 com capa neutra, títulos, descrições e legendas em chinês simplificado e inglês; upload manual pelo Creator Studio.
9. **Painel comercial:** campanhas, produtos, links, cliques, conversões, comissão e custo de produção ficarão separados das métricas editoriais.
10. **Central Comercial Shopee:** entregue no Studio 1.5 com catálogo validado, campanhas persistentes, pacote manual e cálculo de resultado.
11. **Pinterest Video Pin:** entregue no Studio 1.6 como pacote local com vídeo, capa, texto alternativo, link, board-alvo e payload da API; login e upload continuam bloqueados.
12. **Renderização protegida:** entregue no Studio 1.7 com reserva atômica de cada produção, arquivo temporário isolado, promoção somente depois do quality gate e checksum obrigatório antes de aprovar ou reutilizar.
13. **Bilibili localizada:** entregue no Studio 1.8 com classificação editorial conservadora, metadados bilíngues, capa sem texto em português e SRTs separados; a revisão humana da primeira localização continua obrigatória.
14. **Equipes e skills especializadas:** entregue no Studio 1.9 com playbooks reais para YouTube, verticais, afiliados e Bilibili, seleção por produção, persistência no calendário e rastreio das skills executadas.
15. **DNA criativo e aprendizagem:** entregue no Studio 2.0 com 25.600 combinações-base por cena, detector de repetição, biblioteca sonora ampliada, movimento localizado e painel de originalidade.
16. **Cortes inteligentes:** arquitetura preparada para uma fase posterior; trabalhará somente sobre vídeos aprovados, preservará o original e usará capítulos, batidas e retenção para criar versões verticais.

`ALLOW_PLATFORM_PUBLISH=false` permanece o padrão. Credenciais, OAuth e acesso oficial às contas são os únicos bloqueios externos restantes; nenhum conteúdo é tornado público sem confirmação. A seção **Publicação** do painel mostra exatamente o que está liberado e o que ainda precisa de revisão.

As telas, callbacks e validações anteriores ao login já estão preparados. Use [docs/platform-setup.md](docs/platform-setup.md) para registrar as URLs de retorno e concluir cada login quando quiser. Até lá, o botão **Pré-validar** apenas prepara a entrega local e confirma bloqueios; ele não chama a plataforma.

## Frente futura de afiliados

O planejamento consolidado está em `docs/roadmap.md`, e a especificação comercial em `docs/commerce-video-roadmap.md`. Pinterest é destino dos nossos próprios Video Pins e fonte de pesquisa de tendências, nunca biblioteca automática de vídeos de terceiros. O módulo comercial só aceita mídia própria, licenciada ou fornecida oficialmente para afiliados.
