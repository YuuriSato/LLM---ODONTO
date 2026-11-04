# Estudo: integridade de imagens e respostas inconclusivas

Data: 22/10/2026. Escopo: documentação oficial, pesquisas primárias e inspeção dos dois casos locais. Não foram executadas novas inferências nem modificadas regras de classificação. Os dois arquivos não têm procedência autenticada por esta investigação; não são gabaritos de autenticidade.

## Conclusão principal

Há dois problemas diferentes: limitações legítimas para atribuir a origem de uma imagem e respostas do modelo com justificativas incoerentes. O projeto deve aceitar a primeira situação e rejeitar a segunda. Diminuir a quantidade de inconclusivas, isoladamente, não é um objetivo de qualidade.

## O que foi observado no projeto

| Caso | Medição local | Resposta do modelo | Interpretação sustentada |
|---|---|---|---|
| IMG_R.jpg | 685 × 224; 0,153 MP; qualidade insuficiente pela heurística | INDETERMINADO; revisão idêntica | O limite foi acionado corretamente segundo o código, mas não foi demonstrada sua validade para panorâmicas odontológicas |
| IMG2_R.webp | 797 × 1.077; 0,858 MP; qualidade boa | Chamou fotografia intraoral de RADIOGRAFIA e alegou baixa resolução; revisão manteve a justificativa | Erro observável de modalidade e divergência não resolvida entre texto e evidências |

No segundo caso, o modelo inicialmente escolheu `impossivel_avaliar`. A auditoria rejeitou a justificativa de bloqueio; a revisão mudou para `inconclusiva`, retirou `problemas_qualidade`, mas preservou a explicação de baixa resolução. A auditoria final marcou `validada`. Isso valida regras do software, não a verdade factual de todo o texto.

Arquivos examinados: `app/local_forensics.py` (`quality_assessment`), `app/ai/evidence.py`, `schemas.py`, `audit.py`, `integrity_analyzer.py` e `lmstudio_client.py`; resultados locais `58d93edf446e400a9efca75fbbc2320f` e `7bbc8cb7a2124556b2f430046a184e1e`.

## Achados da pesquisa

### 1. MedGemma não equivale a um detector de adulteração

A documentação apresenta MedGemma como ponto de partida para aplicações médicas, sujeito a adaptação e validação específica. O treinamento visual descrito abrange radiografias de tórax, patologia, dermatologia e fundo de olho. Isso não estabelece desempenho em perícia de fotografias odontológicas. O model card alerta para respostas inexatas e sensibilidade ao prompt. A documentação descreve normalização de imagens para 896 × 896 e 256 tokens por imagem no modelo original. Essas características não medem a resolução efetiva do GGUF instalado. [Model card oficial](https://huggingface.co/google/medgemma-4b-it).

O relatório técnico apresenta resultados médicos e ganhos com adaptação em tarefas específicas, sem fornecer validação desta aplicação de integridade odontológica. Portanto, não se podem transferir seus números para este projeto. [MedGemma Technical Report](https://arxiv.org/abs/2507.05201).

### 2. Resolução do arquivo, qualidade e percepção são coisas distintas

Dimensões são fatos verificáveis. Qualidade é uma estimativa dependente da tarefa: enquadramento, região de interesse, foco, exposição, compressão e tamanho dos detalhes também importam. A classificação local `boa` significa que a imagem passou nas heurísticas implementadas; não garante autenticidade nem compreensão pelo modelo. Por outro lado, não reconhecer um detalhe não autoriza inventar um defeito técnico no arquivo.

Processadores visuais podem redimensionar, recortar e normalizar a imagem antes da inferência. O envio do arquivo sem redução pelo cliente não prova que o modelo receba uma representação sem redução. [Documentação de image processors](https://huggingface.co/docs/transformers/en/image_processors).

O LM Studio documentou controles de redimensionamento de anexos na versão 0.3.31. Isso demonstra a existência de processamento intermediário, mas não determina a configuração efetiva desta instalação nem a aplicação exata desses controles ao endpoint utilizado. É necessário conferir versão, runtime e logs. [Notas oficiais](https://lmstudio.ai/blog/lmstudio-v0.3.31).

Os limites 320 px/0,18 MP e Laplaciano 14 são decisões locais. Não foi localizada nas fontes consultadas uma validação desses valores para este uso. Isso não prova que sejam inúteis; exige medição antes de usá-los como bloqueios definitivos.

### 3. JSON correto não garante interpretação correta

O LM Studio usa schemas para restringir o formato. Sua documentação adverte que nem todos os modelos conseguem produzir saídas estruturadas, especialmente abaixo de 7B. O MedGemma instalado tem 4B, o que justifica testar complexidade de schema; não prova a causa destes erros. Uma resposta com modalidade errada pode continuar sendo JSON válido. [Structured Output](https://lmstudio.ai/docs/developer/openai-compat/structured-output).

No código, `validate_references` confere se referências existem e se os valores coincidem. Não verifica suficientemente se esses valores sustentam a afirmação. Citar corretamente 797 × 1.077 não demonstra que essa resolução seja bloqueante. Após remover o bloqueio estruturado, a mesma alegação pode permanecer na justificativa livre e passar na auditoria.

### 4. Indicadores forenses não identificam automaticamente IA

ELA, ruído, nitidez e FFT descrevem propriedades que também variam com aquisição e processamento legítimo. Em estudo experimental de retoque facial, a compressão afetou a detecção e o efeito variou conforme o método. O estudo não é odontológico; serve para justificar testes de robustez, não transferir métricas. [Rathgeb et al., 2021](https://ietresearch.onlinelibrary.wiley.com/doi/full/10.1049/bme2.12027).

Ojha et al. demonstraram falhas de generalização entre famílias de geradores e propuseram um método com melhor desempenho em seus benchmarks. Isso não certifica detectores universais para imagens odontológicas. [CVPR 2023](https://arxiv.org/abs/2302.10174).

Consequência para o projeto: `sem_anomalia` significa que o teste não acionou seu limite; não significa fotografia autenticada. Duas famílias de evidências são uma precaução de engenharia, não uma garantia estatística. Elas também podem compartilhar efeitos de compressão e textura.

### 5. Abstenção precisa ser avaliada junto com erro

A classificação seletiva estuda o compromisso entre cobertura (quanto o sistema decide) e risco (erro nas decisões aceitas). Seus resultados pressupõem protocolos e dados próprios; não se transferem diretamente a um VLM com confiança declarada. [Geifman e El-Yaniv, NeurIPS 2017](https://papers.nips.cc/paper_files/paper/2017/hash/4a8423d5e91fda00bb7e46540e2b0cf1-Abstract.html).

Neste projeto é necessário separar: falha técnica; resposta inválida ou contraditória; imagem sem avaliabilidade; imagem avaliável sem evidência suficiente de origem. Hoje esses mecanismos podem terminar com uma apresentação muito semelhante ao usuário.

## Melhorias propostas, em ordem

1. **Validação semântica estruturada.** Exigir motivo de abstenção tipado, região afetada e evidências que o sustentam. Cruzar alegações computacionais com resultados correspondentes. Se houver conflito com qualidade global boa, permitir uma limitação regional apenas quando explicitamente descrita e verificável. Não usar correspondência de palavras como única solução.
2. **Revisão que resolva cada conflito.** Enviar uma lista identificada de divergências e exigir resolução individual. Se persistirem, registrar resposta contraditória/não validada, preservando o conteúdo, sem fabricar uma classificação de autenticidade.
3. **Identificação visual antes da perícia complexa.** Comparar uma descrição simples (modalidade e quantidade de painéis) com a resposta completa. Uma divergência deve acionar verificação, sem tratar cor ou metadados como prova absoluta da modalidade.
4. **Conferir o caminho visual.** Registrar modelo completo, revisão, quantização, projetor visual, runtime, template, configuração de entrada e contexto efetivo. Conferir compatibilidade entre pesos e projetor. O model card registra correção de token de imagem em julho de 2025; verificar a origem do GGUF antes de atribuir o erro a esse defeito. Quantização, revisão antiga e template são hipóteses ainda não demonstradas aqui.
5. **Qualidade por modalidade e região.** Medir panorâmicas, fotos intraorais e montagens separadamente. Preservar arquivo integral e coordenadas caso se experimentem recortes dos painéis. Não ampliar artificialmente para atravessar um limite: isso não cria detalhes reais.
6. **Avaliar antes de fine-tuning.** O JSONL legado tem 1.902 registros e zero exemplos da classe IA. Não sustenta aprendizado completo dessa distinção. Reunir procedência e histórico de edição verificáveis, exemplos reais processados legitimamente, edições convencionais, imagens geradas e edições por IA. Separar grupos/pacientes/originais e variantes entre treino, calibração e teste.

## Protocolo de experimentos sugerido

Comparar, sobre os mesmos arquivos e configurações registradas: descrição simples; schema completo; prompt revisado; resolução original e versões reduzidas; imagem composta e painéis isolados; português e inglês; outro modelo visual compatível, se disponível. Os rótulos de integridade não devem ser enviados no prompt.

Registrar modalidade correta, contradições, validade de schema, motivos de abstenção, cobertura, erro entre decisões, falsas acusações de IA, falhas técnicas, latência e repetibilidade. Para casos de origem desconhecida, avaliar descrição e coerência, sem inventar gabarito REAL. Qualquer piloto pequeno serve para depuração e não estima desempenho de produção com precisão.

## Limites deste levantamento

Dois casos locais não permitem estimar taxa de acerto ou provar uma causa única. Está demonstrada a lacuna de validação semântica; não estão demonstrados defeito do projetor, perda causada por quantização, truncamento de contexto ou redução específica no servidor. Não se comprovou autenticidade das duas imagens. Não foram enviados arquivos locais a fontes de pesquisa externas.
