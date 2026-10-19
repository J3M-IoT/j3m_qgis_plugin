# J3M Connect — 1.2.0

Plugin Python/PyQGIS para consultar os dados existentes na public_api J3M, carregar coletas/geocercas e produzir mapas, séries e estudos no QGIS. A versão permanece **experimental**. Nenhuma API ou arquivo do frontend foi alterado.

## Instalação e compatibilidade

- Pacote: `dist/j3m_connect-1.2.0.zip`. Instale em **Complementos → Gerenciar e instalar complementos → Instalar a partir do ZIP** e reinicie o QGIS.
- Faixa declarada preservada: **QGIS 3.28 a 4.99**. A compatibilidade é indicada por essa faixa; a flag obsoleta `supportsQt6` foi removida.
- Interface por `qgis.PyQt`, enums com escopo e QAction adaptado a Qt5/Qt6. Sem dependências de pip, QtCharts, WebEngine, pandas ou matplotlib.
- Usa OGR, autenticação, controle temporal e exportadores fornecidos pelo QGIS.
- Execução verificada em **QGIS 3.44.13 e 3.44.15 / Qt 5.15.13 / Windows** e **QGIS 4.2.2 / Qt 6.10.2 / Linux em Docker**, com 44 testes. QGIS 3.28 não foi executado; a faixa declarada não equivale a teste de cada versão intermediária.
- Gere o ZIP com `python scripts/package.py` (Python 3; o empacotamento não importa QGIS).

## Conexão

Em **Configurações → Conexão**, informe Client ID e Client Secret e escolha **Salvar e conectar**. O cofre criptografado do QGIS guarda as credenciais; pode ser necessário desbloquear a senha mestra. O Secret nunca é repopulado. Vazio mantém o salvo, desde que o Client ID não mude.

QgsSettings guarda o identificador do cofre e preferências da interface. A integração usa os cabeçalhos X-Client-Id e X-Client-Secret, não HTTP Basic. Remover conexão apaga a entrada no cofre, sem apagar camadas baixadas.

A distribuição lê somente `j3m_connect/config.json`, com `api_url` e `timeout_seconds`. Não usa .env. Não inclua versão, rota, query, fragmento ou credenciais na URL base. HTTPS é obrigatório, exceto localhost/loopback para desenvolvimento. Timeout: inteiro positivo até 2147483, ou -1 para desabilitar. Redirecionamentos são recusados; configure a URL final. Não há teto de bytes da resposta imposto pelo plugin.

## Consultar e carregar

O painel pode ser acoplado ou flutuar; **Menu** recolhe a navegação. Usa a paleta Qt, incluindo tema claro/escuro, e lembra a posição flutuante.

1. Selecione Dispositivos, Sessões, Clusters ou Geocercas e busque por nome/UUID.
2. O período padrão selecionável é **hoje, 00:00:00 a 23:59:59**. Dispositivos/clusters usam seu fuso cadastrado; geocercas usam UTC conforme a API. Selecionar outro recurso reaplica o padrão. Atalhos: Hoje, Ontem, 7 dias e 24 horas.
3. O equivalente UTC fica explícito. Sessões usam o intervalo definido no J3M, sem filtro adicional de período.
4. Consulte total/condição, cartões das primeiras quatro métricas e tabela completa. Geocercas também consultam mínimos/máximos.
5. **Adicionar coletas ao mapa** cria um snapshot. **Adicionar vários registros** processa uma fila sequencial; falha interrompe o lote e preserva camadas concluídas. O intervalo digitado usa o fuso de cada recurso, conforme informado no seletor do lote.
6. **Salvar consulta** registra recurso, intervalo e fuso no projeto, sem segredos. Salve o projeto QGIS para persistir. Consultas salvas resolvem o recurso pelo catálogo autorizado atual.

O catálogo mostra, quando disponíveis, bateria, última coleta, status, modo, validador, observações e indicação de sessão ao vivo. Status cadastral não comprova conexão em tempo real; a atualização é manual.

O HTTP é assíncrono, com progresso e cancelamento. A interpretação do JSON, validação, gravação e preparação OGR ocorrem em tarefas de segundo plano; a camada pronta é transferida para a thread principal antes de entrar no projeto. Fechar o painel ou mudar de seção cancela as consultas e preparações pendentes, descartando resultados atrasados. As rotas atuais não oferecem cursor/paginação.

## Geocercas

**Geocercas no mapa** continua independente do dashboard: busca, marcação múltipla e uma camada/arquivo por geocerca. Marcar todas as visíveis respeita a busca; desmarcar todas também limpa ocultas. Erros são individuais e itens que falharam permanecem marcados.

Borda sólida, preenchimento com 25% de opacidade, cor cadastrada e tooltip com nome são preservados. O dashboard de coletas usa a associação geofence._id registrada no J3M, sem executar um novo recorte ponto-no-polígono.

## Análise → Camadas e estudos

Selecione uma camada J3M no projeto. Os snapshots continuam disponíveis offline. **Analisar camada ativa**, também no menu de contexto das camadas vetoriais, admite camadas antigas com collectedAt e campos collects_; sua procedência anterior fica identificada como desconhecida.

- **Mapa:** condição original ou rampa por métrica, escala fixa, tamanho de ponto e legenda para valores ausentes/fora da escala. Aliases/unidades, grupo J3M e controle temporal por collectedAt são configurados ao carregar.
- **Série:** gráfico Qt por dispositivo em UTC, com seleção ligada ao mapa. Valores ausentes interrompem as linhas, assim como intervalos superiores a 3× o intervalo mediano. Séries grandes têm desenho reduzido identificado (até 4.000 pontos no gráfico), preparado antes da pintura. A tabela limita a exibição a 2.000 observações; resumos e exportação usam todas.
- **Qualidade:** n válido, mínimo, média, mediana, máximo, desvio padrão populacional e contagens de datas/geometrias inválidas e IDs repetidos/ausentes. Zero é preservado. Unidades conflitantes suspendem resumos numéricos e gráfico.
- **Distribuição:** barras e contagens por condição, dia/noite, modo e dispositivo. São percentuais de registros, não duração de exposição.
- **Comparar:** n e médias de duas camadas, com diferença B − A quando a unidade é confirmada. Comparação descritiva, sem pareamento espacial/temporal ou inferência causal.
- **Inspecionar:** atributos completos de até 20 pontos selecionados, com cópia. O tooltip existente continua disponível.
- **Exportar:** GeoPackage, CSV com coordenadas, GeoJSON, KML, QML e procedência JSON; PDF da camada com mapa/legenda textual/estatísticas; estudo portátil QGZ + GeoPackage + estilo + procedência. Quando disponível, o pacote inclui o GeoJSON original. Não empacota automaticamente todas as bases externas do projeto.

**Atualizar snapshot** repete a consulta original usando o catálogo de integração atual, mantém a identidade da camada e seu estilo e troca sua fonte por um novo arquivo. Não é sincronização incremental. Camadas em edição são recusadas; resposta vazia preserva a camada anterior. Arquivos antigos não são apagados, pois outros projetos podem referenciá-los.

## Relatórios públicos complementares de sessão

Para uma sessão do catálogo autorizado, a aba **Relatórios da sessão** usa as rotas já existentes:

- GET /v1/device-sessions/{uuid}/collects/range: extremos e instantes.
- GET /v1/device-sessions/{uuid}/aggregation: contagem por condição.
- GET /v1/device-sessions/{uuid}/changes: mudanças persistentes.
- GET /v1/device-sessions/{uuid}/changes/detail: detalhe, série e localização; duplo clique na mudança.

Essas rotas têm política de acesso própria e **não recebem os cabeçalhos de credenciais da integração**. Não substituem silenciosamente /sessions/.... Aggregation é contagem por condição, não série horária de temperatura. Detecção e validadores continuam sendo calculados pelo backend.

## Mapas compartilhados

Em **Compartilhados → Mapas por código**, informe um código existente. O plugin consulta /v1/map-links/{code} e exporta coletas via /v1/map-links/{uuid}/export?format=geojson, sem exigir/enviar credenciais de integração. O código não é salvo no projeto ou na procedência.

Nome, dispositivos, fuso e intervalo vêm do compartilhamento; seu período não é substituído por Hoje. A camada pode ser analisada/exportada. O fundo cadastrado pode ser adicionado quando fornece modelo XYZ HTTPS com {z}/{x}/{y}. Isso não cria um catálogo administrativo de mapas. A renovação de compartilhamentos é manual nessa seção.

## Precisão, origem e limites

- Indicadores podem contar coletas sem GPS; GeoJSON exclui coordenadas inválidas. Algumas rotas usam fim exclusivo e outras inclusivo. O plugin explicita essa diferença, sem mudar regras do servidor. O intervalo padrão é enviado literalmente até 23:59:59.
- Resumos locais usam registros baixados, sem ponderação por sensor/tempo ou remoção automática de outliers. Condição ambiental não certifica qualidade metrológica.
- Procedência inclui recurso, período, fuso, versão, URL pública, download e SHA-256 do JSON canônico. O formato do hash está descrito na ficha; não é um hash do GPKG/arquivo transformado. Não contém credenciais.
- Arquivos no perfil QGIS são snapshots e não são criptografados pelo plugin. Compartilhe um estudo portátil para evitar depender do caminho do perfil.
- Unidades fornecidas têm prioridade; defaults conhecidos são mantidos. Não há conversão de unidades.
- Não há novos endpoints, cursor, atualização delta, algoritmos científicos de qualidade/conforto/interpolação, escrita no J3M ou migração do admin. Relatórios meteorológicos/diários/mensais e catálogos administrativos completos dependem de novos contratos de integração.

## Desenvolvimento e validação

Módulos: dialog (consulta), workbench (análise), analysis (resumos), charts (Qt), cartography (estilo/temporalidade/exportação), shared_maps (compartilhamentos), api (rede), settings (cofre), layers (OGR), map_tips e geofences.

dialog.ui continua legado e não é empacotado. scripts/package.py usa uma lista explícita de arquivos. ENDPOINT_VERSIONS continua permitindo versão por operação nas rotas de integração.

Execute `-m unittest discover -s tests -p 'test_*.py'` no Python do QGIS, com QT_QPA_PLATFORM=offscreen e QGIS_CUSTOM_CONFIG_PATH apontando para um perfil temporário. Exemplo de interpretador: C:/Program Files/QGIS 3.44.15/bin/python-qgis-ltr.bat.

tests/render_workbench_fixture.py gera capturas reais de widgets Qt com dados locais, sem rede/credenciais, para consulta, análise, exportação e modo compacto/escuro. A API publicada com credenciais reais não foi exercitada; contratos usam respostas locais/mocks e recursos reais do QGIS.

## Licença

Consulte j3m_connect/LICENSE. Esta versão não altera o texto da licença ou os avisos de copyright existentes.
