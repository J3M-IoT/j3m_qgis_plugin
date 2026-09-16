# Changelog

## 1.1.0

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
