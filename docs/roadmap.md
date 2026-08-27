# Roadmap consolidado

O projeto terá duas linhas independentes que compartilham agentes, assets, renderização, fila, aprovação e métricas. Nenhuma fase futura habilita publicação automática por padrão.

## Linha editorial

### Entregue — fábrica de ambientação

- vídeos longos e verticais;
- cenas originais, música lo-fi e efeitos localizados;
- agentes, calendário, piloto automático e operação noturna;
- quality gate, aprovação, pacotes YouTube/Shorts/Reels/TikTok e métricas;
- conectores preparados até o ponto anterior ao login.

### Próxima — contas oficiais atuais

- concluir manualmente OAuth de YouTube, TikTok e Instagram;
- ativar coleta oficial de métricas;
- manter confirmação humana antes de cada publicação durante o período de validação.

### Futura — Bilibili

1. Criar o perfil de destino e presets técnicos.
2. Gerar títulos, descrições, capas e legendas em inglês e chinês simplificado.
3. Adicionar validação cultural e terminológica, sem tradução literal cega.
4. Produzir um pacote `bilibili-upload.json` para revisão e upload manual.
5. Registrar métricas separadas por idioma e série.
6. Avaliar automação somente por acesso oficial estável e autorizado.

Referência: [Bilibili Studio para criadores](https://member.bilibili.com/creator/home).

## Linha comercial

### Entregue — base segura Shopee

- validação de produto exato, mídia licenciada, alegações e `#publicidade`;
- pacote vertical comercial sem upload;
- bloqueio explícito de mídia de terceiros obtida no Pinterest.

### Próxima — central de campanhas

1. Separar campanhas comerciais das séries editoriais.
2. Importar produto e link de afiliado por fonte oficial ou formulário revisável.
3. Gerar roteiro, vídeo, capa, legenda e variações de CTA.
4. Associar cada criativo ao produto exato e registrar validade de preço/oferta.
5. Medir cliques, conversões, comissão, custo e retorno por campanha.

### Futura — Shopee + Pinterest

1. Reutilizar o vídeo comercial original em formato Video Pin.
2. Registrar app Pinterest e OAuth da conta Business.
3. Publicar em boards comerciais usando somente a API oficial.
4. Conectar o Pin ao link rastreável permitido e registrar a origem da campanha.
5. Coletar métricas orgânicas e comparar Pinterest, Shopee Video e formatos verticais.
6. Nunca baixar ou republicar automaticamente vídeos de outros Pins.

Referências: [Pinterest Content API](https://developers.pinterest.com/docs/work-with-organic-content-and-users/create-boards-and-pins/) e [Pinterest Organic Analytics](https://developers.pinterest.com/docs/analytics-and-reports/organic-reporting/).

## Ordem aprovada

1. Concluir logins das plataformas que já estão preparadas.
2. Construir a central comercial e o catálogo Shopee.
3. Adicionar Pinterest como destino de mídia própria.
4. Adicionar o pacote manual localizado para Bilibili.
5. Automatizar publicações individualmente somente após testes, aprovação das APIs e confirmação humana.
