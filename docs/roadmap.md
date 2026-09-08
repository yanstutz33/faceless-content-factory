# Roadmap executivo — Faceless Content Factory

Última revisão: 07/09/2026. O roadmap separa o que foi validado localmente, o que foi confirmado no YouTube e o que ainda depende de contas ou dados externos. Publicação pública automática continua desativada por padrão: o envio começa privado, passa por integridade e processamento HD e somente então recebe a liberação já autorizada no Studio. Hospedagem permanente foi adiada para manter custo zero; o Hub continua disponível localmente enquanto o computador estiver ligado.

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
- o conector envia ao YouTube somente como privado; a mudança para público é feita no Studio depois da confirmação de HD;
- coleta de métricas do YouTube está operacional em modo somente leitura; a autorização foi renovada e a YouTube Analytics API foi ativada no projeto oficial.

## Próximas fases, em ordem

### Fase 1 — Catálogo criativo de produção — concluída

Objetivo: eliminar a repetição perceptível antes de aumentar o volume.

- gerar ou importar e validar pelo menos 12 faixas lo-fi/chill perceptivelmente diferentes, com licença e atribuição quando exigida — **concluído: 13 faixas ouvidas, aprovadas e em rotação; as 24 faixas antigas continuam preservadas em quarentena**;
- ampliar para pelo menos 12 cenas-base originais, com zonas de movimento coerentes — **concluído: 23 registros visuais disponíveis; a coorte oficial usa somente as nove referências personalizadas aprovadas e ignora assets históricos/de teste**;
- criar combinações por intenção: foco, leitura, sono, madrugada, melancolia e relaxamento;
- impedir repetição recente de faixa, cena, paleta, enquadramento e arranjo;
- gerar 10 vídeos longos de validação e aprovar apenas os que passarem no controle técnico e criativo — **concluído: 13 pilotos de 30 minutos passaram em integridade, qualidade, direitos, áudio distinto e DNA visual integral distinto; os 13 foram aprovados**;
- manter capas 16:9 no padrão cinematográfico noturno aprovado — **concluído: nove referências únicas em `nocturnal_rain_v1`, incluindo uma nova cena original gerada pela fábrica, sem banners, títulos longos ou câmera artificial**;
- manter títulos e descrições públicas em inglês natural, com frases emocionais curtas e reconfortantes — **concluído: gerador e os 13 pilotos oficiais migrados para inglês; os temas internos em português continuam preservados apenas para operação do Hub**;
- sincronizar capas e vídeos históricos com backup recuperável — **concluído em 35 pacotes: a imagem aprovada foi incorporada ao MP4 e comparada após o play; 22 pacotes históricos foram preservados fora da fila publicável**;
- preparar geração musical externa sem tornar a montagem dependente de uma plataforma — **implementado: importação rastreável do Flow e geração direta em lote com Lyria 3 pela Gemini API; o Hub cria, baixa, valida e cataloga 4, 8 ou 12 faixas com direções musicalmente distintas, mantendo revisão auditiva obrigatória**.

Resultado verificado em 06/09/2026: a coorte explícita `pilot-flow-2026-08-30` contém 13 pilotos aprovados. Eles têm pelo menos 30 minutos, usam 13 músicas aprovadas sem repetição no lote, 13 DNAs visuais integrais distintos e nota de novidade mínima de 70,3. Outros 22 pacotes históricos foram movidos para revisão/quarentena sem exclusão de arquivos. Os manifestos são validados sem hash autorreferente e os derivados ficam vinculados por hash à versão exata do vídeo, thumbnail e metadados. As 24 faixas antigas continuam preservadas em quarentena. A identidade pública ativa é **3AM Shelter**; FFactory segue como infraestrutura interna.

Critério de conclusão: 10 de 10 vídeos com duração válida, áudio distinto no lote, imagem coerente, sem chuva dentro de ambientes, sem tremor de câmera e com manifesto de direitos completo.

Automação: ingestão, validação técnica, registro, rotação, montagem e certificação do lote estão automatizados. Permanecem humanas a decisão editorial e a liberação pública.

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

### Fase 3 — YouTube publicado e coletor real operacional — concluída

Objetivo: validar o canal principal com risco mínimo.

- configurar projeto OAuth e conectar a conta oficial do YouTube;
- enviar inicialmente como privado ou não listado;
- confirmar título, descrição, thumbnail, duração, áudio e processamento da plataforma;
- importar impressões, CTR, retenção e tempo de exibição;
- manter confirmação humana antes de tornar um vídeo público durante o piloto.

Progresso verificado em 07/09/2026: **cinco pilotos publicados, todos processados em HD a partir de arquivos 1920×1080, H.264, 30 fps, `yuv420p` limitado BT.709 e áudio AAC**. O player público confirmou 1080p e 30:00 nos novos envios. Os títulos foram alinhados às cenas realmente codificadas, e a thumbnail usa a mesma fonte visual vista após o play. Publicações: `VijwOMULOiE`, `rv-Vl0wlns4`, `08UvW-_bB7w`, `4F-wDCrSxYk` e `kF_khVghtrc`. O envio original em 720p `3qfjb0BCuPU` e os vídeos históricos continuam privados e preservados. Os 12 Shorts públicos da identidade anterior também foram tornados privados, sem exclusão, e os dois rascunhos foram preservados. O canal público agora exibe somente os cinco vídeos do 3AM Shelter, com foto, banner, descrição e identificador `@3AMShelterMusic` confirmados ao vivo. O Hub registra os cinco como `uploaded_public` e impede que um pré-teste posterior apague esse estado.

Critério de publicação concluído: cinco uploads privados corretos e cinco publicações aprovadas sem divergência entre o pacote local e o YouTube. O coletor oficial consulta Data API e Analytics API em modo somente leitura, vincula cada `video_id` ao trabalho local, registra snapshots diários idempotentes e preserva entradas manuais. Em 06/09/2026 a conta foi reautorizada com os escopos de leitura, a YouTube Analytics API foi ativada e os primeiros cinco snapshots reais foram importados. Uma segunda sincronização atualizou os mesmos cinco registros, sem duplicá-los e sem alterar publicação alguma. Como os vídeos ainda não tinham visualizações registradas, o aprendizado permanece corretamente em exploração até atingir a amostra mínima.

Automação: preparação, upload privado e coleta de métricas. Manual: login inicial e confirmação de publicação.

### Fase 4 — Aprendizado criativo controlado

Objetivo: aprender com desempenho sem transformar todos os vídeos em cópias do vencedor.

- registrar CTR, retenção por trecho, tempo de exibição e retorno de audiência;
- comparar cena, faixa, paleta, título e thumbnail por coortes;
- manter novidade com peso dominante e limitar a influência de métricas recentes;
- sugerir testes A/B, nunca substituir criativos aprovados silenciosamente;
- exibir a justificativa de cada recomendação no Hub.

Critério de conclusão: recomendações reproduzíveis, auditáveis e baseadas em volume mínimo de dados.

Estado técnico em 07/09/2026: armazenamento de CTR, retenção média, tempo assistido, impressões, comentários e compartilhamentos concluído; os cinco vídeos possuem snapshots reais com fonte, data e identificador externo. A coleta direcionada oficial já traz visualizações, retenção, tempo assistido e engajamento. A YouTube Reporting API entregou o primeiro relatório diário `channel_reach_basic_a1`, com cinco linhas vinculadas corretamente; impressões e CTR ainda estão zerados na origem. A influência das métricas continua limitada a 20%, com novidade dominante e exploração automática enquanto não houver volume estatístico suficiente. O mecanismo está concluído, mas o critério de aprendizado depende de audiência real e não pode ser fabricado localmente.

### Fase 5 — Cortes inteligentes verticais

Objetivo: reutilizar apenas vídeos longos já aprovados em Shorts, TikTok e Reels.

- detectar capítulos, mudanças musicais, regiões seguras e possíveis ganchos;
- gerar candidatos 9:16 específicos por plataforma, sem alterar o original;
- adaptar legenda, título, duração e enquadramento para cada destino;
- executar quality gate próprio e manter aprovação manual.

Critério de conclusão: cada corte preserva o assunto principal, não corta texto/rosto e possui origem rastreável. Contrato: [smart-cuts-architecture.md](smart-cuts-architecture.md).

Implementação concluída localmente em 07/09/2026: `smart_cuts_v1` gera candidatos de 15, 30 e 60 segundos em 1080×1920 a partir de capítulos do vídeo aprovado. O quadro original inteiro é preservado sobre fundo desfocado, cada corte recebe timestamps, SHA-256 da fonte, motivo de seleção, relatório técnico e textos próprios para Shorts, TikTok e Reels. Os cinco vídeos públicos certificados receberam 15 candidatos reais; todos passaram em duração, H.264, `yuv420p`, áudio AAC e resolução. Os 15 também passaram por revisão editorial assistida com amostras visuais do ponto médio, preservação do enquadramento e conferência dos gates completos. Os 13 pacotes da coorte oficial foram reconstruídos e recertificados: 13 elegíveis, 13 íntegros e nenhum bloqueado. Nenhum corte foi enviado às plataformas.

### Fase 6 — TikTok e Instagram — implementação local concluída

Objetivo: conectar os fluxos verticais somente depois do piloto de cortes.

- concluir contas, OAuth e permissões oficiais;
- testar upload privado/rascunho onde a API permitir;
- coletar retenção, conclusão, compartilhamentos e cliques;
- criar estratégias separadas por plataforma, sem replicação cega.

Automação: pacote, validação e métricas. Manual: login e publicação onde não houver API oficial adequada.

Estado verificado em 07/09/2026: estratégia separada por plataforma, pacote vertical, textos, validação e pré-teste de publicação concluídos. O pré-teste oficial não contatou a rede nem publicou conteúdo e confirmou que os arquivos estão aptos. A ativação real depende de credenciais de aplicativo, autenticação OAuth e aprovação manual do primeiro piloto nas contas profissionais do TikTok e Instagram — dependências externas que não podem ser concluídas sem essas contas.

### Fase 7 — Shopee + Pinterest comercial — implementação local concluída

Objetivo: operar afiliados sem misturar o catálogo editorial com campanhas.

- importar produto exato, link rastreável, preço e mídia autorizada;
- gerar vídeo comercial original e reutilizá-lo como Video Pin;
- validar alegações, direitos e divulgação `#publicidade`;
- conectar Pinterest Business e recursos oficiais disponíveis da Shopee;
- registrar cliques, conversões, comissão, custo, lucro e ROI;
- nunca baixar nem republicar automaticamente vídeos de outros Pins.

Critério de conclusão: produto, criativo e origem de mídia rastreáveis; nenhuma campanha é publicada sem revisão.

Estado verificado em 07/09/2026: validação do produto exato, direitos, divulgação publicitária, campanha, métricas, ROI, pacote Pinterest Video Pin e pré-teste da Shopee concluídos. Os pacotes passam na validação local sem contato com a rede. O aplicativo Pinterest já foi criado e o fluxo OAuth oficial está implementado, mas o acesso trial permanece pendente e o token temporário não possui os escopos de escrita. A ativação real depende do segredo liberado pelo Pinterest, OAuth da conta Business, catálogo autorizado e conta de parceiro/afiliado Shopee.

### Fase 8 — Bilibili localizado — pacote concluído

Objetivo: testar distribuição sem tradução literal ou automação frágil.

- revisar títulos, descrição, capa e legendas em inglês e chinês simplificado;
- validar categoria, contexto cultural e direitos do conteúdo;
- usar primeiro o pacote manual `bilibili-upload.json`;
- automatizar upload somente com acesso oficial estável, autorizado e testado;
- registrar métricas separadamente das plataformas ocidentais.

Estado verificado em 07/09/2026: capa, títulos, descrições, legendas em inglês e chinês simplificado, manifesto e pacote manual `bilibili-upload.json` concluídos. A localização `curated_scene_and_intent_v2` diferencia cenas como apartamento, cafeteria, trem, observatório, estação orbital, biblioteca, cabana, estufa, lavanderia e loja de discos, inclusive quando o título também contém palavras genéricas como “rain”. A ativação real depende de uma conta creator, revisão final por falante nativo e aprovação do primeiro envio manual.

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

## Próximos passos completos

Todo o trabalho local e automatizável das fases 1 a 8 está implementado. O ciclo real do YouTube foi fechado com identidade pública limpa em `@3AMShelterMusic`, cinco vídeos públicos em 1080p, cinco snapshots reais importados, 15 cortes verticais aprovados e 13 pacotes oficiais íntegros. Os passos abaixo começam nas dependências externas e estendem o produto até uma operação comercializável.

### Prioridade 0 — segurança e continuidade

1. Revogar e gerar novamente qualquer token que tenha aparecido em captura de tela, especialmente o token temporário do Pinterest; nunca reutilizar o valor exposto.
2. Manter segredos apenas no cofre criptografado do Hub ou nas variáveis privadas do ambiente; nunca gravá-los no repositório, nos relatórios ou na interface.
3. Confirmar que o projeto Google OAuth continua em modo adequado aos usuários autorizados e que somente os escopos realmente usados estão habilitados.
4. Testar restauração do backup mais recente em uma cópia isolada, além de apenas testar sua integridade.
5. Criar uma rotina mensal de rotação de credenciais, revisão de permissões, backup e teste de recuperação.

Critério de conclusão: nenhum segredo exposto permanece válido e uma restauração completa funciona sem afetar os dados principais.

Progresso em 07/09/2026: os comandos `backup-restore-test` e `security-audit` foram implementados e executados nos dados reais. A restauração isolada passou na integridade, abriu 12 tabelas e conferiu os registros sem tocar no banco principal; a cópia temporária foi removida. A auditoria confirmou zero segredo ou arquivo sensível versionado, cofre Windows DPAPI ativo, publicação automática bloqueada e proteção do acesso remoto. A troca do token exposto do Pinterest continua obrigatória. O mesmo aplicativo Pinterest pode ser mantido — somente a credencial deve ser revogada e renovada.

### Prioridade 1 — operação editorial do 3AM Shelter

1. Manter um calendário inicial sustentável de um vídeo longo por semana; aumentar somente após quatro semanas sem falha operacional.
2. Usar exclusivamente títulos em inglês natural, curtos e coerentes com a cena, como `Go to Sleep, It's 3 A.M.` e `It's Okay. Get Some Rest.`.
3. Revisar antes de cada publicação: imagem exibida antes e depois do play, faixa correta, duração, 1080p, thumbnail, título, descrição, direitos e visibilidade pública.
4. Preservar a linha visual aprovada: noite chuvosa, cidade japonesa ou interior acolhedor, contraste azul/verde com luz âmbar, atmosfera cinematográfica e sem aparência cartunesca genérica.
5. Impedir repetição musical por impressão digital, estrutura, timbre, andamento e clima; não considerar apenas o nome do arquivo.
6. Criar grupos musicais distintos — sono, leitura, exaustão, memória, chuva urbana e retorno para casa — com instrumentos e dinâmica próprios.
7. Manter o Google Flow como produção manual/importada enquanto não houver integração oficial estável; usar a integração Lyria disponível no Hub somente com limite de custo e revisão humana.
8. Registrar para cada faixa: origem, prompt, data, ferramenta, licença, arquivo mestre e produções em que foi utilizada.

Critério de conclusão: quatro semanas de publicações consistentes, sem mídia incorreta, repetição evidente, falha de qualidade ou problema de direitos.

Progresso em 07/09/2026: o piloto automático foi corrigido para representar frequência semanal real, três pautas automáticas vencidas e sem produção foram arquivadas, e a cadência foi reduzida de três para um vídeo por semana. Uma combinação contraditória de noite com amanhecer foi identificada, arquivada e bloqueada no gerador. A próxima pauta ficou planejada para 11/09/2026 às 19:00, sem renderização ou publicação. Treze pacotes antigos de validação foram removidos da fila ativa de revisão sem exclusão de arquivos; os quatro lotes da Fase 2 continuam certificados e agora registram zero revisão pendente. O comando `music-diversity-audit` comparou as 13 faixas aprovadas em 78 pares e não encontrou duplicatas exatas ou quase duplicatas; o relatório é somente leitura e não substitui audição humana. A automação editorial está ativa, sem bloqueios, e continua incapaz de publicar sozinha.

### Prioridade 2 — aprendizado com dados reais

1. Sincronizar métricas do YouTube semanalmente, sem alterar automaticamente a estratégia por oscilações de poucas visualizações.
2. Aguardar amostra mínima antes de comparar títulos, capas e temas; manter o modo de exploração enquanto impressões e CTR forem insuficientes.
3. Registrar CTR, impressões, retenção nos primeiros 30 segundos, duração média, tempo assistido, origem do tráfego, inscritos, comentários e compartilhamentos.
4. Comparar apenas uma variável principal por teste: título, thumbnail, cena, duração ou família musical.
5. Criar uma revisão mensal com três decisões: manter, ajustar ou retirar um formato.
6. Nunca comprar visualizações, usar engajamento artificial ou fabricar métricas.

Critério de conclusão: recomendações reproduzíveis baseadas em volume real, com histórico da hipótese, amostra, resultado e decisão.

Progresso em 07/09/2026: a sincronização oficial permanece somente leitura e os cinco vídeos continuam vinculados aos identificadores corretos. O relatório diário de alcance possui cinco linhas; impressões e CTR continuam zerados na fonte, portanto o sistema permanece em exploração e não promove uma falsa conclusão estatística.

### Prioridade 3 — piloto de Shorts, TikTok e Instagram Reels

1. Criar ou confirmar contas profissionais com a identidade 3AM Shelter, e-mail de recuperação e autenticação em dois fatores.
2. Criar os aplicativos oficiais do TikTok e Meta, solicitar somente as permissões necessárias e concluir o OAuth de cada conta.
3. Fazer o primeiro envio como rascunho ou privado quando a plataforma permitir.
4. Conferir manualmente enquadramento 1080×1920, áudio, texto, loop, título, descrição e ausência de elementos cortados.
5. Publicar primeiro três cortes diferentes, um por vídeo de origem, sem despejar os 15 candidatos de uma vez.
6. Medir retenção, conclusão, repetição, compartilhamentos, salvamentos, visitas ao perfil e cliques separadamente por plataforma.
7. Aprovar publicação automática somente depois de três pilotos consecutivos sem erro por plataforma.
8. Manter limites diários, botão de pausa e registro auditável de cada tentativa de publicação.

Critério de conclusão: TikTok e Instagram possuem OAuth válido, três pilotos aprovados cada e métricas reais importadas sem duplicação.

### Prioridade 4 — Pinterest e Shopee comercial

1. Revogar o token temporário exposto e aguardar/liberar o acesso trial do aplicativo Pinterest.
2. Obter o segredo do aplicativo, concluir OAuth da conta Business e validar os escopos de criação e leitura necessários.
3. Criar a conta de parceiro/afiliado Shopee e confirmar por escrito quais APIs e recursos estão disponíveis para a região da conta.
4. Importar somente catálogo real com preço, disponibilidade, link rastreável, comissão e mídia cujo uso esteja autorizado.
5. Separar totalmente campanhas comerciais do catálogo editorial do 3AM Shelter.
6. Revisar alegações, direitos, transparência publicitária e destino do link antes de cada campanha.
7. Fazer um piloto com um único produto e um criativo original; reutilizar esse criativo como Video Pin somente após validação.
8. Medir cliques, conversões, cancelamentos, comissão líquida, custo e ROI; pausar automaticamente campanhas com produto indisponível ou link inválido.

Critério de conclusão: um produto rastreável percorre catálogo, revisão, publicação e métricas sem uso indevido de mídia ou promessa enganosa.

### Prioridade 5 — Bilibili localizado

1. Criar e verificar uma conta creator com autenticação em dois fatores.
2. Contratar ou obter revisão de um falante nativo para título, descrição, capa, legenda e adequação cultural.
3. Fazer o primeiro upload manual usando `bilibili-upload.json` e confirmar categoria, direitos, qualidade e processamento.
4. Manter métricas do Bilibili separadas do YouTube e das plataformas verticais.
5. Considerar automação somente se houver acesso oficial estável e depois de três envios manuais corretos.

Critério de conclusão: primeiro vídeo revisado por falante nativo, publicado corretamente e acompanhado por métricas próprias.

### Prioridade 6 — disponibilidade do Hub sem custo inicial

1. Manter o Hub local e protegido enquanto a exigência for custo zero; o endereço temporário depende de o computador permanecer ligado.
2. Não prometer acesso permanente antes de existir hospedagem contínua e armazenamento adequado aos vídeos.
3. Preparar configuração reproduzível, inventário de arquivos, backup e instruções de implantação para reduzir a migração futura.
4. Avaliar planos gratuitos apenas se suportarem aplicação, banco, armazenamento e limites de execução sem comprometer segurança ou confiabilidade.
5. Quando houver orçamento ou infraestrutura gratuita realmente suficiente, implantar primeiro um ambiente de teste, validar login, upload, reprodução, backup e restauração, e só então migrar a operação.

Critério de conclusão: Hub acessível por HTTPS sem depender do computador pessoal, com autenticação, persistência, backup e restauração verificados.

### Prioridade 7 — produto comercializável

1. Separar dados, canais, arquivos e credenciais por cliente ou espaço de trabalho.
2. Implementar contas de usuário, recuperação de acesso, papéis de administrador/editor/revisor e trilha de auditoria.
3. Criar onboarding guiado, dados de demonstração descartáveis e estados vazios claros; nenhum cliente deve ver dados do projeto 3AM Shelter.
4. Transformar integrações em módulos opcionais, com tela de permissões, teste de conexão, revogação e mensagem de erro compreensível.
5. Adicionar limites de uso, filas, tentativas seguras, prevenção de publicação duplicada e isolamento de falhas.
6. Criar painel operacional de saúde, armazenamento, custos, falhas, publicações e credenciais próximas do vencimento.
7. Definir política de privacidade, termos de uso, retenção/exclusão de dados, tratamento de direitos autorais e conformidade com a LGPD.
8. Fazer análise de segurança, acessibilidade e desempenho antes de aceitar usuários externos.
9. Definir oferta comercial somente depois de medir custo por vídeo, tempo economizado, taxa de falha e suporte necessário.
10. Executar um piloto fechado com poucos usuários, recolher feedback e corrigir bloqueadores antes de qualquer venda pública.

Critério de conclusão: isolamento entre clientes comprovado, segurança e recuperação testadas, documentação legal disponível e piloto fechado operando sem acesso indevido ou publicação duplicada.

Progresso em 07/09/2026: a fronteira entre o Hub pessoal e um futuro produto foi documentada em `commercial-readiness.md`, com sequência para isolamento de espaços, papéis, conectores modulares, cotas, exportação, suporte, revisão profissional e piloto fechado. O checklist reutilizável `release-checklist.md` também foi criado. A arquitetura multiusuário ainda não foi implementada e o FFactory continua corretamente classificado como sistema pessoal em validação.

### Prioridade 8 — lançamento e melhoria contínua

1. Criar checklist de lançamento com responsável, evidência e possibilidade de reversão para cada etapa.
2. Definir indicadores principais: vídeos aprovados, falhas por lote, tempo de produção, custo por vídeo, alcance, retenção e receita líquida.
3. Fazer revisão semanal da operação e revisão mensal de produto; arquivar funcionalidades duplicadas ou sem uso comprovado.
4. Manter testes internos, interface em computador/celular, acessibilidade, integridade dos pacotes e backup como bloqueadores obrigatórios de versão.
5. Publicar um registro de mudanças compreensível e manter versões recuperáveis do banco, configurações e aplicação.
6. Só liberar automações destrutivas ou publicação sem revisão após histórico suficiente, limites de segurança e mecanismo de cancelamento.

Critério de conclusão: operação previsível, mensurável e recuperável, com evolução orientada por uso real e não por acúmulo de funcionalidades.

## Ordem executiva recomendada

1. Segurança: revogar credenciais expostas e testar restauração.
2. YouTube: cumprir quatro semanas de calendário e acumular métricas reais.
3. Verticais: autenticar TikTok e Instagram e executar três pilotos controlados em cada plataforma.
4. Comercial: ativar Pinterest e Shopee com um único produto rastreável.
5. Internacional: revisar e publicar o primeiro piloto manual no Bilibili.
6. Infraestrutura: migrar o Hub somente quando existir opção contínua, segura e financeiramente aceitável.
7. Produto: implementar isolamento multiusuário, segurança, aspectos legais e piloto fechado antes de comercializar.

Nenhuma dependência externa deve ser simulada com dados falsos, integrações não oficiais, reutilização de credenciais expostas ou publicação sem revisão.
