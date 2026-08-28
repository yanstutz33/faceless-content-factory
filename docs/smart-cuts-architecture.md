# Arquitetura futura — cortes inteligentes

Este módulo está deliberadamente marcado como `planned`: o Studio 2.0 prepara os dados que ele usará, mas não cria cortes automáticos ainda.

## Entrada segura

- somente um vídeo já renderizado e aprovado;
- DNA criativo e pacote de metadados do trabalho;
- capítulos, roteiro e legendas quando disponíveis;
- retenção e desempenho quando a plataforma autorizada fornecer esses sinais.

## Processo previsto

1. detectar limites semânticos, silêncios, mudanças de energia e batidas;
2. ranquear trechos por clareza isolada e retenção provável;
3. gerar enquadramento 9:16 sem sobrescrever o vídeo original;
4. produzir legendas, capa e metadados específicos por plataforma;
5. executar quality gate e enviar o pacote à aprovação manual.

## Contrato do módulo

A entrada será um manifesto imutável do vídeo aprovado. A saída ficará em uma pasta separada, com timestamps de origem, SHA-256, motivo de seleção e direitos herdados. Nenhuma publicação ocorrerá como efeito colateral da criação dos cortes.

O objetivo é reutilizar a mesma memória criativa do Studio: evitar múltiplos cortes quase idênticos, aprender com taxa de conclusão e compartilhamentos e manter estratégias diferentes para Shorts, TikTok e Reels.
