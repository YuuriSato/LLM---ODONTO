# Rede neural e organização dos dados

A CNN está em `app/neural/`. O treinamento usa validação para escolher o checkpoint e testa somente depois dessa escolha. A arquitetura é uma baseline experimental pequena, não um detector odontológico previamente validado.

## Ambiente separado

```powershell
python -m venv .venv-neural
.\.venv-neural\Scripts\python.exe -m pip install -r requirements-neural.lock.txt
```

O lockfile registra o ambiente Windows/Python 3.13 usado nesta instalação. CPU funciona; CUDA depende de uma distribuição PyTorch compatível com o hardware. O serviço web não precisa importar PyTorch.

## Inventário existente

Foi criado `fine_tuning/datasets/legacy-review-v1/`:

- `review.csv`: 3.254 arquivos, dimensões, hashes e campos para revisão.
- `inventory.json`: contagens resumidas.
- `duplicates.json`: 1.868 cópias além dos 1.386 conteúdos únicos.
- `groups.json`: sugestões de agrupamento por nome entre originais e variantes.

Nenhuma imagem foi apagada, movida ou rotulada como verificada. São 500 candidatos a edição tradicional, 1.352 candidatos REAL e 1.402 sem rótulo. Cópias exatas podem aparecer em mais de uma pasta; essas contagens não representam amostras independentes.

Reproduzir em uma nova pasta:

```powershell
.\.venv\Scripts\python.exe scripts/training/inventory_dataset.py --source data --output fine_tuning/datasets/legacy-review-v2
```

## Revisão antes do treino dental

No CSV, preencha apenas quando houver evidência:

| Campo | Conteúdo |
|---|---|
| verified_label | REAL, EDICAO_TRADICIONAL, IA_GERADA ou IA_EDITADA |
| verified_group | Mesmo grupo para paciente/original e todas as variantes |
| provenance | Origem e evidência da autenticidade ou do processo de edição |
| reviewer | Responsável pela confirmação |
| reviewed_at | Data da revisão |
| split | train, validation ou test |
| include | yes para incluir; no para excluir |

Nome de pasta e sugestão automática não bastam. Para cada duplicata exata, selecione uma única cópia. Augmentations de um mesmo exame podem ter nomes diferentes: revise o agrupamento além das sugestões automáticas. Cada classe deve existir nas três divisões; não reutilize a mesma imagem para satisfazer esse requisito.

```powershell
.\.venv\Scripts\python.exe scripts/training/build_reviewed_manifest.py fine_tuning/datasets/legacy-review-v1/review.csv --source data --output fine_tuning/datasets/dental-v1
.\.venv-neural\Scripts\python.exe scripts/training/train_neural.py fine_tuning/datasets/dental-v1/manifest.json --output fine_tuning/runs/dental-v1 --epochs 20 --batch-size 16
```

O primeiro comando recusará a planilha atual porque nenhuma linha foi atestada. Esse é o estado correto enquanto a revisão está pendente. O dataset resultante será autocontido, com cópias dos arquivos aprovados e hashes conferidos.

## Artefatos por execução

Cada pasta contém `config.json`, `manifest.json`, `history.json`, `model.pt` e `evaluation.json`. O manifesto copiado na execução é um registro da seleção; suas imagens permanecem no dataset original da execução. A configuração guarda o hash do manifesto e a avaliação guarda o hash dos pesos.

O relatório inclui matriz de confusão, acurácia, acurácia balanceada e recall por classe. Softmax não é confiança calibrada. Dados de teste precisam ser reservados antes de experimentar configurações; os resultados do piloto não aprovam uso operacional.

Predição:

```powershell
.\.venv-neural\Scripts\python.exe scripts/training/predict_neural.py CAMINHO_DA_IMAGEM --checkpoint fine_tuning/runs/dental-v1/model.pt
```

## Integração experimental com a aplicação

Após treinar um checkpoint dental, `NEURAL_CHECKPOINT` no `.env` pode apontar para seu caminho completo. Somente `APP_ENV=development` ativa esse adaptador. Reinicie o backend após configurar.

O adaptador usa o Python de `.venv-neural`, identifica a versão pelo hash dos pesos e registra a distribuição no resultado do detector. A conclusão desse componente permanece inconclusiva: sem calibração e validação de campo, o score não pode determinar o veredito. Pesos de engenharia são rejeitados pela integração odontológica.

## Teste de engenharia executado

`engineering-v1` contém 112 imagens geométricas: 64 treino, 24 validação e 24 teste. O treino de 8 épocas foi preservado e teve acurácia de teste 0,375. A execução `engineering-v2`, com 40 épocas, aprendeu os quatro padrões e acertou 24/24 controles. A leitura dos pesos e predição por CLI foram verificadas.

Esses experimentos verificam funcionamento e aprendizado em padrões artificiais. A repetição foi parte da depuração do treinamento; 24/24 não é uma estimativa imparcial de desempenho geral, nem mede odontologia ou detecção de IA. Não há modelo dental treinado nesta etapa.

```powershell
.\.venv-neural\Scripts\python.exe scripts/training/neural_smoke_dataset.py fine_tuning/datasets/engineering-new
.\.venv-neural\Scripts\python.exe scripts/training/train_neural.py fine_tuning/datasets/engineering-new/manifest.json --output fine_tuning/runs/engineering-new --epochs 40
```

Conhecimento relacionado: `obsidian/Rede neural.md`, `obsidian/Dataset.md` e `obsidian/Validacao.md`.
