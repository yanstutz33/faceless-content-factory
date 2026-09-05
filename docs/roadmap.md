# Roadmap executivo — Faceless Content Factory

Última revisão: 03/09/2026. O roadmap separa o que já foi validado localmente, o que a fábrica pode automatizar sem contas externas e o que depende de login ou decisão humana. Publicação pública automática continua desativada por padrão. Hospedagem permanente foi adiada para manter custo zero; o Hub continua disponível localmente enquanto o computador estiver ligado.

## Estado atual verificável

### Base operacional concluída

- pipeline Python com fila, reserva exclusiva de trabalho, renderização atômica e validação de integridade;
- vídeos longos públicos limitados a 30 ou 60 minutos, com bloqueio de artefatos menores;
- biblioteca de músicas próprias/licenciadas, ingestão local, catálogo, checksums e rastreabilidade de direitos;
- composição com câmera fixa, movimentos localizados e tratamento de imagem sem tremor artificial;
- agentes de planejamento, criação, áudio, montagem, qualidade, aprovação e empacotamento;
- detector histórico de repetição e DNA criativo para imagem, composição, movimento e som;
- quality gate, aprovação manual, pacotes de publicação e registro local de métricas;
- coortes explícitas de piloto, manifestos completos sem hash autorreferente e validação integral antes da aprovação;
- Hub responsivo com navegação direta, acessibilidade automatizada, feedback de erro e tema editorial;
- conector do YouTube autenticado e envio privado controlado operacional; os demais conectores continuam preparados até o ponto anterior à autenticação.

### Limites atuais

- variedade real de áudio depende de uma biblioteca com faixas diferentes e direitos documentados;
- a fábrica não deve prometer diversidade visual antes de ampliar e validar o catálogo de cenas;
- TikTok, Instagram, Pinterest, Shopee e Bilibili ainda exigem login/configuração manual;
- o YouTube aceita somente upload privado com confirmação humana explícita; publicação pública permanece bloqueada.

## Próximas fases, em ordem

### Fase 1 — Catálogo criativo de produção — pilotos em revisão

Objetivo: eliminar a repetição perceptível antes de aumentar o volume.

- gerar ou importar e validar pelo menos 12 faixas lo-fi/chill perceptivelmente diferentes, com licença e atribuição quando exigida — **concluído: 13 faixas ouvidas, aprovadas e em rotação; as 24 faixas antigas continuam preservadas em quarentena**;
- ampliar para pelo menos 12 cenas-base originais, com zonas de movimento coerentes — **concluído: 23 registros visuais disponíveis; a coorte oficial usa somente as nove referências personalizadas aprovadas e ignora assets históricos/de teste**;
- criar combinações por intenção: foco, leitura, sono, madrugada, melancolia e relaxamento;
- impedir repetição recente de faixa, cena, paleta, enquadramento e arranjo;
- gerar 10 vídeos longos de validação e aprovar apenas os que passarem no controle técnico e criativo — **concluído automaticamente: 13 pilotos de 30 minutos passaram em integridade, qualidade, direitos, áudio distinto e DNA visual integral distinto; os 13 aguardam avaliação humana**;
- manter capas 16:9 no padrão cinematográfico noturno aprovado — **concluído: nove referências únicas em `nocturnal_rain_v1`, incluindo uma nova cena original gerada pela fábrica, sem banners, títulos longos ou câmera artificial**;
- manter títulos e descrições públicas em inglês natural, com frases emocionais curtas e reconfortantes — **concluído: gerador e os 13 pilotos oficiais migrados para inglês; os temas internos em português continuam preservados apenas para operação do Hub**;
- sincronizar capas e vídeos históricos com backup recuperável — **concluído em 35 pacotes: a imagem aprovada foi incorporada ao MP4 e comparada após o play; 22 pacotes históricos foram preservados fora da fila publicável**;
- preparar geração musical externa sem tornar a montagem dependente de uma plataforma — **implementado: importação rastreável do Flow e geração direta em lote com Lyria 3 pela Gemini API; o Hub cria, baixa, valida e cataloga 4, 8 ou 12 faixas com direções musicalmente distintas, mantendo revisão auditiva obrigatória**.

Resultado parcial: a coorte explícita `pilot-flow-2026-08-30` contém somente os 13 pilotos atuais. Eles têm 30 minutos, usam 13 músicas aprovadas sem repetição no lote, 13 DNAs visuais integrais distintos e nota de novidade mínima de 70,3. Todos passaram no controle técnico automático e permanecem em `aguardando aprovação`; nenhum foi publicado externamente. Outros 22 pacotes históricos foram movidos para revisão/quarentena sem exclusão de arquivos. Os 35 manifestos completos foram reparados e validados sem hash autorreferente. O Centro de Publicação certifica apenas a coorte oficial e separa os controles automáticos da revisão humana. As 24 faixas antigas continuam preservadas em quarentena. O kit público **Pausa Pra Anime · by YAMI** para YouTube continua pronto; FFactory segue apenas como infraestrutura interna.

Critério de conclusão: 10 de 10 vídeos com duração válida, áudio distinto no lote, imagem coerente, sem chuva dentro de ambientes, sem tremor de câmera e com manifesto de direitos completo.

Automação: ingestão, validação técnica, registro, rotação, montagem e certificação do lote estão automatizados. Permanecem humanas a revisão visual/auditiva final dos 13 pilotos e as decisões de publicação.

Nota sobre A/B: as variantes atuais usam deliberadamente a mesma cena do vídeo para impedir que o pôster seja trocado por uma imagem diferente após o play. Um experimento A/B real deverá variar apenas enquadramento ou tratamento da mesma cena, sem quebrar essa identidade.

### Fase 2 — Piloto automático sem publicação — concluída

Objetivo: provar que a fábrica consegue trabalhar sozinha de ponta a ponta.

- gerar pauta, roteiro leve/metadados, composição, thumbnail e pacote de publicação em lote;
- executar renderização noturna com retomada segura após falha;
- priorizar automaticamente ideias com maior novidade e menor risco de repetição;
- criar um relatório diário simples: concluídos, bloqueados, motivo e ação recomendada — **implementado no Calendário, com endpoint somente leitura e garantia explícita de que não publica**;
- manter todos os resultados na fila de aprovação local.
- registrar cada execução como uma coorte autônoma auditável e certificar automaticamente a sequência de três lotes — **implementado: cada turno recebe um identificador próprio, valida manifesto, mídia, qualidade e pacote local; nenhuma aprovação ou publicação é inferida**;
- impedir o início da Fase 2 enquanto o piloto explícito não tiver pelo menos dez aprovações humanas — **implementado no turno noturno e exposto no diagnóstico da Fase 2**.

Critério de conclusão: três lotes consecutivos terminam sem intervenção e sem artefatos inválidos.

Automação: completa, sem publicar externamente.

Resultado verificado em 02/09/2026: três coortes autônomas consecutivas produziram seis vídeos de 30 minutos, todos com nota automática 92/100, manifestos íntegros e pacotes locais. Não houve falha, recuperação manual, artefato inválido ou publicação externa. A certificação da Fase 2 permanece auditável no Hub.

### Fase 3 — YouTube privado e métricas reais

Objetivo: validar o canal principal com risco mínimo.

- configurar projeto OAuth e conectar a conta oficial do YouTube;
- enviar inicialmente como privado ou não listado;
- confirmar título, descrição, thumbnail, duração, áudio e processamento da plataforma;
- importar impressões, CTR, retenção e tempo de exibição;
- manter confirmação humana antes de tornar um vídeo público durante o piloto.

Progresso verificado em 04/09/2026: **2 uploads privados concluídos para o primeiro piloto, sendo um original preservado e um substituto validado em 1080p**. O envio original `3qfjb0BCuPU` confirmou capa, áudio e 720p, mas sua fonte havia sido produzida em 1280×720. O pacote foi reconstruído em 1920×1080, H.264 High, 30 fps, `yuv420p` limitado BT.709 e áudio AAC, com controle automático 100/100. A revisão visual também restringiu a chuva animada ao plano das janelas, sem atravessar a personagem ou a cama. O substituto privado `VijwOMULOiE` foi enviado com título e descrição em inglês, thumbnail personalizada e conteúdo não destinado a crianças. O YouTube concluiu os processamentos SD e HD, e o player oferece `1080p HD`, `720p`, `480p` e `360p`. O upload original continua privado e preservado até a decisão humana sobre a publicação. Os outros 12 pilotos oficiais também permanecem validados em 1920×1080.

Critério de conclusão: cinco uploads privados corretos e cinco publicações aprovadas sem divergência entre o pacote local e o YouTube.

Automação: preparação, upload privado e coleta de métricas. Manual: login inicial e confirmação de publicação.

### Fase 4 — Aprendizado criativo controlado

Objetivo: aprender com desempenho sem transformar todos os vídeos em cópias do vencedor.

- registrar CTR, retenção por trecho, tempo de exibição e retorno de audiência;
- comparar cena, faixa, paleta, título e thumbnail por coortes;
- manter novidade com peso dominante e limitar a influência de métricas recentes;
- sugerir testes A/B, nunca substituir criativos aprovados silenciosamente;
- exibir a justificativa de cada recomendação no Hub.

Critério de conclusão: recomendações reproduzíveis, auditáveis e baseadas em volume mínimo de dados.

### Fase 5 — Cortes inteligentes verticais

Objetivo: reutilizar apenas vídeos longos já aprovados em Shorts, TikTok e Reels.

- detectar capítulos, mudanças musicais, regiões seguras e possíveis ganchos;
- gerar candidatos 9:16 específicos por plataforma, sem alterar o original;
- adaptar legenda, título, duração e enquadramento para cada destino;
- executar quality gate próprio e manter aprovação manual.

Critério de conclusão: cada corte preserva o assunto principal, não corta texto/rosto e possui origem rastreável. Contrato: [smart-cuts-architecture.md](smart-cuts-architecture.md).

### Fase 6 — TikTok e Instagram

Objetivo: conectar os fluxos verticais somente depois do piloto de cortes.

- concluir contas, OAuth e permissões oficiais;
- testar upload privado/rascunho onde a API permitir;
- coletar retenção, conclusão, compartilhamentos e cliques;
- criar estratégias separadas por plataforma, sem replicação cega.

Automação: pacote, validação e métricas. Manual: login e publicação onde não houver API oficial adequada.

### Fase 7 — Shopee + Pinterest comercial

Objetivo: operar afiliados sem misturar o catálogo editorial com campanhas.

- importar produto exato, link rastreável, preço e mídia autorizada;
- gerar vídeo comercial original e reutilizá-lo como Video Pin;
- validar alegações, direitos e divulgação `#publicidade`;
- conectar Pinterest Business e recursos oficiais disponíveis da Shopee;
- registrar cliques, conversões, comissão, custo, lucro e ROI;
- nunca baixar nem republicar automaticamente vídeos de outros Pins.

Critério de conclusão: produto, criativo e origem de mídia rastreáveis; nenhuma campanha é publicada sem revisão.

### Fase 8 — Bilibili localizado

Objetivo: testar distribuição sem tradução literal ou automação frágil.

- revisar títulos, descrição, capa e legendas em inglês e chinês simplificado;
- validar categoria, contexto cultural e direitos do conteúdo;
- usar primeiro o pacote manual `bilibili-upload.json`;
- automatizar upload somente com acesso oficial estável, autorizado e testado;
- registrar métricas separadamente das plataformas ocidentais.

## Portas de qualidade para publicação

Um lote só avança quando todas as condições abaixo forem verdadeiras:

1. nenhum vídeo longo tem menos de 30 minutos;
2. início, meio e fim decodificam corretamente;
3. vídeo público do YouTube é produzido em 1920×1080 e só é liberado depois que o processamento HD termina;
4. faixa e cena não repetem a janela configurada;
5. imagem, movimento e efeitos respeitam a lógica física da cena;
6. música e imagens possuem origem e direitos registrados;
7. título, descrição, thumbnail e arquivo final pertencem à mesma produção;
8. testes automatizados e CI estão verdes;
9. publicação permanece manual até o piloto específico da plataforma ser aprovado.

## Próxima ação recomendada

Piloto criativo, Fase 2, OAuth oficial do YouTube e validação privada do primeiro piloto em 1080p concluídos. A próxima decisão humana é publicar ou manter privado o substituto `VijwOMULOiE`; o vídeo original permanece privado. Depois dessa decisão, mais quatro pilotos poderão ser enviados, um de cada vez, mantendo confirmação humana antes de cada envio e de qualquer publicação pública.
