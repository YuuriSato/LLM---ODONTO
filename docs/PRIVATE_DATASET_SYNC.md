# Compartilhamento privado de imagens

O repositorio principal e publico. Nao adicione `runtime/`, fotos do historico,
manifestos privados ou pacotes exportados ao PR. O codigo de sincronizacao pode
ser revisado em um PR, mas o acervo precisa de um destino privado com acesso
restrito aos computadores autorizados.

## Exportar na maquina de origem

Pare o servico antes de copiar o historico, para evitar um pacote inconsistente.
No PowerShell, a partir da raiz do projeto:

```powershell
.\.venv\Scripts\python.exe scripts\private_dataset_bundle.py export C:\dados-privados\odonto-2026-10
.\.venv\Scripts\python.exe scripts\private_dataset_bundle.py verify C:\dados-privados\odonto-2026-10
```

O pacote deve ficar fora da pasta do repositorio. Ele inclui as imagens do manifesto, as imagens ligadas aos registros do
historico e seus metadados. Os arquivos sao copiados sem recompressao, com
SHA-256 por arquivo. Hashes detectam corrupcao, mas nao autenticam a origem do
pacote. O pacote **nao e criptografado**: use um armazenamento
privado com controle de acesso e criptografia em transito e em repouso. Revise
identificadores nas imagens, nomes e metadados e a autorizacao de uso antes de
compartilhar. Imagens do dataset legado em `data/dataset_dental/` ja sao parte
do Git e nao sao duplicadas no pacote.

## Importar em outro computador

Copie o pacote pelo canal privado. Pare o servico e rode:

```powershell
.\.venv\Scripts\python.exe scripts\private_dataset_bundle.py verify C:\dados-privados\odonto-2026-10
.\.venv\Scripts\python.exe scripts\private_dataset_bundle.py import C:\dados-privados\odonto-2026-10
```

A importacao verifica hashes e recusa IDs ou arquivos locais em conflito. Ela
preserva os registros locais e adiciona os novos. Guarde um backup antes de
importar; nao use este comando como mecanismo de sincronizacao em tempo real.

## Fine-tuning

Historico de analises nao comprova o rotulo verdadeiro. Vereditos produzidos
por LLM nao viram exemplos supervisionados automaticamente. Para listar apenas
amostras de desenvolvimento com rotulo de origem verificado:

```powershell
.\.venv\Scripts\python.exe scripts\private_dataset_bundle.py train-candidates C:\dados-privados\odonto-2026-10
```

`train_candidates.jsonl` e uma lista de candidatos para revisao, nao um dataset
pronto para o script legado de LoRA. Antes de treinar, confirme licenca/consentimento,
rotulos, diversidade e separacao por paciente/grupo; mantenha teste e calibracao
fora do treino. O script legado espera classes diferentes e precisa de uma
conversao de rotulos revisada, nao automatica.
