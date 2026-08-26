# Faceless Content Factory — Studio MVP 1.0

Uma fábrica local e automatizada para transformar um tema em um pacote de vídeo de ambientação: roteiro, metadados, paisagem sonora, imagem, vídeo MP4, thumbnail, legenda e checklist de publicação. O MVP não envia nada para plataformas; a fila termina em aprovação para upload manual.

## O que já funciona

- Tema digitado, sugerido pelos agentes ou recebido pela linha de comando
- Oito agentes locais: pesquisa, estratégia, roteiro, direção, SEO, conformidade, crítica e reaproveitamento
- Roteiro, título, descrição, tags, capítulos, direção visual/sonora e score de qualidade
- Três cenas-mestre lo-fi originais incluídas: café chuvoso, estúdio acolhedor e lounge cósmico
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
- Quatro templates de séries, geração em lote e calendário editorial
- Início automático dos itens vencidos do calendário, com fila resiliente e publicação ainda manual
- Biblioteca de assets com licença, confirmação de direitos e composição multicena
- Duas thumbnails editoriais por vídeo, comparação A/B e seleção persistente da capa final
- Direcionamento editorial alimentado pelas métricas mais recentes de cada plataforma
- CTR por capa, retenção média, impressões, cliques, conversões e receita por snapshot
- Recomendação da capa vencedora por série sem troca automática arriscada
- Agentes enriquecíveis pela OpenAI Responses API, sempre com fallback local reproduzível
- Pacote `youtube-upload.json` privado e revisável, sem executar upload
- Validador comercial que bloqueia produto divergente, publicidade oculta e mídia sem direitos
- Piloto automático semanal com séries, cadência, horário e duração configuráveis
- Reposição inteligente do calendário sem repetir temas já produzidos ou planejados
- Pausa automática por fila de revisão, trabalhos ativos ou pouco espaço em disco
- Painel responsivo para desktop e celular, sem Node e sem build
- Pacote isolado por vídeo em `data/jobs/<id>/`

Narração é opcional. `--narration` usa voz neural em português e tenta a voz local do Windows como fallback quando ela estiver realmente instalada. Neste computador nenhuma voz SAPI está disponível; por isso o diagnóstico informa essa ausência e o padrão seguro conclui o vídeo com música lo-fi.

## Imagem e música automáticas

Produções antigas não são modificadas retroativamente. Os primeiros testes sem asset usavam apenas um fundo procedural escuro e ruídos ambientais; por isso pareciam não ter imagem e soavam semelhantes. Todo pacote novo agora recebe uma cena ilustrada real do starter pack e uma trilha lo-fi original. O perfil `rain` adiciona chuva baixa atrás da música, enquanto `cozy`, `cosmic` e `focus` usam somente variações musicais e textura leve.

A câmera permanece completamente fixa. O renderizador cria um ciclo visual suave de 12 segundos apenas em uma camada atmosférica localizada: fumaça sobre a xícara nos perfis cozy/focus, chuva no perfil rain e pontos de luz no cosmic. É o efeito de um GIF ambiente, mas entregue diretamente no vídeo MP4/H.264 para preservar qualidade. Perfil, atmosfera e efeitos usados ficam registrados no campo `motion` de `metadata.json`.

O loop musical é sintetizado pelo próprio projeto e não copia gravações ou músicas externas. Tema e perfil determinam seed, progressão, BPM e melodia. Os detalhes ficam em `metadata.json` no campo `music`.

## Início rápido (Windows / PowerShell)

Requisitos: Python 3.11+ e FFmpeg. Esta cópia local contém uma instalação portátil em `.tools/ffmpeg/bin` (a pasta não vai para o GitHub). FFprobe é usado quando estiver disponível; sem ele, a fábrica valida metadados e decodifica uma amostra diretamente com FFmpeg. Instale a dependência opcional de voz com `python -m pip install -r requirements.txt`.

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
python app.py generate --topic "Café ao amanhecer" --duration 12 --profile preview --asset "C:\Assets\cafe.jpg"
python app.py doctor
```

O tempo e o espaço de renderização crescem com a duração. Faça uma prévia antes de iniciar vídeos de várias horas.

## Como os agentes trabalham

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
web/                   painel operacional
tests/                 agentes, banco, API e renderização real
data/jobs/             pacotes gerados (ignorado pelo Git)
```

## Assets próprios

O fluxo gera placeholders originais por padrão. Em **Biblioteca de assets**, registre nome, arquivo, licença, origem e observações e confirme os direitos comerciais. Em **Opções avançadas**, selecione até 12 imagens aprovadas; a fábrica divide o vídeo entre elas, aplica movimento suave e salva `asset-manifest.json` no pacote.

Um caminho avulso ainda pode ser informado para testes rápidos, mas a biblioteca é o fluxo recomendado porque mantém a rastreabilidade. Não reutilize vídeos de outros canais sem permissão.

## Testes

```powershell
python -m unittest discover -s tests -v
```

A suíte cobre agentes, validação, migração/estado da fila, retomada após reinício, calendário automático, insights por snapshot, catálogo de licenças, segurança da API, streaming por faixa, fallback de voz, thumbnails A/B, renderização simples, checksums e composição multicena real com FFmpeg. A interface também é validada em desktop e viewport móvel.

Cada pacote novo inclui `render-report.json`, com o resultado técnico da mídia, e `artifact-manifest.json`, com tamanho e SHA-256 dos arquivos principais. Esses relatórios não publicam nada; servem para detectar pacotes incompletos antes da sua aprovação.

## Estado do roadmap

0. **Variedade criativa:** sete cenas-mestre originais, seleção por tema, três arranjos musicais, progressões rotativas e partículas variadas pela seed editorial. Cada pacote registra sua impressão digital criativa.
0. **Quality gate automático:** cada render é amostrado e bloqueado antes da aprovação se houver tela preta, ausência de movimento, câmera não fixa, áudio inaudível/clipping, duração ou decodificação inválida.
0. **Reaproveitamento vertical:** produções aprovadas agora geram um recorte 9:16 validado e pacotes manuais para Shorts, Reels e TikTok, sem upload automático.

1. **Conector opcional de LLM:** implementado com Responses API, Structured Outputs, `store=false` e fallback local. Só ativa com `OPENAI_API_KEY`.
2. **Microvariações sonoras:** implementadas por seed, BPM, progressão, melodia e perfil.
3. **CTR e capas:** implementados no banco, API e painel; a fábrica recomenda vencedoras por série sem fazer trocas cegas.
4. **YouTube:** pacote privado oficial preparado após aprovação. O upload real depende do arquivo OAuth da conta e continuará exigindo confirmação humana.
5. **Retenção:** captura e ranking implementados. A coleta automática depende da autorização da conta/plataforma.
6. **Voz offline:** fallback implementado e diagnosticado, mas este Windows não possui uma voz SAPI instalada. A ambientação segura continua funcionando.

`ALLOW_PLATFORM_PUBLISH=false` permanece o padrão. Credenciais, OAuth e acesso oficial às contas são os únicos bloqueios externos restantes; nenhum conteúdo é tornado público sem confirmação.

## Frente futura de afiliados

O planejamento para Shopee está documentado em `docs/commerce-video-roadmap.md`. Pinterest será tratado como referência de pesquisa, não como fonte automática de vídeos sem autorização. O módulo comercial só deverá aceitar mídia própria, licenciada ou fornecida oficialmente para afiliados.

