# Roadmap seguro para vídeos de afiliados e Shopee

Esta frente fica separada do pipeline editorial atual até a base de ambientação estar estável.

## Objetivo

Transformar dados de produtos afiliados em vídeos curtos originais, com rastreabilidade de mídia, revisão humana e links de comissão permitidos pela plataforma.

## Regra de mídia

Pinterest terá duas funções diferentes: pesquisa visual de tendências e destino oficial dos vídeos originais produzidos pela fábrica. Ele não será biblioteca automática de vídeos. Um pin de terceiro não comprova que o autor autorizou download, alteração, republicação ou uso comercial.

Fontes aceitas para uma futura automação:

- gravações e demonstrações próprias;
- mídia fornecida pelo vendedor com autorização explícita para afiliados;
- kit oficial da campanha ou da plataforma;
- banco de mídia com licença comercial compatível;
- conteúdo gerado por provedor cujo contrato permita uso comercial;
- domínio público ou CC0 com origem registrada.

## Pipeline proposto

1. Importar produto, preço e link de afiliado por fonte oficial.
2. Registrar cada imagem ou vídeo no catálogo de assets com licença e origem.
3. O agente de conformidade bloqueia assets sem comprovação.
4. Gerar roteiro original baseado em características verificáveis do produto.
5. Montar vídeo 9:16, legenda, aviso de afiliado e thumbnail.
6. Revisar alegações, preço, direitos e regras atuais da plataforma.
7. Publicar manualmente ou por API oficial quando disponível.
8. Registrar cliques, conversões e comissão sem armazenar dados pessoais do comprador.
9. Criar opcionalmente um Video Pin com o nosso vídeo, capa e link rastreável, usando a API oficial do Pinterest depois da autorização da conta.

## Regras oficiais verificadas em 26/08/2026

- Na Shopee Video, o produto precisa ser adicionado diretamente ao vídeo; link na descrição ou comentários não substitui esse vínculo.
- O conteúdo precisa representar o mesmo produto vinculado, sem discrepância que possa induzir a compra errada.
- Conteúdo que gera comissão deve ser identificado claramente como publicidade; o projeto usa `#publicidade` como padrão brasileiro.
- No YouTube integrado à Shopee, o produto deve estar visível ou mencionado e relacionado de forma autêntica ao conteúdo.

Fontes: [adicionar produtos na Shopee Video](https://help.shopee.com.br/portal/10/article/165032), [diretrizes da comunidade](https://help.shopee.com.br/portal/10/article/165433-Diretrizes-da-comunidade-Shopee-Video), [identificação de publicidade](https://help.shopee.com.br/portal/10/article/196794) e [marcação no YouTube](https://help.shopee.com.br/portal/10/article/189593).

O comando `python app.py commerce-check produto.json` agora valida um briefing e bloqueia produto incorreto, ausência de divulgação, alegações sem fonte e mídia sem direitos. A futura saída Pinterest publicará somente mídia criada ou licenciada pela própria operação.

Documentação oficial do destino Pinterest: [criação de Pins e Video Pins](https://developers.pinterest.com/docs/work-with-organic-content-and-users/create-boards-and-pins/) e [métricas orgânicas](https://developers.pinterest.com/docs/analytics-and-reports/organic-reporting/).

## Itens ainda dependentes da conta

- acesso a catálogo/API ou exportação oficial;
- permissão específica para reutilizar mídia de cada vendedor;
- canais e APIs de publicação aceitos.

O módulo futuro deve falhar de forma segura: sem prova de direitos, não renderiza nem publica.
