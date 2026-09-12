# Fundação de isolamento por espaço

Esta etapa introduz uma fronteira física opt-in para preparar o FFactory para um futuro piloto com clientes sem alterar a operação pessoal já validada.

## Garantias implementadas

- `3am-shelter` é o espaço reservado e continua usando o diretório `data/`, o banco `data/factory.db` e todos os caminhos atuais.
- Cada novo espaço recebe uma raiz exclusiva em `data/workspaces/<id>/`.
- Banco SQLite, vídeos, biblioteca, backups, relatórios, fila de entregas, auditoria e cofre criptografado passam a ser derivados da raiz selecionada.
- O identificador aceita somente letras minúsculas, números e hífens; caminhos, barras e travessia de diretório são recusados antes de qualquer acesso ao disco.
- Consultar um espaço desconhecido não cria arquivos. O provisionamento precisa ser explícito.
- Duas bases podem conter o mesmo identificador de produção sem ler ou sobrescrever uma à outra, porque nunca compartilham a conexão nem a raiz de arquivos.
- `data/workspaces/` é ignorado pelo Git e pelo contexto da imagem Docker.

## Operação

Criar e listar espaços não acessa contas externas e não publica conteúdo:

```powershell
python app.py workspace-create client-alpha --name "Cliente Alpha"
python app.py workspace-list
```

Para iniciar qualquer comando ou um Hub preso a um espaço específico, informe a opção global antes do comando:

```powershell
python app.py --workspace client-alpha list
python app.py --workspace client-alpha serve
```

Sem `--workspace`, o comportamento continua sendo o da instalação pessoal `3am-shelter`.

## Limite deliberado

Contas individuais, papéis admin/editor/reviewer, validação de workspace por sessão, recuperação de uso único, auditoria por usuário/workspace e exportação/demo/exclusão estão implementados localmente. Ative login somente depois de criar o administrador com `python app.py --workspace client-alpha auth-bootstrap --username owner`, usando `FACTORY_LOCAL_AUTH=true`. Cada espaço continua exigindo uma instância separada. Revisão profissional, piloto externo e infraestrutura contínua permanecem necessários antes de comercializar.

Os comandos `workspace-status`, `workspace-export`, `workspace-demo-seed`, `workspace-demo-reset` e `workspace-delete-plan` usam o workspace global selecionado. `workspace-delete` exige `--username` e `--confirmation DELETE:<id>`, além de senha atual. Exportações excluem credenciais; backups de exclusão são privados e recuperáveis. Essas operações nunca atingem `3am-shelter`.
