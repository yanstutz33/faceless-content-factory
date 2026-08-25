# Faceless Content Factory — Studio MVP 0.2

Uma fábrica local e automatizada para transformar um tema em um pacote de vídeo de ambientação: roteiro, metadados, paisagem sonora, imagem, vídeo MP4, thumbnail, legenda e checklist de publicação. O MVP não envia nada para plataformas; a fila termina em aprovação para upload manual.

## O que já funciona

- Tema digitado, sugerido pelos agentes ou recebido pela linha de comando
- Sete agentes locais: pesquisa, estratégia, roteiro, direção, SEO, conformidade e crítica
- Roteiro, título, descrição, tags, capítulos, direção visual/sonora e score de qualidade
- Assets visuais e sonoros originais gerados localmente
- Ingestão opcional de JPG/PNG/WebP próprio com enquadramento automático
- Perfis YouTube longo (16:9), vertical (9:16) e prévia rápida
- Renderização H.264/AAC com FFmpeg
- Legenda SRT opcional e thumbnail JPG
- Fila assíncrona persistente em SQLite: a interface não fica bloqueada durante a renderização
- Progresso, prioridade, histórico, revisão, aprovação/rejeição, repetição e métricas
- Quatro templates de séries, geração em lote e calendário editorial
- Painel responsivo para desktop e celular, sem Node e sem build
- Pacote isolado por vídeo em `data/jobs/<id>/`

Narração é opcional. `--narration` usa voz neural em português e requer internet durante essa etapa; sem a opção, tudo funciona offline com a paisagem sonora. Outro provedor de TTS pode ser conectado depois sem alterar a fila ou o renderizador.

## Início rápido (Windows / PowerShell)

Requisitos: Python 3.11+ e FFmpeg. Este pacote já contém uma instalação portátil em `.tools/ffmpeg/bin`. Instale a dependência opcional de voz com `python -m pip install -r requirements.txt`.

```powershell
Copy-Item .env.example .env
python app.py serve
```

Abra `http://127.0.0.1:8787`, clique em **Nova produção** e escolha o formato. Para usar a linha de comando:

```powershell
python app.py generate --topic "Biblioteca chuvosa à noite" --duration 3600 --profile youtube_long
python app.py generate --topic "Cabana na neve" --duration 45 --profile vertical_short --narration
python app.py generate --topic "Café ao amanhecer" --duration 12 --profile preview --asset "C:\Assets\cafe.jpg"
```

O tempo e o espaço de renderização crescem com a duração. Faça uma prévia antes de iniciar vídeos de várias horas.

## Como os agentes trabalham

Cada produção salva `agents.json` com entregas auditáveis:

1. **Radar** identifica público, intenção e palavras-chave.
2. **Norte** define promessa, objetivo de retenção e cadência.
3. **Roteirista** prepara introdução, texto falado e capítulos.
4. **Direção** define paleta, movimento, som e briefing de asset.
5. **Descoberta** cria título, descrição e tags.
6. **Guardião** verifica direitos, riscos e modo de publicação.
7. **Crítica** gera score, alertas e próxima ação.

Hoje eles funcionam localmente com regras reproduzíveis. As interfaces estão separadas para permitir substituir um agente por LLM ou outro provedor sem reescrever fila e renderização.

## Séries, lotes e calendário

- **Lugares sob chuva**, **Mundos acolhedores**, **Foco cósmico** e **Momentos verticais** vêm prontos como pontos de partida.
- **Gerar lote** aceita até 20 temas e coloca tudo em uma fila serial para preservar a responsividade do computador.
- O calendário guarda tema, formato, duração e data. Um item planejado pode ser iniciado imediatamente sem redigitação.
- Os templates ficam em `factory/templates.py` e podem ser adaptados sem alterar o pipeline.

## Operação de baixo esforço

1. Escolha uma oportunidade sugerida ou informe tema, perfil e duração.
2. Continue usando o painel enquanto a fila renderiza em segundo plano.
3. Abra a produção, assista à prévia e confira direção, score e metadados.
4. Aprove ou peça ajustes; falhas e revisões podem ser executadas novamente.
5. Faça o upload manual pelo YouTube Studio enquanto a API não estiver configurada.
6. Registre resultados para formar histórico de aprendizado:

```powershell
python app.py metrics ID_DO_TRABALHO --views 1200 --likes 84 --watch-minutes 530
```

## Estrutura

```text
app.py                 comandos e inicialização
factory/config.py      ambiente e modo seguro
factory/agents.py      equipe digital, perfis e sugestões
factory/pipeline.py    planejamento, assets e renderização
factory/store.py       fila, eventos e métricas SQLite
factory/web.py         API e servidor local
web/                   painel operacional
tests/                 agentes, banco, API e renderização real
data/jobs/             pacotes gerados (ignorado pelo Git)
```

## Assets próprios

O fluxo gera placeholders originais por padrão. Em **Opções avançadas**, informe o caminho de uma imagem licenciada; ela será enquadrada automaticamente. O pacote registra o briefing e alerta para confirmar direitos. Não reutilize vídeos de outros canais sem permissão.

## Testes

```powershell
python -m unittest discover -s tests -v
```

A suíte cobre agentes, validação, migração/estado da fila, API e uma renderização real de 5 segundos com FFmpeg. A interface também foi validada em desktop e viewport móvel.

## Próximas etapas

1. Catálogo de assets licenciados com manifesto de origem e múltiplas cenas por vídeo.
2. Conector opcional de LLM para enriquecer Radar/Roteirista, mantendo o modo local como fallback.
3. Thumbnails com composição e tipografia específicas por série.
4. Templates de séries, geração em lote e calendário editorial.
5. Integração oficial com YouTube Data API, primeiro em modo privado e sempre com confirmação humana.
6. Coleta automática de retenção e priorização de temas com base no histórico.

`ALLOW_PLATFORM_PUBLISH=false` é o padrão. Alterar essa variável sozinho não publica: um conector oficial ainda precisa ser implementado e testado.
