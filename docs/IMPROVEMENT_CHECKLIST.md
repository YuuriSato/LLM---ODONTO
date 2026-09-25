# Implementacao das melhorias

Objetivo: aplicar os 15 requisitos solicitados, com verificacao por requisito.
`[ ]` pendente; `[~]` em andamento; `[x]` implementado e verificado.

- [x] 1. Pipeline estruturado e auditoria comuns a Gemini e LM Studio.
- [~] 2. Inferencia multimodal real registrada para cada modelo configurado.
- [~] 3. Dataset com procedencia, controles, pares e separacao teste/calibracao.
- [~] 4. Avaliacao por modelo/qualidade, matriz de confusao, FP/FN e abstencoes.
- [~] 5. Privacidade: Git, retencao, protecao HTTP e rotacao de credencial exposta.
- [x] 6. SQLite, migracao idempotente e historico sem limite de 100 registros.
- [x] 7. Separacao de frontend, persistencia, uploads e orquestracao.
- [x] 8. Fila limitada, estados, cancelamento e recuperacao de falhas.
- [x] 9. Limites de bytes/pixels e validacao do conteudo dos uploads.
- [x] 10. Dependencias fixadas e instalacao reproduzivel.
- [~] 11. CI com testes de backend e interface sem credenciais reais.
- [x] 12. Selecao unica e coerente de provedor/modelo.
- [~] 13. Catalogo com servidor, capacidade, carga e disponibilidade verificada.
- [x] 14. Calibracao separada da analise comum.
- [x] 15. Filtro por modelo, comparacao lado a lado e exportacao de evidencias.

## Gates externos

- A chave exposta deve ser revogada pelo titular no provedor e substituida no
  `.env`. Nao basta remover a chave do codigo ou de uma mensagem.
- Um modelo listado nao esta aprovado: registrar chamada com imagem, schema,
  validacao de referencias e auditoria. Falha deve permanecer visivel.
- Nao atribuir procedencia clinica ou autenticidade a imagens sem comprovacao.
  Uma colecao sintetica testa engenharia, nao demonstra acuracia clinica.

## Validacao

Resultados e lacunas serao registrados conforme cada etapa for executada.
Nenhum item fica concluido somente porque existe uma implementacao ou um mock.

### Rodada 2026-09-23

- 56 testes Python passaram tambem em um ambiente virtual novo instalado de
  `requirements.lock.txt`. `pip check` sem conflitos. Windows/Python 3.13.
- Navegador: 25 combinacoes de cinco paginas e cinco larguras; persistencia do
  seletor, encaminhamento ao LM Studio simulado, retorno da fila e separacao de
  calibracao verificados. Sem erros JavaScript nem overflow horizontal.
- Historico real: 97 registros importados. Teste automatizado importa 150 registros,
  repete migracao sem duplicar e adiciona 20 registros concorrentes.
- Uploads: bytes invalidos, extensao divergente, limite de tamanho/pixels e
  caminhos externos testados. Bytes validos mantidos sem alteracao.
- 114 arquivos privados retirados somente do indice Git. JSON e 129 uploads locais
  continuam no disco. Retencao de 90 dias inspecionada em dry-run: zero candidatos.
- Chamada real `gemini-flash-latest`: HTTP 503, gate reprovado, evidencias preservadas.
- Chamada real `medgemma-4b-it`: LM Studio indisponivel, gate reprovado.
- Registro de uma amostra conhecida IA_EDITADA (image_gen), com referencia e
  limitacoes documentadas. Ausencia de controles e de conjunto representativo:
  nao ha estimativa de acuracia validada ainda.

### Rodada 2026-09-25

- 81 testes Python passaram no ambiente principal e no ambiente instalado do
  lockfile. `pip check` sem conflitos no segundo ambiente.
- Fila verificada por HTTP: envio assincrono, resposta sincrona, saturacao,
  cancelamento em execucao e leitura do estado de falha apos reinicio.
- Corrigidas corrida no cancelamento de jobs finalizados e capacidade perdida
  apos falha de persistencia. Erros nao encerram o worker nem expoem texto sensivel.
  Desconexao do navegador nao gera traceback nem cancela a analise persistida.
- Navegador: 25 combinacoes de pagina/largura, comparacao em tres larguras,
  download JSON por HTTP real em servidor temporario, persistencia de modelo,
  indisponibilidade sem fallback, reload/reconexao sem reenvio e cancelamento.
- Historico real: 97 registros consultados sem alteracao; um par existente abriu
  em 1440 e 390 px e o JSON baixado foi comparado com o resultado do backend.
- Manifesto: hashes de imagem e referencia, duplicatas, caminhos externos,
  cruzamento teste/calibracao em ambas as ordens e registro atomico testados.
  Manifesto local validado: uma amostra com rotulo verificado, ainda insuficiente
  para medir desempenho.
- Retencao: bloqueio entre processos, preservacao de arquivos/cache compartilhados,
  calibracao, timestamps com fuso, legado divergente e caminhos redirecionados
  testados em pastas temporarias. Dry-run real de 90 dias: zero candidatos.
  Nenhuma limpeza aplicada nos dados do usuario. Servidor reiniciado com lock ativo.
- Gate LM Studio repetido: `unavailable`, evidencias preservadas. Gemini nao foi
  chamado novamente nesta rodada: falta confirmacao da troca da chave exposta.
- Verificacao Git passou: nenhum arquivo de runtime ou `.env` no indice atual.

### Pendencias externas

- Executar CI no GitHub quando estas mudancas forem publicadas; workflow ainda
  nao foi executado remotamente. Validacao Linux ainda pendente.
- Rotacao da chave e eventual limpeza coordenada dos commits antigos dependem
  do titular; nao foi feito force-push nem revogacao de credencial.
- Disponibilizar provedores e repetir gates reais; nenhuma troca automatica.
