# Roadmap consolidado

O projeto terá duas linhas independentes que compartilham agentes, assets, renderização, fila, aprovação e métricas. Nenhuma fase futura habilita publicação automática por padrão.

### Confiabilidade operacional — Studio 1.7

- uma produção só pode ser reservada por um worker/processo de cada vez;
- a renderização escreve em arquivo temporário e só substitui o vídeo final depois da validação;
- início, meio e fim do vídeo são decodificados quando o FFprobe não está disponível;
- aprovação e reaproveitamento conferem novamente o checksum SHA-256 do vídeo.

## Linha editorial

### Entregue — fábrica de ambientação

- vídeos longos e verticais;
- cenas originais, música lo-fi e efeitos localizados;
- agentes, calendário, piloto automático e operação noturna;
- quality gate, aprovação, pacotes YouTube/Shorts/Reels/TikTok e métricas;
- conectores preparados até o ponto anterior ao login.

### Entregue — escala criativa (Studio 2.0)

- 48 candidatos avaliados por produção e 25.600 combinações-base por cena;
- detector histórico de repetição para imagem, composição, movimento e som;
- oito tratamentos visuais, cinco enquadramentos e 16 movimentos localizados com câmera fixa;
- oito arranjos lo-fi, quatro progressões, camadas de baixo/melodia e cinco texturas;
- aprendizado conservador por retenção, CTR e engajamento: métricas pesam 20% e novidade pesa 80%;
- painel de originalidade e rastreabilidade completa no DNA criativo.

### Planejada — cortes inteligentes

- reutilizar apenas vídeos já aprovados, sem alterar o original;
- combinar capítulos, batidas, legendas e sinais de retenção;
- produzir candidatos 9:16 diferentes para Shorts, TikTok e Reels;
- executar quality gate e manter aprovação manual antes de qualquer entrega.

Contrato técnico: [smart-cuts-architecture.md](smart-cuts-architecture.md).

### Próxima — contas oficiais atuais

- concluir manualmente OAuth de YouTube, TikTok e Instagram;
- ativar coleta oficial de métricas;
- manter confirmação humana antes de cada publicação durante o período de validação.

### Entregue — pacote Bilibili manual

1. Perfil de destino e fluxo manual seguro — concluído no Studio 1.8.
2. Títulos, descrições, capa neutra e legendas em inglês e chinês simplificado — concluído.
3. Classificação conservadora por cena e intenção, sem tradução literal cega — concluído.
4. Pacote `bilibili-upload.json` para revisão e upload manual — concluído.
5. Registro de métricas Bilibili no histórico editorial — concluído.
6. Primeiro login, categoria e validação cultural final — etapa manual.
7. Automação de upload somente se houver acesso oficial estável, autorizado e testado.

Referência: [Bilibili Studio para criadores](https://member.bilibili.com/creator/home).

## Linha comercial

### Entregue — base segura Shopee

- validação de produto exato, mídia licenciada, alegações e `#publicidade`;
- pacote vertical comercial sem upload;
- bloqueio explícito de mídia de terceiros obtida no Pinterest.

### Entregue — central de campanhas

1. Campanhas comerciais separadas das séries editoriais.
2. Produto e link de afiliado importados por formulário revisável e validação oficial de domínio.
3. Produto exato, direitos, divulgação e alegações verificados antes da campanha.
4. Criativo associado ao produto e à produção aprovada para gerar o pacote manual.
5. Cliques, conversões, comissão, custo, lucro e ROI persistidos por campanha.

### Em andamento — Shopee + Pinterest

1. Reutilizar o vídeo comercial original em formato Video Pin — concluído no Studio 1.6.
2. Registrar app Pinterest e OAuth da conta Business.
3. Gerar payload local com board, vídeo, capa e texto alternativo — concluído no Studio 1.6.
4. Publicar em boards comerciais usando somente a API oficial após login.
5. Conectar o Pin ao link rastreável permitido e registrar a origem da campanha.
6. Coletar métricas orgânicas e comparar Pinterest, Shopee Video e formatos verticais.
7. Nunca baixar ou republicar automaticamente vídeos de outros Pins.

Referências: [Pinterest Content API](https://developers.pinterest.com/docs/work-with-organic-content-and-users/create-boards-and-pins/) e [Pinterest Organic Analytics](https://developers.pinterest.com/docs/analytics-and-reports/organic-reporting/).

## Ordem aprovada

1. Escala criativa, detector de repetição e aprendizado conservador — concluídos no Studio 2.0.
2. Concluir logins das plataformas que já estão preparadas.
3. Central comercial e catálogo Shopee — concluídos no Studio 1.5.
4. Pacote Pinterest para mídia própria — concluído no Studio 1.6; login oficial pendente.
5. Adicionar o pacote manual localizado para Bilibili — concluído no Studio 1.8.
6. Implementar cortes inteligentes depois que houver vídeos aprovados e sinais suficientes para avaliação.
7. Automatizar publicações individualmente somente após testes, aprovação das APIs e confirmação humana.
