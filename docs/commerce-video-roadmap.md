# Roadmap seguro para vídeos de afiliados e Shopee

Esta frente fica separada do pipeline editorial atual até a base de ambientação estar estável.

## Objetivo

Transformar dados de produtos afiliados em vídeos curtos originais, com rastreabilidade de mídia, revisão humana e links de comissão permitidos pela plataforma.

## Regra de mídia

Pinterest pode ser usado para pesquisa visual e identificação de tendências, mas não como biblioteca automática de vídeos. Um pin não comprova que o autor autorizou download, alteração, republicação ou uso comercial.

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

## Itens a verificar antes da implementação

- termos atuais do programa de afiliados da Shopee para o país da conta;
- acesso a catálogo/API ou exportação oficial;
- regras de divulgação de publicidade e comissão;
- permissão específica para reutilizar mídia de cada vendedor;
- canais e APIs de publicação aceitos.

O módulo futuro deve falhar de forma segura: sem prova de direitos, não renderiza nem publica.
