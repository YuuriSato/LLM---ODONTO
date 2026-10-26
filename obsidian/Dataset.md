---
tags: [lm-odonto, dados]
---

# Dataset

Origem pública candidata e ressalvas sobre os rótulos: [[Origem OPG]].

[[Inicio]] · [[Rede neural]] · [[Validacao]] · [[Decisoes]]

O JSONL legado tem 1.902 registros: REAL 1.352; alterações manuais 250; digitais 250; indeterminado 50. Não contém classe IA. Rótulos de pasta não são comprovação de origem.

Para a nova CNN, cada imagem precisa de hash, grupo/paciente/original, origem, rótulo verificado e divisão train/validation/test. Todas as variantes do mesmo original devem permanecer no mesmo grupo. O carregador recusa grupos cruzados, arquivos duplicados, hashes divergentes e rótulos não verificados.

O manifesto dental exige REAL, EDICAO_TRADICIONAL, IA_GERADA e IA_EDITADA. O modelo escolhe checkpoint pela validação; o teste só é usado após essa escolha. Não adicionar imagens do teste ao treino após observar seus resultados sem criar uma nova avaliação independente.

Pendência: reunir uma base dental com essas classes e procedência comprovada. O material legado pode ajudar na exploração, mas não deve receber atestação automática.

Inventário de toda a pasta `data`: 3.254 imagens, 1.386 hashes únicos, 1.868 cópias duplicadas e nenhum erro de leitura. Candidatos por pasta: 500 edição tradicional, 1.352 REAL, 1.402 sem rótulo. As contagens incluem duplicatas. Revisão em `../fine_tuning/datasets/legacy-review-v1/review.csv`; nenhuma linha foi atestada automaticamente.

## Revisão sem duplicatas

A fila `../fine_tuning/datasets/legacy-queue-v1/queue.json` reúne as cópias por hash: 837 conteúdos candidatos a REAL, 500 a edição tradicional e 49 sem rótulo. Não foram encontrados hashes com rótulos candidatos conflitantes. Os vínculos por nome e hash formam 836 grupos candidatos; isso não equivale a 836 pacientes, pois a identidade do paciente não foi confirmada.

O script `scripts/training/synthesize_training_variants.py` descreve desenhos coloridos e colagens como edições tradicionais, além de redução de resolução/desfoque. Ele não gera exemplos com IA. A existência desse script e os nomes dos arquivos não provam que os bytes atuais foram produzidos por aquela execução. Registros ou reprodução verificável ainda são necessários.

Revise cada conteúdo apenas uma vez e selecione uma única cópia no CSV original. A fila não modifica o CSV nem certifica rótulos. Instruções em `../fine_tuning/datasets/legacy-queue-v1/README.md`.

## Transformações reproduzidas

A auditoria local reproduziu exatamente os bytes de todas as 550 variantes: 250 marcações, 250 colagens e 50 degradações, usando seed 7 e o script legado. O relatório registra hashes de origem, destino, reprodução e receita, além da versão do Pillow. Arquivo: `../fine_tuning/datasets/legacy-review-v1/transformation-audit.json`. Isso comprova a relação reprodutível com a imagem-base; não comprova origem clínica nem autenticidade dessa base. As classes de IA continuam sem exemplos verificados.
