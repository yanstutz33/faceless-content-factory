# Faceless Content Factory — Studio MVP 2.0

Uma fábrica local e automatizada para transformar um tema em um pacote de vídeo de ambientação: roteiro, metadados, paisagem sonora, imagem, vídeo MP4, thumbnail, legenda e checklist de publicação. O MVP não envia nada para plataformas; a fila termina em aprovação para upload manual.

## O que já funciona

- Tema digitado, sugerido pelos agentes ou recebido pela linha de comando
- Oito agentes locais: pesquisa, estratégia, roteiro, direção, SEO, conformidade, crítica e reaproveitamento
- Roteiro, título, descrição, tags, capítulos, direção visual/sonora e score de qualidade
- Doze cenas-mestre lo-fi originais incluídas, com a linha opcional Anime Nights totalmente autoral
- Seleção automática da cena conforme o tema quando nenhum asset próprio é informado
- Loop visual ambiente de 12 segundos com câmera fixa e efeitos atmosféricos localizados
- Fumaça sobre a xícara, chuva ou estrelas pulsantes conforme o perfil, codificadas no MP4 em vez de GIF pesado
- Música chill/lo-fi original gerada localmente com 12 instrumentações e sete famílias rítmicas, incluindo faixas sem bateria
- Chuva apenas como camada discreta nos temas correspondentes; cozy, cosmic e focus não recebem chuva
- Ingestão opcional de JPG/PNG/WebP próprio com enquadramento automático
- Produção principal exclusivamente em YouTube longo 16:9, com opções fechadas de 30 ou 60 minutos
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
- Biblioteca de imagens e músicas com licença, confirmação de direitos, rotação automática de faixas e composição multicena
- Duas capas cinematográficas por vídeo no padrão `nocturnal_rain_v1`, comparação A/B e seleção persistente da capa final
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
- Resumo diário compacto no Calendário com concluídos, trabalhos em curso, revisões, bloqueios e próxima ação
- Painel responsivo para desktop e celular, sem Node e sem build
- Pacote isolado por vídeo em `data/jobs/<id>/`

Narração é opcional. `--narration` usa o provedor dedicado configurado por `TTS_PROVIDER`, `TTS_VOICE`, `TTS_RATE` e `TTS_PITCH`; o padrão é Edge TTS em português. A voz local do Windows é o segundo fallback e, se ambas falharem, o modo seguro pode concluir o vídeo apenas com música lo-fi. O pacote registra qual mecanismo de voz foi realmente usado.

## Imagem e música automáticas

Os primeiros testes sem asset usavam apenas um fundo procedural escuro e ruídos ambientais; por isso pareciam não ter imagem e soavam semelhantes. Todo pacote novo agora recebe uma cena aprovada incorporada ao próprio MP4. O botão **Sincronizar imagens e vídeos** e o comando `python app.py sync-video-visuals` nunca trocam apenas o pôster: eles reconstroem o vídeo com a mesma imagem e preservam a versão anterior em `data/archive/video-visual-sync/`.

A série opcional `Anime Nights original` usa uma personagem adulta criada exclusivamente para o projeto, sem copiar franquias, personagens ou artistas. Ela só é escolhida quando o tema menciona explicitamente anime ou personagem; as demais séries continuam sem personagens.

A câmera permanece completamente fixa. O renderizador cria um ciclo visual suave de 12 segundos apenas em uma camada atmosférica localizada: fumaça sobre a xícara nos perfis cozy/focus, chuva mascarada nas janelas ou no plano externo em cenas internas e pontos de luz no cosmic. Em vídeos com 24 segundos ou mais, esse ciclo é codificado uma única vez e repetido por remux, evitando recodificar horas de quadros iguais. Perfil, atmosfera, zona do efeito e estratégia de render ficam registrados em `metadata.json`.

Na **Biblioteca criativa**, o botão **Importar músicas** registra um arquivo ou uma pasta inteira de WAV, MP3, M4A, AAC, FLAC, OGG ou OPUS. A confirmação de direitos comerciais é obrigatória. A cada produção, a fábrica escolhe somente entre faixas ouvidas e aprovadas, registra a escolha no pacote e intercala o catálogo automaticamente; também é possível fixar uma faixa nas opções avançadas. Vídeos longos nunca recebem uma trilha sintética de emergência: se não houver música aprovada, a produção para com uma orientação clara para recompor o catálogo.

O painel **Google Music** oferece dois caminhos oficiais. O Flow Music abre em uma aba protegida pelo Google e usa os créditos da assinatura, mas ainda exige gerar e baixar pelo site. Para automação completa, o Lyria 3 usa a Gemini API: a chave é guardada no cofre criptografado local, nunca retorna ao navegador e a cobrança é separada da assinatura. O botão **Gerar lote diverso** cria, baixa, valida e cataloga 4, 8 ou 12 músicas sem copiar prompts. As 12 direções evitam a antiga receita repetida e alternam BPM, tonalidade, forma, instrumentos e famílias como jazz-hop, bossa, synthwave, ambient, folk, dub, trip-hop e música de câmara.

Para conectar sem editar arquivos, abra **Biblioteca → Conectar chave de API**, crie a chave no [Google AI Studio](https://aistudio.google.com/apikey) e cole no formulário. Como alternativa, defina `GEMINI_API_KEY` no `.env`. O modelo padrão é `lyria-3-pro-preview`; `lyria-3-clip-preview` serve para testes rápidos. Referências oficiais: [geração musical com Lyria 3](https://ai.google.dev/gemini-api/docs/music-generation), [preços](https://ai.google.dev/gemini-api/docs/pricing) e [termos da Gemini API](https://ai.google.dev/gemini-api/terms).

O lote usa no máximo duas gerações simultâneas, preserva resultados parciais quando uma chamada falha e informa custo estimado antes do envio. Faixas recém-geradas permanecem pendentes; geração automática não equivale a aprovação auditiva.

Ao importar um lote aprovado do Flow Music, a opção **Usar este lote no lugar das faixas sintéticas antigas** retira o catálogo de teste da rotação sem apagar seus arquivos ou histórico. O plano Google AI Plus/Starter inclui direitos comerciais segundo a [documentação oficial do Google One](https://support.google.com/googleone/answer/16882689).

O catálogo só aparece como pronto quando passa tanto pelos controles técnicos quanto pela escuta humana. Cada cartão musical possui **Aprovar faixa** e **Reprovar**; a reprovação retira a música da rotação sem apagar o arquivo e também põe em revisão qualquer vídeo publicável ligado a ela. A prévia continua disponível para comparação e a decisão pode ser revertida. O lote só é liberado quando todas as faixas ativas forem ouvidas. `MUSIC_CATALOG_HUMAN_APPROVED` continua disponível apenas como override administrativo; hashes diferentes, sozinhos, não são tratados como variedade sonora.

O kit visual público do canal fica em `assets/channel` e usa exclusivamente a identidade **3AM Shelter**, separada de Pausa Pra Anime e YAMI. Inclui avatar 800×800, banner 2560×1440 com conteúdo dentro da área segura central e marca-d'água transparente. O FFactory permanece como infraestrutura interna. `python scripts/generate_channel_brand.py` recompõe o kit de forma determinística a partir da coleção noturna aprovada.

As capas seguem a coleção oficial `assets/covers/nocturnal-rain-v1`: nove referências 16:9, noite chuvosa, azul/verde profundo, luz âmbar pontual e acabamento anime-realista cinematográfico. O gerador não adiciona mais faixa escura, selo, eyebrow ou título longo. O teste A/B compara duas referências tematicamente próximas; cada variação usa imagem limpa ou texto curto já integrado à arte. A direção reproduzível e o prompt-base ficam em `factory/visual_style.py`.

O backend, os lotes, o calendário, o piloto automático, a interface pública e a linha de comando aceitam somente 1.800 ou 3.600 segundos. Qualquer solicitação abaixo de uma hora é normalizada para 30 minutos; solicitações de uma hora ou mais são normalizadas para 60 minutos. Conteúdos históricos abaixo desse limite podem ser arquivados com `python scripts/archive_short_productions.py`, que preserva uma cópia recuperável do banco e dos pacotes removidos da fila ativa.

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
python app.py lyria-generate --name "Midnight Rhodes" --prompt "Instrumental lo-fi chill with warm Rhodes, 72 BPM, no vocals" --confirm-rights
python app.py generate --topic "Cabana na neve" --duration 1800 --profile youtube_long --narration
python app.py generate --topic "Café ao amanhecer" --duration 3600 --profile youtube_long --asset "C:\Assets\cafe.jpg" --confirm-asset-rights
python app.py doctor
python app.py integrations
python app.py backup
python app.py establish-pilot-cohort --cohort-id pilot-flow-2026-08-30
python app.py repair-manifests
python app.py phase2-status
python app.py commerce-overview
python app.py commerce-pinterest-package ID_DA_CAMPANHA --board-name "Achados úteis"
python app.py bilibili-package ID_DA_PRODUCAO
```

## Acesso de qualquer lugar

O FFactory mantém o renderizador, os MP3, os vídeos e o banco neste computador e publica somente uma porta HTTPS protegida. Isso evita enviar centenas de gigabytes para uma hospedagem comum e permite controlar o Hub pelo celular ou por outro computador enquanto a máquina principal estiver ligada.

1. Instale o conector oficial: `winget install --id Cloudflare.cloudflared --exact`.
2. No `.env`, defina `FACTORY_REMOTE_ACCESS=true`, um `FACTORY_REMOTE_USERNAME` e uma senha exclusiva com pelo menos 16 caracteres em `FACTORY_REMOTE_PASSWORD`.
3. Reinicie o Hub com `.\scripts\start.ps1`.
4. Em outra janela, execute `.\scripts\start-remote.ps1`. O endereço temporário `https://...trycloudflare.com` impresso no terminal funciona em qualquer navegador e solicita o usuário e a senha do FFactory.

O servidor continua vinculado a `127.0.0.1`: nenhuma porta do roteador é aberta. Requisições remotas sem autenticação são recusadas, alterações exigem origem HTTPS igual ao endereço aberto e o diagnóstico nunca devolve a senha. O túnel temporário é apenas para validação e muda ao reiniciar. Para operação diária, crie um túnel nomeado e uma aplicação **Cloudflare Access** ligada a um domínio; permita somente seu e-mail por código de uso único. Essa etapa exige login e seleção do domínio na sua conta Cloudflare.

O computador precisa permanecer ligado e conectado. A hospedagem integral em nuvem fica como uma fase separada porque renderizar 30–60 minutos e armazenar os vídeos exige uma máquina com volume persistente e custo mensal.

Para operar com o computador desligado, use a implantação em nuvem descrita em [`docs/cloud-hosting.md`](docs/cloud-hosting.md). O projeto inclui uma imagem Docker, configuração pronta para Render e uma opção de VPS com HTTPS automático. A nuvem exige um plano pago com disco persistente; os dados atuais não cabem com segurança nas ofertas gratuitas.

O renderizador codifica um ciclo visual curto uma vez e o repete sem recodificar cada quadro das 30/60 minutos, reduzindo drasticamente o tempo e o uso de CPU.

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

- **Lugares sob chuva**, **Mundos acolhedores**, **Foco cósmico** e **Anime Nights original** vêm prontos como séries longas.
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
3. Abra a produção, assista à prévia, compare as capas A/B e confira direção, score e os painéis legíveis de resumo, qualidade e integridade.
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

## Biblioteca criativa

O fluxo gera placeholders originais por padrão. Em **Biblioteca de assets**, registre nome, arquivo, licença, origem e observações e confirme os direitos comerciais. Em **Opções avançadas**, selecione até 12 imagens aprovadas; a fábrica divide o vídeo entre elas, aplica movimento suave e salva `asset-manifest.json` no pacote.

Um caminho avulso ainda pode ser informado para testes rápidos, mas exige confirmação explícita de direitos na interface ou a opção `--confirm-asset-rights` na linha de comando. A biblioteca é o fluxo recomendado porque mantém a rastreabilidade. Não reutilize vídeos de outros canais sem permissão.

Para música, use **Biblioteca → Importar músicas**, cole o caminho de um arquivo ou de uma pasta e escolha a licença correspondente. A pasta é varrida automaticamente, cada faixa é validada por decodificação e até 200 arquivos podem ser registrados de uma vez. Músicas baixadas do YouTube só podem ser usadas quando você possuir licença comercial explícita; a disponibilidade pública do vídeo não concede direitos de reutilização.

## Testes

```powershell
python -m unittest discover -s tests -v
npm install
npx playwright install chromium
npm run test:e2e
```

A suíte cobre agentes, validação, migração/estado da fila, trava de render entre processos, retomada após reinício, calendário com equipe especializada, insights por snapshot, catálogo de licenças, rotação da biblioteca musical, domínios oficiais, segurança da API, streaming por faixa, TTS, thumbnails A/B, renderização otimizada, checksums e composição multicena real com FFmpeg. Playwright e axe-core validam navegação, teclado, acessibilidade, biblioteca musical, limite público de 30/60 minutos e ausência de overflow em desktop e celular no GitHub Actions.

A Biblioteca também pode criar um catálogo inicial de 12 músicas lo-fi originais no próprio computador. As faixas usam arranjos, ritmos, progressões, BPM, texturas e sementes diferentes, recebem manifesto SHA-256 e podem ser ouvidas no Hub antes do lote piloto. Arquivos gerados permanecem locais em `data/library/`; o código publicado no GitHub consegue recriá-los sem distribuir binários de áudio no repositório.

Cada pacote novo inclui `render-report.json`, com o resultado técnico da mídia, e `artifact-manifest.json`, com tamanho e SHA-256 dos arquivos principais. Na interface, os botões **Resumo do vídeo**, **Relatório técnico**, **Controle de qualidade** e **Integridade dos arquivos** abrem explicações legíveis; os JSON permanecem apenas como registro interno auditável.

## Estado do roadmap

0. **Operação noturna:** turno configurável, execução antecipada de até cinco itens do calendário, uma rodada por noite, recuperação após reinício e pausa automática por fila, espaço ou trabalhos ativos.
0. **Escala criativa:** o diretor avalia 48 receitas por produção e combina 12 cenas originais, oito tratamentos, cinco composições, 16 movimentos localizados, 12 arranjos musicais, quatro progressões e cinco texturas. Cada pacote registra um DNA criativo reproduzível.
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
5. **Retenção:** captura e ranking implementados. A conta do YouTube foi reautorizada em modo somente leitura, a Analytics API foi ativada e os cinco primeiros snapshots reais foram sincronizados de forma idempotente.
6. **Voz dedicada e offline:** Edge TTS configurável e voz SAPI local estão implementados e diagnosticados. A ambientação segura continua funcionando quando os dois mecanismos estiverem indisponíveis.
7. **Shopee + Pinterest:** trilha comercial aprovada para transformar produtos oficiais em vídeos próprios e publicar Video Pins rastreáveis; Pinterest nunca será fonte automática de mídia de terceiros.
8. **Bilibili:** pacote localizado entregue no Studio 1.8 com capa neutra, títulos, descrições e legendas em chinês simplificado e inglês; upload manual pelo Creator Studio.
9. **Painel comercial:** campanhas, produtos, links, cliques, conversões, comissão e custo de produção ficarão separados das métricas editoriais.
10. **Central Comercial Shopee:** entregue no Studio 1.5 com catálogo validado, campanhas persistentes, pacote manual e cálculo de resultado.
11. **Pinterest Video Pin:** entregue no Studio 1.6 como pacote local com vídeo, capa, texto alternativo, link, board-alvo e payload da API; login e upload continuam bloqueados.
12. **Renderização protegida:** entregue no Studio 1.7 com reserva atômica de cada produção, arquivo temporário isolado, promoção somente depois do quality gate e checksum obrigatório antes de aprovar ou reutilizar.
13. **Bilibili localizada:** entregue no Studio 1.8 com classificação editorial conservadora, metadados bilíngues, capa sem texto em português e SRTs separados; a revisão humana da primeira localização continua obrigatória.
14. **Equipes e skills especializadas:** entregue no Studio 1.9 com playbooks reais para YouTube, verticais, afiliados e Bilibili, seleção por produção, persistência no calendário e rastreio das skills executadas.
15. **DNA criativo e aprendizagem:** entregue no Studio 2.0 com 25.600 combinações-base por cena, detector de repetição, biblioteca sonora ampliada, movimento localizado e painel de originalidade.
16. **Cortes inteligentes:** módulo local disponível para vídeos aprovados; preserva o original e cria candidatos verticais de 15, 30 e 60 segundos com origem, enquadramento e integridade rastreáveis.

`ALLOW_PLATFORM_PUBLISH=false` permanece o padrão. Credenciais, OAuth e acesso oficial às contas são os bloqueios externos. O lote criativo de validação está certificado, e nenhum novo conteúdo é tornado público sem confirmação. A seção **Publicação** do painel mostra exatamente o que está liberado e o que ainda precisa de revisão.

As telas, callbacks e validações anteriores ao login já estão preparados. Use [docs/platform-setup.md](docs/platform-setup.md) para registrar as URLs de retorno e concluir cada login quando quiser. Até lá, o botão **Pré-validar** apenas prepara a entrega local e confirma bloqueios; ele não chama a plataforma.

## Frente futura de afiliados

O planejamento consolidado está em `docs/roadmap.md`, e a especificação comercial em `docs/commerce-video-roadmap.md`. Pinterest é destino dos nossos próprios Video Pins e fonte de pesquisa de tendências, nunca biblioteca automática de vídeos de terceiros. O módulo comercial só aceita mídia própria, licenciada ou fornecida oficialmente para afiliados.
