# Controles operacionais locais

O módulo `factory/operational_controls.py` concentra controles baratos que
podem ser integrados por workers futuros sem alterar o fluxo de métricas ou
conceder acesso de publicação:

- `UsageLedger` limita operações ativas, tamanho da fila, tentativas e uma
  sincronização de métricas por dia. O contador usa SQLite transacional para
  continuar atômico quando workspaces rodam em processos separados.
- `CrossWorkspaceClaims` registra uma reserva global por plataforma e payload.
  Dois workspaces não podem reivindicar o mesmo conteúdo; a repetição do mesmo
  job é idempotente. O ledger não contém tokens.
- `operational_health` resume fila, falhas, claims, sinais de custo e validade
  das credenciais sem devolver valores secretos.

O Hub instancia esses controles no banco global privado, aplica-os ao worker,
à sincronização de métricas e ao envio privado, e expõe somente o resumo
redigido em `/api/operations/health` e no dashboard.

## Rotina segura

1. Antes de iniciar um worker, reserve a operação; ao iniciar, marque-a como
   ativa; registre cada tentativa; finalize como `completed`, `failed` ou
   `cancelled`.
2. Gere o `payload_key` a partir do hash do pacote final, incluindo a versão
   do vídeo, e faça a claim antes de preparar qualquer entrega externa.
3. Continue usando `youtube-sync-metrics` como único sincronizador oficial.
   O `UsageLedger` deve apenas admitir ou recusar a execução; ele não consulta
   a API e não cria uma segunda automação.
4. Execute `backup` e `backup-restore-test` em cópia isolada, depois rode
   `security-audit`. Nunca copie tokens para relatórios ou backups manuais.
5. Interprete `expiring_soon` como alerta operacional e `expired` como bloqueio
   de integração; o relatório contém somente plataforma, estado e data.

Se o Google devolver `invalid_grant` ao renovar o YouTube, o conector marca
`reauthorization_required` no cofre e apresenta login necessário no Hub.
Não repete a renovação rejeitada nem expõe o corpo da resposta. Reconecte
em **Conexões**; uma nova autorização substitui a marcação. O histórico e
os vínculos de vídeos continuam preservados.

Os testes em `tests/test_operational_controls.py` simulam dois workspaces
tentando publicar o mesmo payload e confirmam que a segunda reivindicação é
rejeitada antes de qualquer credencial ou rede.
