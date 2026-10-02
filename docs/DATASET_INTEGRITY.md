# Base de integridade

A base atual fica em `runtime/datasets/manifest.json`, fora do Git. Cada imagem
tem hash, procedencia, grupo de origem, particao e estado de verificacao do rotulo.
Importar uma foto clinica nao confirma que ela seja REAL. As imagens importadas
ficam com `ground_truth: null` e `verified: false` ate revisao de procedencia.

## Importacao

AlphaDent: uma foto por paciente, revisao fixa do arquivo oficial e selecao
reproduzivel. O script verifica a licenca no repositorio de origem. Os bytes sao
preservados; ZIP CRC e SHA-256 local sao registrados. O hash publicado do ZIP
completo nao e verificado porque apenas os trechos selecionados sao baixados.

```powershell
.\.venv\Scripts\python.exe scripts/import_alphadent.py --count 100 --list-only
.\.venv\Scripts\python.exe scripts/import_alphadent.py --count 100
```

Hanoi: consulta de metadados por padrao; `--download` transfere o arquivo de
6,55 GB, retomando o `.part` existente e verificando o SHA-256 final.

```powershell
.\.venv\Scripts\python.exe scripts/download_hanoi.py
.\.venv\Scripts\python.exe scripts/download_hanoi.py --download
```

Os dois scripts salvam origem, versao e licenca em `sources/`. Nenhum realiza
inferencia, envio de fotos a provedores, treinamento ou rotulacao automatica.

## Calibracao e teste

- Variantes e referencias do mesmo grupo permanecem na mesma particao.
- `calibration` reserva uma amostra para desenvolvimento; nao a inclui
  automaticamente nos exemplos aprendidos pela aplicacao.
- A pagina Calibracao registra um rotulo fornecido pelo operador e descritores
  locais, somente em desenvolvimento. Nao altera os pesos do Gemini ou MedGemma.
- Uma referencia nao recebe REAL automaticamente. Seu rotulo pode ser desconhecido
  ou ate IA; rotulos existentes permanecem intactos.
- Imagens e referencias reservadas para teste sao bloqueadas na API de calibracao.
  A verificacao reconhece hashes legados em maiusculas e hashes do manifesto em
  minusculas. O registro de testes tambem rejeita arquivos ja calibrados.
- Nao reutilize o teste para escolher exemplos, ajustar limiares ou ensinar as
  respostas. Uma nova rodada de desenvolvimento exige um teste independente.

Validacao do manifesto, sem chamadas a provedores:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_integrity.py runtime/datasets/manifest.json --provider gemini --model gemini-flash-latest
```

`--run` executa chamadas reais sobre a particao de teste, inclusive amostras sem
rotulo, e pode ter custo. O relatorio separa falhas tecnicas, abstencoes e acertos;
amostras nao verificadas nao entram nas taxas de acerto.

## Estado em 2026-09-27

- 100 fotos AlphaDent de pacientes distintos importadas, todas aguardando revisao.
- Duas edicoes conhecidas por IA, do mesmo grupo, reservadas para teste. A geracao
  tambem mudou dimensoes e adicionou margens: nao sao pares de alteracao localizada
  controlada e nao demonstram sensibilidade a edicoes sutis.
- Uma imagem frontal totalmente sintetica adicionada ao manifesto como IA_GERADA
  e a calibracao experimental da aplicacao. O contrato legado de calibracao usa
  IA_GERADA_EDITADA; o manifesto preserva a classe especifica e a procedencia.
- Prompt e inspecao da geracao: `runtime/datasets/sources/synthetic-frontal-20260927.json`.
- Total: 103 imagens, 94 reservadas para calibracao e 9 para teste. Dessas 94,
  apenas a nova imagem sintetica foi adicionada a calibracao nesta rodada.
- Nenhuma sobreposicao de hashes com o teste na calibracao ativa foi encontrada.
- Nenhum ganho de acuracia foi comprovado. Faltam controles REAL verificados,
  diversidade de geradores/edicoes e um provedor operacional para comparar rodadas.

## Treino legado

`scripts/training/` e `data/dataset_dental/` usam classes e formato de resposta
anteriores ao pipeline estruturado. Nao use nomes de pastas como comprovacao de
autenticidade nem misture esse conjunto com o manifesto sem auditar procedencia,
duplicatas e grupos. O treino legado nao gera automaticamente um modelo compativel
com o contrato Gemini, suas referencias de evidencia e auditoria.
