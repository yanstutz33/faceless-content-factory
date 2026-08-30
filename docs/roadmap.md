# Roadmap executivo — Faceless Content Factory

Última revisão: 29/08/2026. O roadmap separa o que já foi validado localmente, o que a fábrica pode automatizar sem contas externas e o que depende de login ou decisão humana. Publicação automática continua desativada por padrão.

## Estado atual verificável

### Base operacional concluída

- pipeline Python com fila, reserva exclusiva de trabalho, renderização atômica e validação de integridade;
- vídeos longos públicos limitados a 30 ou 60 minutos, com bloqueio de artefatos menores;
- biblioteca de músicas próprias/licenciadas, ingestão local, catálogo, checksums e rastreabilidade de direitos;
- composição com câmera fixa, movimentos localizados e tratamento de imagem sem tremor artificial;
- agentes de planejamento, criação, áudio, montagem, qualidade, aprovação e empacotamento;
- detector histórico de repetição e DNA criativo para imagem, composição, movimento e som;
- quality gate, aprovação manual, pacotes de publicação e registro local de métricas;
- Hub responsivo com navegação direta, acessibilidade automatizada, feedback de erro e tema editorial;
- conectores preparados somente até o ponto anterior à autenticação das plataformas.

### Limites atuais

- variedade real de áudio depende de uma biblioteca com faixas diferentes e direitos documentados;
- a fábrica não deve prometer diversidade visual antes de ampliar e validar o catálogo de cenas;
- YouTube, TikTok, Instagram, Pinterest, Shopee e Bilibili ainda exigem login/configuração manual;
- nenhuma plataforma recebe upload automático antes de um piloto privado aprovado.

## Próximas fases, em ordem

### Fase 1 — Catálogo criativo de produção — em revisão musical

Objetivo: eliminar a repetição perceptível antes de aumentar o volume.

- gerar ou importar e validar pelo menos 12 faixas lo-fi/chill diferentes, com licença e atribuição quando exigida — **em validação auditiva: 12 faixas do Flow Music estão ativas, a coleção sintética foi arquivada e cada faixa agora pode ser aprovada ou reprovada diretamente no hub**;
- ampliar para pelo menos 12 cenas-base originais, com zonas de movimento coerentes — **concluído: 12 cenas-base disponíveis**;
- criar combinações por intenção: foco, leitura, sono, madrugada, melancolia e relaxamento;
- impedir repetição recente de faixa, cena, paleta, enquadramento e arranjo;
- gerar 10 vídeos longos de validação e aprovar apenas os que passarem no controle técnico e criativo — **a validação técnica passou, mas o lote musical precisa ser refeito com as novas faixas**;
- manter capas 16:9 no padrão cinematográfico noturno aprovado — **concluído: nove referências únicas em `nocturnal_rain_v1`, incluindo uma nova cena original gerada pela fábrica, sem banners, títulos longos ou câmera artificial**;
- migrar capas históricas para o padrão aprovado com backup recuperável — **implementado; disponível no hub e na linha de comando**;
- preparar geração musical externa sem tornar a montagem dependente de uma plataforma — **implementado: Flow Music Bridge com abertura oficial protegida pelo Google, importação rastreável do lote Starter, substituição reversível do catálogo sintético, integração opcional com Lyria 3 pela Gemini API e montagem local automática**.

Resultado parcial: vídeos, duração, câmera e integridade técnica foram validados; as capas aprovadas já estão visíveis na Biblioteca e são escolhidas por tema. O lote de 12 músicas do Flow Music Starter foi importado e a aprovação auditiva faixa a faixa continua obrigatória. O primeiro piloto com a faixa nova `3 A.M. Shadow` foi renderizado por 30 minutos com qualidade técnica 100/100 e aguarda revisão. O kit visual FFACTORY para YouTube também está pronto. Nenhum vídeo foi publicado externamente.

Critério de conclusão: 10 de 10 vídeos com duração válida, áudio distinto no lote, imagem coerente, sem chuva dentro de ambientes, sem tremor de câmera e com manifesto de direitos completo.

Automação: geração, validação, registro, rotação e montagem estão automatizados. Permanecem humanos apenas a criação/colagem inicial da chave, a aceitação dos termos/custos e a aprovação auditiva do lote.

### Fase 2 — Piloto automático sem publicação — próxima

Objetivo: provar que a fábrica consegue trabalhar sozinha de ponta a ponta.

- gerar pauta, roteiro leve/metadados, composição, thumbnail e pacote de publicação em lote;
- executar renderização noturna com retomada segura após falha;
- priorizar automaticamente ideias com maior novidade e menor risco de repetição;
- criar um relatório diário simples: concluídos, bloqueados, motivo e ação recomendada;
- manter todos os resultados na fila de aprovação local.

Critério de conclusão: três lotes consecutivos terminam sem intervenção e sem artefatos inválidos.

Automação: completa, sem publicar externamente.

### Fase 3 — YouTube privado e métricas reais

Objetivo: validar o canal principal com risco mínimo.

- configurar projeto OAuth e conectar a conta oficial do YouTube;
- enviar inicialmente como privado ou não listado;
- confirmar título, descrição, thumbnail, duração, áudio e processamento da plataforma;
- importar impressões, CTR, retenção e tempo de exibição;
- manter confirmação humana antes de tornar um vídeo público durante o piloto.

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
3. faixa e cena não repetem a janela configurada;
4. imagem, movimento e efeitos respeitam a lógica física da cena;
5. música e imagens possuem origem e direitos registrados;
6. título, descrição, thumbnail e arquivo final pertencem à mesma produção;
7. testes automatizados e CI estão verdes;
8. publicação permanece manual até o piloto específico da plataforma ser aprovado.

## Próxima ação recomendada

Ouvir e decidir as 12 faixas pelo hub, revisar o primeiro piloto `Observatório lunar abandonado` e substituir qualquer faixa reprovada. Com a diversidade musical aprovada, renderizar os nove pilotos restantes e executar os três lotes automáticos da Fase 2. Somente depois disso iniciar o piloto privado do YouTube.
