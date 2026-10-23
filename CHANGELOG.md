# Changelog

## 1.2.1

- Tradução do plugin em português do Brasil (pt-BR), inglês dos Estados Unidos (en-US) e espanhol da Espanha (es-ES), incluindo menus, mensagens, acessibilidade, gráficos, tooltips, aliases, legendas e relatórios gerados.
- Idioma automático conforme a interface do QGIS, com fallback em inglês e seleção manual persistente no menu próprio Configurações → Idioma, separado de Conexão.
- Aplicação de outro idioma reinicia o painel e cancela consultas pendentes, preservando as camadas do projeto.
- Envio do idioma à API pelos cabeçalhos X-Locale e Accept-Language e reconhecimento de respostas vazias traduzidas nos três idiomas.
- Tradução de métricas e valores conhecidos apenas na apresentação, preservando identificadores, dados originais e o cruzamento entre indicadores e mínimos/máximos.
- 56 testes aprovados em QGIS 3.44.15 / Qt 5.15.13 / Windows e QGIS 4.2.2 / Qt 6.10.2 / Linux em Docker. API real com credenciais não exercitada.

## 1.2.0

- Painel acoplável/flutuante, menu recolhível, cartões de métricas e paleta nativa Qt.
- Datas padrão: hoje, 00:00:00 a 23:59:59, no fuso do dispositivo/cluster ou UTC em geocercas; atalhos e equivalente UTC. Sessões e compartilhamentos mantêm o período da API.
- Catálogo enriquecido, consultas salvas no projeto, carga sequencial, progresso e cancelamento visível.
- Mapas por métrica com escala fixa, classes para ausentes/fora da escala, tamanho de ponto, aliases e controle temporal.
- Série Qt, seleção ligada ao mapa, qualidade, distribuições, comparação descritiva e inspeção persistente.
- Atualização de snapshots preservando camada/estilo; adoção de camadas antigas e ação no menu de contexto do QGIS.
- Extremos, distribuições e mudanças/detalhes de sessão por rotas públicas existentes, sem encaminhar o Secret da integração.
- Mapas compartilhados por código, coletas por UUID e fundo XYZ HTTPS quando informado pela API.
- Exportações GeoPackage/CSV/GeoJSON/KML, QML, procedência, PDF e estudo portátil QGZ + GeoPackage + original quando disponível.
- Análises maiores e exportações vetoriais em tarefas canceláveis do QGIS; renderização assíncrona do mapa do PDF.
- Faixa QGIS 3.28–4.99 preservada e flag supportsQt6 obsoleta removida. 44 testes em QGIS 3.44.13/3.44.15 com Qt5 e QGIS 4.2.2 com Qt 6.10.2. API real não exercitada.
- Preparação JSON/OGR, hash e cópia de originais em segundo plano; descarte de resultados cancelados e testes de falhas HTTP/descarregamento durante tarefas. Gráficos com preparação prévia e desenho limitado.
- Metadado de licença alinhado à GPL v3 já presente no LICENSE; enums revisados pelo verificador Qt 6.
- Nenhuma alteração nas APIs ou frontend. Sem novos algoritmos científicos ou regras de classificação J3M.

## 1.1.0

- Menu em grupos expansíveis: Dispositivos, Sessões, Clusters, Geocercas e Configurações, com submenus por função.

- Nova seção independente Geocercas no mapa, com busca, seleção múltipla e uma camada por geocerca.
- Borda sólida, preenchimento com 25% de opacidade e tooltip com o nome da geocerca.
- Seleções preservadas ao filtrar/atualizar o catálogo e erros individuais na adição.

- Import de QAction compatível com Qt5/Qt6 e metadata permitindo QGIS 4.x.
- Testes de campos migrados para QMetaType em QGIS recente, mantendo fallback para QGIS 3.28.
- Cobertura do carregamento/descarregamento do plugin e da simbologia de pontos.

- Menu lateral para sessões, coletas por dispositivo, geocercas, clusters e conexão.
- Credenciais no cofre QGIS, com opção de mostrar o Secret digitado.
- Busca de registros, período com fuso explícito e indicadores em tabela.
- Mínimos/máximos de geocercas e polígonos com a cor cadastrada.
- GeoJSON dos quatro escopos diretamente no mapa.
- 18 testes locais aprovados no QGIS 3.44; API autenticada pendente de validação integrada.


## 0.1.0 — em desenvolvimento

- Estrutura inicial instalável do J3M Connect para QGIS 3.
- Ícone do pacote, menu e barra de ferramentas baseado no logotipo utilizado pelo frontend J3M.
- Interface de configuração, seleção de sessões e indicadores dinâmicos.
- Credenciais no cofre QGIS e comunicação HTTP assíncrona.
- Carregamento de GeoJSON e tratamento de erros.
- Pontos coloridos pelo hexadecimal de `markerColor`; valores ausentes ou inválidos usam cinza.
- Tooltip HTML dinâmico por coleta, com cabeçalho na cor da condição e campos ausentes/nulos ocultos.
- Pontos de adaptação para o contrato da API ainda em desenvolvimento.
- Adaptação aos exemplos da API de 14/09/2026: sessões em data por UUID/nome, indicadores dinâmicos em data e prefixo /v1.
- Campos aninhados de coletas expostos como colunas pelo OGR, incluindo métricas opcionais entre registros.
- Distinção entre 404 sem dados e recurso inacessível, com mensagens para HTTP 422/429.
- Conexão configurada exclusivamente em `config.json`, distribuído no pacote; a janela do usuário apresenta somente as credenciais.
