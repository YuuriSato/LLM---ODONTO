# Perito Visual Local

Analise de integridade de imagens odontologicas, sem diagnostico clinico.

Fluxo de producao: imagem original -> pericia local -> local_evidence.json ->
Gemini Flash Latest -> auditoria no backend -> veredito final.

Vereditos: REAL, IA_GERADA, IA_EDITADA, EDICAO_TRADICIONAL ou INDETERMINADO.
O Codex e ferramenta de desenvolvimento; nao e o classificador de producao.
Ollama, calibracao e testes exclusivamente locais ficam restritos ao modo de
desenvolvimento. O historico legado conserva seus rotulos originais.

## Estrutura

```text
app/                     Aplicacao web e CLI
models/                  Modelfiles do Ollama
data/                    Dataset e JSONL de treino
runtime/                 Historico, uploads, cache e outputs gerados
reports/                 Relatorios CSV/Markdown/JSON
scripts/training/        Scripts de dataset, LoRA e merge
scripts/download/        Scripts auxiliares de download Hugging Face
docs/                    Documentacao complementar
logs/                    Logs antigos de treino/download/web
tests/                   Imagens de teste locais
```

## Como iniciar o web service para teste

Na raiz do projeto:

```powershell
cd C:\Scripts\Ollama_ImageOBS\Chatbot---LLM-RASA
```

Crie e ative o ambiente virtual, caso ainda nao exista:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instale as dependencias:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.lock.txt
```

Use .env.example como referencia e preencha .env, que e ignorado pelo Git:

```env
APP_ENV=production
AI_PROVIDER=gemini
GEMINI_MODEL=gemini-flash-latest
GEMINI_API_KEY=sua-chave-do-gemini
AI_TIMEOUT_SECONDS=90
AI_MAX_OUTPUT_TOKENS=8192
```

AI_PROVIDER tem precedencia sobre LLM_PROVIDER (compatibilidade legada).
Gemini Flash Latest continua como padrao, com Gemini 2.5 Flash no seletor.
Cada analise usa o modelo escolhido: nao ha fallback automatico, nem uso dos antigos
GEMINI_FALLBACK_MODELS. Se houver 404, a analise fica nao_concluida, com as
evidencias preservadas. Listar modelos ou validar a chave nao confirma que a
conta consegue executar esse modelo.

Suba o web service:

```powershell
python .\app\web_alteracao.py
```

Abra no navegador:

```text
http://localhost:9090
```

Se quiser testar em outra porta, altere `WEB_PORT` no `.env` e reinicie o
servidor. Exemplo:

```env
WEB_PORT=8080
```

```text
http://localhost:8080
```

Na tela, envie a imagem a analisar e, se disponivel, uma imagem de referencia.
O pipeline completo roda sempre em producao, independentemente do score ou
da existencia de uma calibracao anterior.

## Arquitetura de integridade

- app/static/: HTML, CSS e JavaScript, separados do servidor.
- app/history_store.py: SQLite e importacao unica do historico JSON legado.
- app/uploads.py: verificacao de formato real, integridade, bytes e pixels.
- app/jobs.py: fila de uma analise por vez, limite de oito trabalhos ativos.
- app/ai/lmstudio_client.py: imagens originais e JSON Schema via LM Studio.
- app/ai/integrity_analyzer.py: validacao e revisao comuns aos dois provedores.

- app/ai/config.py: configuracao centralizada e restricoes de producao.
- app/ai/evidence.py: ELA, FFT, ruido global e por blocos, nitidez, compressao,
  metadados tecnicos, qualidade, sobreposicoes e comparacao opcional.
- app/ai/gemini_client.py: unico acesso ao SDK, imagens originais, schema,
  timeout e limpeza dos arquivos remotos temporarios.
- app/ai/gemini_integrity_analyzer.py e schemas.py: interpretacao multimodal,
  validacao Pydantic estrita e referencias as medicoes locais.
- app/ai/audit.py e pipeline.py: auditoria obrigatoria, revisao condicional e
  persistencia separada das hipoteses inicial, revisada e conclusao final.
- app/ai/detector.py: contrato de detector externo, desativado por padrao.

## Modelos locais e fila

Para LM Studio, configure `APP_ENV=development` e
`LM_STUDIO_HOST=http://127.0.0.1:11345`. Carregue um modelo com visao no servidor
e clique em Atualizar modelos. Modelos de embeddings e modelos sem visao nao
entram no seletor. O resultado local e experimental, mas passa pelo mesmo schema,
verificacao de referencias e auditoria do Gemini. Nao ha reducao da imagem nesse
pipeline. Settings mostra capacidades e a ultima verificacao real, quando existir.

A interface usa `POST /analyze` com `Prefer: respond-async`, consulta
`GET /jobs/<id>` e cancela por `POST /jobs/<id>/cancel`. Clientes antigos podem
aguardar a resposta sincrona; ambos usam a mesma fila. Uma chamada em andamento
ao provedor pode terminar antes do cancelamento; nenhuma revisao nova e iniciada.
Trabalhos interrompidos por reinicio ficam como falha, sem repeticao automatica.
A aba guarda o identificador da analise durante a sessao. Recarregar a pagina
retoma a consulta, sem reenviar a imagem. Em uma falha de conexao, use Retomar
acompanhamento; o cancelamento so e confirmado pela resposta do servidor.

Calibracao tem pagina propria e confirmacao. Imagens reservadas no manifesto de
teste nao podem ser adicionadas a calibracao. Historico permite filtrar por modelo,
comparar os dois arquivos e exportar o JSON completo de novas analises.

## Validacao e avaliacao

```powershell
python -m unittest discover -s tests -p "test_*.py"
python scripts/check_private_files.py
python scripts/provider_check.py --provider gemini --model gemini-flash-latest
python scripts/provider_check.py --provider lmstudio --model medgemma-4b-it
```

Os dois ultimos comandos fazem chamadas reais com uma imagem sintetica sem dados
de pacientes. O teste inclui imagem, schema, referencias e auditoria; nao mede
acuracia clinica. Resultados ficam em `runtime/provider_checks`. Falhas nao aprovam
o modelo. Nao use uma credencial exposta: revogue-a no provedor e atualize `.env`.

`scripts/register_sample.py --help` registra imagens com hash, procedencia,
grupo, rotulo e divisao teste/calibracao. `--verified` e uma atestacao humana da
procedencia, nao uma inferencia baseada na aparencia. Mantenha pares no mesmo grupo.
Sem rotulo comprovado, omita `--verified`; nao invente uma classe REAL.
O manifesto confere o SHA-256 da imagem e da referencia (`reference_sha256`),
rejeita imagens duplicadas e impede compartilhamento entre teste e calibracao.
Registro de amostras e calibracao usam um bloqueio comum entre processos.

```powershell
python scripts/evaluate_integrity.py runtime/datasets/manifest.json --provider gemini --model gemini-flash-latest
```

Sem `--run`, o comando apenas valida o dataset. Com `--run`, executa os testes
reais e grava matriz de confusao, cobertura, abstencoes, falhas tecnicas, FP/FN e
acuracia nas respostas decididas, por modelo e qualidade. Amostras de engenharia
e odontologicas sao reportadas separadamente. Rotulos nao sao enviados ao modelo.
O conjunto atual ainda nao tem tamanho nem diversidade para estimar acuracia.

## Privacidade e retencao

Uploads, historico, cache, datasets e `.env` sao privados e ignorados no Git.
Arquivos ja publicados continuam em commits antigos: retirar do indice nao apaga
o historico remoto. Uma limpeza desse historico exige uma operacao coordenada.
O servidor escuta somente em loopback e rejeita Host/Origin externos; nao e uma
solucao de autenticacao multiusuario e nao deve ser exposto na rede.

O historico e importado sem limite de 100 registros para
`runtime/analysis_history.sqlite3`. O JSON legado nao e reescrito na migracao.
Uploads aceitam ate 15 MiB por arquivo e 24 milhoes de pixels, configuraveis no env.

```powershell
python scripts/retention.py --days 90
```

O comando acima so mostra candidatos. Pare o servidor antes de usar `--apply`:
o bloqueio do processo impede aplicacao enquanto o servico esta aberto. A lista
e recalculada sob bloqueio; arquivos e evidencias usados por registros recentes
ou calibracao sao preservados. O JSON legado so e removido quando ha registros
vencidos e seu conteudo esta integralmente representado no SQLite; divergencias
interrompem a aplicacao antes da exclusao. Links e junctions nao sao seguidos.
Jobs finalizados vencidos tambem sao removidos. Datasets, calibracao,
backups e arquivos orfaos exigem revisao separada. Nenhuma exclusao automatica foi
ativada. Mantenha backups privados com prazo de retencao definido pela operacao.

O workflow `.github/workflows/test.yml` executa testes Python e de navegador sem
chaves reais. `requirements.lock.txt` fixa as dependencias do ambiente Python 3.13.
O checklist integral e suas pendencias ficam em `docs/IMPROVEMENT_CHECKLIST.md`.

JPEG, PNG e WebP sao enviados sem recompressao nem reducao de resolucao. BMP e
convertido para PNG sem perdas, com conversao registrada. Arquivos grandes usam
a API de arquivos do Gemini e sao removidos ao final; falhas de limpeza ficam
registradas. A modalidade TOMOGRAFIA refere-se a imagem 2D enviada; DICOM e
volumes 3D nao sao suportados nesta versao.

FFT usa remocao da media, janela Hann e 16 faixas radiais. Ruido usa residuo
gaussiano e coordenadas na imagem de analise reduzida. Metricas novas sao
descritivas, sem limiares de fraude inventados. Ausencia, falha, metodo nao
aplicavel e detector desativado sao estados distintos, nunca scores iguais a zero.

O schema obriga a separar evidencias visuais e computacionais, citar as medicoes
originais e declarar limitacoes. O backend verifica tipos, enums, confianca
finita, referencias e valores. Permite uma tentativa de correcao de resposta
invalida, sem regex de recuperacao nem preenchimento silencioso.

A auditoria exige suporte visual e medicoes coerentes de pelo menos duas
familias locais distintas para uma conclusao definitiva. ELA e compressao contam
como uma familia; ruido e nitidez como outra. Frequencia e metadados sao apenas
descritivos. Esses criterios sao conservadores e heuristicos, nao validacao
cientifica de um detector de IA.

Conflitos, qualidade insuficiente ou evidencias fracas provocam revisao
multimodal, no maximo uma vez. Se persistirem, o resultado e INDETERMINADO e a
confianca final fica nula; a confianca inicial do modelo permanece registrada.
Nenhuma confianca e apresentada como probabilidade calibrada. Falha de API,
schema ou revisao gera nao_concluida, sem inventar um veredito.

## Evidencias e API

```text
runtime/uploads/
runtime/analysis_cache/<analysis_id>/local_evidence.json
runtime/analysis_cache/<analysis_id>/result.json
runtime/analysis_history.json
runtime/integrity_calibration.json
```

Cada tentativa tem identificador proprio. O arquivo de evidencias e salvo antes
de chamar a IA e o resultado preserva todas as evidencias e respostas recebidas.
A tela mostra um resumo; Settings permite consultar os dados completos.
O historico e paginado, sem descarte automatico aos 100 registros. Os artefatos
completos permanecem nas pastas individuais ate uma retencao explicita.

POST /analyze conserva o formulario multipart com image e original_image
opcional. Retorna schema_version, analysis_id, status, verdict, structured_result
e audit, alem dos campos legados de apresentacao. status=nao_concluida retorna
HTTP 503, verdict=null e error_code. INDETERMINADO e uma analise concluida,
nao uma falha de transporte.

GET /analysis/<analysis_id> recupera o resultado completo. GET /agents informa
a configuracao, sem confundir presenca de chave com disponibilidade comprovada.
A aplicacao continua local e sem autenticacao; nao a exponha publicamente sem
controle de acesso aos uploads, historico e artefatos.

## Desenvolvimento e testes

Com APP_ENV=development, Settings libera teste local e selecao experimental
de provedor. /calibrate retorna 403 em producao, e requisicoes de outro provedor
tambem sao bloqueadas pelo backend. A interface marca resultados experimentais.

```powershell
.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Testes de interface (Node.js necessario, sem inferencia real):

```powershell
npm install --no-save --package-lock=false playwright@1.62.1
npx playwright install chromium
$env:TEST_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
node tests/ui_smoke.cjs
```

O teste abre um servidor temporario com dados sinteticos, encerra-o ao terminar
e nao modifica seu historico. Cobre cinco larguras, comparacao, download JSON,
seletor indisponivel, retomada sem reenvio e cancelamento. Para uma verificacao
somente de leitura com pares existentes no servico local, execute
`node tests/ui_live_history.cjs`; esse teste exige um par salvo e um resultado
exportavel. Screenshots ficam em `logs/`, fora do Git.

Antes de considerar a operacao pronta, teste uma geracao multimodal real com
JSON Schema usando gemini-flash-latest. Esse alias e o modelo de producao;
a versao retornada pelo provedor e registrada em cada chamada para rastreabilidade.
Nao ha troca automatica para outro modelo se a chamada falhar.

## Ollama

Ferramenta experimental, fora do pipeline de producao.

Baixar modelo base:

```powershell
$env:OLLAMA_HOST = "127.0.0.1:11435"
ollama pull medgemma1.5:4b
```

Criar/recriar persona:

```powershell
$env:OLLAMA_HOST = "127.0.0.1:11435"
ollama create codex-dental -f .\models\Modelfile-Codex-Dental
```

## CLI

Fluxo legado experimental, fora da classificacao de integridade de producao.

```powershell
.\.venv\Scripts\python.exe .\app\perito_flow.py .\tests\test_dental.png --json
```

## Parecer tecnico (Modo Plan)

O script `scripts/codex_plan_mode.py` transforma evidencias locais em um parecer
experimental via Ollama, fora do pipeline de producao,
em portugues, com paragrafos curtos e sem diagnostico odontologico. Ele recebe
somente JSON: nao analisa a imagem novamente. Esta funcao e executada pelo
terminal e nao adiciona uma pagina na interface web.

Com o Ollama em execucao e o modelo instalado, confira `OLLAMA_HOST` e
`VISION_MODEL` no `.env`. Sao aceitos hosts com ou sem `http://`.

Use um arquivo JSON existente com um objeto de evidencias (qualidade, score,
ELA, ruido, nitidez ou comparacao com original). O caminho abaixo e um exemplo;
substitua pelo arquivo que deseja usar, pois ele nao e criado pelo comando:

```powershell
.\.venv\Scripts\python.exe .\scripts\codex_plan_mode.py --input-json .\runtime\analysis_cache\local_evidence.json --output-txt .\reports\codex_parecer.txt --output-json .\reports\codex_parecer.json
```

As pastas de saida sao criadas automaticamente. `--output-json` e opcional e
`--model nome-do-modelo` substitui o modelo configurado. O TXT preserva o parecer
completo, incluindo a linha final `VEREDITO_PLAN`. O JSON contem `parecer_texto`
e `resumo_extraido` (veredito, confianca de 0 a 1 e recomendacao).

Se o modelo retornar um resumo invalido, o texto e preservado para revisao,
`resumo_extraido` fica `null` e o comando termina com codigo 1 e um aviso.
O parecer gerado requer revisao humana; sua confianca e declarada pelo modelo.

## Comparacao de Raios-X por Paciente

O script abaixo compara exames odontologicos de atendimentos diferentes e estima
se parecem pertencer ao mesmo paciente. Ele nao emite diagnostico odontologico.

Manifest CSV aceito:

```csv
image_path,patient_name,dentist,appointment_date,appointment_id
.\runtime\uploads\exame_01.jpg,Paciente A,Dentista Y,2026-06-01,1
.\runtime\uploads\exame_02.jpg,Paciente A,Dentista X,2026-07-01,2
```

Tambem sao aceitos cabecalhos em portugues como `caminho_arquivo`,
`nome_paciente`, `dentista`, `data_atendimento` e `numero_atendimento`.

Executar com manifest:

```powershell
.\.venv\Scripts\python.exe .\scripts\compare_dental_xrays.py --manifest .\data\xrays_manifest.csv --output .\reports\xray_patient_comparison.csv --excel .\reports\xray_patient_comparison.xlsx
```

Executar direto com uma pasta de imagens:

```powershell
.\.venv\Scripts\python.exe .\scripts\compare_dental_xrays.py --image-dir .\tests --output .\reports\xray_patient_comparison.csv
```

## Dataset

Estrutura esperada:

```text
data/dataset_dental/
  real/
  alterada_manualmente/
  alterada_digitalmente/
  ia/
  indeterminado/
```

Gerar JSONL:

```powershell
.\.venv\Scripts\python.exe .\scripts\training\prepare_training_jsonl.py
```

O arquivo padrao gerado fica em:

```text
data/codex_training.jsonl
```

## Fine-Tuning

O fine-tuning do MedGemma 4B em CPU nao foi viavel nesta maquina. Para GPU/Colab, veja:

```text
docs/FINE_TUNING.md
```
