# Checklist de liberação

Use este checklist em toda versão do Hub e em todo novo conector. Cada item precisa de evidência; “parece funcionar” não é aprovação.

## Aplicação

- [ ] Testes internos aprovados.
- [ ] Testes de interface em computador e celular aprovados.
- [ ] Nenhuma violação séria de acessibilidade.
- [ ] Nenhuma rolagem horizontal involuntária.
- [ ] Diagnóstico de FFmpeg, FFprobe, armazenamento e modo seguro aprovado.
- [ ] Auditoria de segurança sem segredo versionado.
- [ ] Backup criado e restauração isolada aprovada.

## Conteúdo

- [ ] Música ouvida, aprovada, licenciada e diferente das faixas recentes.
- [ ] Imagem pertence à coleção aprovada e possui origem registrada.
- [ ] Thumbnail e primeiro quadro após o play representam a mesma cena.
- [ ] Vídeo final possui 1920×1080, H.264, 30 fps, `yuv420p` e áudio AAC.
- [ ] Início, meio e fim decodificam corretamente.
- [ ] Título público está em inglês natural e corresponde à cena.
- [ ] Descrição, hashtags, duração e visibilidade foram revisadas.

## Plataforma

- [ ] Conta e aplicativo oficiais.
- [ ] OAuth válido com o menor conjunto de permissões possível.
- [ ] Pré-teste passou sem contato de rede ou alteração de publicação.
- [ ] Identificador externo e comprovante da operação foram registrados.
- [ ] Proteção contra duplicação está ativa.
- [ ] Primeiro piloto exige confirmação humana.

## Reversão

- [ ] Versão anterior identificada.
- [ ] Backup anterior disponível.
- [ ] Procedimento para pausar fila e publicações conhecido.
- [ ] Responsável pela decisão de reversão definido.
- [ ] Resultado da reversão pode ser verificado sem apagar evidências.

## Liberação

Versão: ______  Data: ______  Responsável: ______

Evidências: ______

Decisão: [ ] liberar  [ ] corrigir  [ ] reverter
