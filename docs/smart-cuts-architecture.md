# Cortes inteligentes — implementação local

O módulo `smart_cuts_v1` está disponível para vídeos aprovados. Ele cria três candidatos locais de 15, 30 e 60 segundos em 1080×1920, sem alterar o vídeo longo e sem publicar.

## Entrada segura

- somente um vídeo já renderizado e aprovado;
- DNA criativo e pacote de metadados do trabalho;
- capítulos, roteiro e legendas quando disponíveis;
- retenção e desempenho quando a plataforma autorizada fornecer esses sinais.

## Processo implementado

1. usar capítulos auditáveis como limites semânticos e incorporar sinais de retenção quando existirem;
2. ranquear abertura e mudanças de capítulo, mantendo o motivo da escolha no pacote;
3. gerar enquadramento 9:16 com a cena integral sobre fundo desfocado, sem sobrescrever o original;
4. produzir legendas, capa e metadados específicos por plataforma;
5. executar quality gate e enviar o pacote à aprovação manual.

## Contrato do módulo

A entrada será um manifesto imutável do vídeo aprovado. A saída ficará em uma pasta separada, com timestamps de origem, SHA-256, motivo de seleção e direitos herdados. Nenhuma publicação ocorrerá como efeito colateral da criação dos cortes.

Cada candidato contém início e fim no original, SHA-256 da fonte, relatório técnico, enquadramento seguro e textos separados para Shorts, TikTok e Reels. A aprovação e a publicação continuam manuais.
