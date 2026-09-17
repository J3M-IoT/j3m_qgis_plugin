# J3M Connect

Plugin Python/PyQGIS para consultar a API de integrações do J3M e carregar coletas no mapa. Versão **1.1.0**, experimental, em desenvolvimento. O backend mantém autenticação, autorização e regras de negócio; o plugin cuida da configuração, comunicação, apresentação e camadas.

## Requisitos

- QGIS 3.28 a 4.99, com Python e provedor OGR (incluídos no QGIS).
- Nenhuma dependência Python externa. Imports adaptados para Qt5/Qt6; a execução local foi validada no QGIS 3.44 com Qt5. QGIS 4/Qt6 ainda requer validação nesse ambiente.
- Para acesso remoto, URL da API e credenciais fornecidas pelo J3M.

## Instalação local

O pacote pronto está em `dist/j3m_connect-1.1.0.zip`. No QGIS, abra **Complementos → Gerenciar e instalar complementos → Instalar a partir do ZIP**, selecione o pacote e habilite **J3M Connect**. O plugin aparece no menu Complementos e na barra de ferramentas.

Para gerar novamente o ZIP, execute na raiz com Python 3:

```powershell
python scripts/package.py
```

Alternativamente, em **Configurações → Perfis de usuário → Abrir pasta do perfil ativo**, copie a pasta `j3m_connect` para `python/plugins` (crie essas subpastas se necessário), reinicie o QGIS e habilite o complemento. No Windows, o perfil padrão normalmente fica em `%APPDATA%/QGIS/QGIS3/profiles/default`.

## Configuração

As configurações globais ficam em `j3m_connect/config.json`, incluído no ZIP publicado:

```json
{
  "api_url": "https://j3m-public-api-47f36ac58e86.herokuapp.com",
  "timeout_seconds": 30
}
```

Para alterar o backend da distribuição, edite `api_url` nesse arquivo e gere novamente o pacote com `python scripts/package.py`. O arquivo é destinado ao versionamento e contém somente configurações públicas; não coloque credenciais nele. O empacotamento valida as chaves `api_url` e `timeout_seconds`.

`timeout_seconds` define o tempo máximo da requisição em segundos inteiros positivos (até 2147483, limite do temporizador Qt). Use `-1` para desabilitar o timeout do plugin. O padrão é 30 segundos. Não há limite de tamanho de resposta imposto pelo plugin.

Após instalar, o usuário informa somente **Client ID** e **Client Secret**. A URL não aparece na janela e é lida exclusivamente do `config.json` distribuído no pacote. Não é necessário criar arquivos locais. Não há leitura de `.env` nem de variáveis de ambiente para configurar o backend, nem URL fixa no código Python.

URLs salvas por versões anteriores são ignoradas. Para trocar o backend, o mantenedor altera `config.json` e distribui o pacote atualizado. Reinicie o QGIS após atualizar os arquivos. Se a configuração de conexão estiver ausente ou inválida, o plugin orienta o usuário a contatar o responsável pelo plugin.

A URL é a base da API; não inclua a versão (`/v1`, `/v2`), `/sessions`, parâmetros, fragmentos ou credenciais na URL. HTTPS é obrigatório, exceto HTTP em `localhost`, `127.0.0.1` ou `::1`, para desenvolvimento local.

Para execução local, use `http://localhost:8014` em `config.json`. A versão de cada endpoint fica em `ENDPOINT_VERSIONS`, no arquivo `j3m_connect/api.py`, inicialmente `v1`. Por exemplo, alterar somente `ENDPOINT_VERSIONS["devices"]["collections"]` para `"v2"` faz essa chamada usar `/v2/devices/{uuid}/collections`, mantendo os demais endpoints em `v1`. A operação `sessions` é um alias de `catalog` e usa a mesma versão.

Clique em **Salvar e conectar**. O QGIS poderá solicitar a criação/desbloqueio da senha mestra. Client ID e Client Secret ficam no banco de autenticação criptografado do QGIS, em uma configuração Basic usada apenas como armazenamento. As chamadas usam os cabeçalhos `X-Client-Id` e `X-Client-Secret`, não HTTP Basic. Somente o identificador da configuração de autenticação fica em QgsSettings. Deixe o campo de segredo vazio para manter o segredo já salvo; ele nunca é repopulado na interface. **Remover conexão salva** apaga essa entrada do cofre e as preferências do plugin.

## Utilização

1. No menu **Conexão**, informe Client ID e Client Secret e clique em **Salvar e conectar**. É possível mostrar o Secret digitado; ao trocar o Client ID, informe também o novo Secret.
2. Escolha **Sessões**, **Coletas por dispositivo**, **Geocercas** ou **Clusters** no menu lateral. Busque por nome/UUID, selecione o registro e use **Atualizar registros** para renovar o catálogo.
3. Sessões consultam indicadores automaticamente. Nas demais áreas, escolha início/fim e clique em **Consultar indicadores**. As datas usam o fuso exibido do dispositivo/cluster; geocercas usam UTC.
4. Veja total, condição e médias na tabela. Geocercas apresentam também mínimos e máximos.
5. **Adicionar coletas ao mapa** carrega o GeoJSON diretamente, sem pré-visualização em textarea. **Adicionar limite da geocerca ao mapa** cria seu polígono WGS 84 na cor cadastrada.

Alterar registro ou período limpa os indicadores anteriores. Cada adição cria uma nova camada persistida no perfil QGIS.

Os pontos chegam coloridos pelo campo `markerColor` de cada coleta, aceitando hexadecimal `#RRGGBB` ou `#RGB`. Campo ausente, nulo ou inválido usa cinza. Nenhum outro campo de cor é utilizado. A simbologia fica salva junto ao projeto QGIS; camadas já carregadas antes desta alteração precisam ser adicionadas novamente para receber esse estilo.

Ao adicionar uma camada, o plugin ativa as dicas de mapa do QGIS. Passe o mouse sobre um ponto da camada ativa para ver o cartão com dispositivo, condição, leituras e demais dados. O cabeçalho usa `condition.hex` (coluna `condition_hex`), com `markerColor` como alternativa e cinza se nenhuma cor for válida. As seções são construídas com os campos disponíveis; valores nulos, false, textos vazios e coleções vazias não aparecem, enquanto zero é preservado. Campos de fonte, use_queue, has_geolocation, is_working, device_id, identificadores da condição e estado de movimento são ocultados. Presença territorial e distância são agrupadas (por exemplo, Água · 12,00 m), sem has_ ou true; nomes conhecidos são traduzidos e novos nomes continuam visíveis. day/night aparecem como Dia/Noite. O tipo de firmware precede a versão, exibida em badge. A bateria usa badge verde de 75 a 100%, amarelo de 50 a menos de 75%, laranja de 25 a menos de 50% e vermelho de 0 a menos de 25%. O raio aparece uma única vez, sem casas decimais (por exemplo, 200 m), mesmo quando repetido nos objetos territoriais. Métricas novas aparecem automaticamente. As métricas conhecidas exibem unidades padrão (°C, %, hPa, m e dB); campos de unidade enviados com a métrica (`unit` ou `unidade`) têm prioridade. Métricas desconhecidas continuam aparecendo, com unidade quando fornecida. As coordenadas aparecem discretamente no topo, acima do status e da data, preservando a precisão recebida e com quebra de linha para valores longos. Os demais valores numéricos, exceto o raio, são apresentados com duas casas decimais e vírgula decimal; o valor original da camada é preservado. Não há conversões de unidades. O cartão usa três métricas por linha, reúne velocidade, rede, bateria, firmware e período, destaca o contexto territorial com distâncias e raio e omite seções sem dados. O tooltip é salvo no projeto e usa HTML, expressões nativas QGIS e um script local de dimensionamento, sem recursos externos. O cartão mantém altura natural, quebra textos longos e permite rolagem interna quando ultrapassa o espaço que o QGIS disponibiliza; nenhuma métrica é truncada. O GeoJSON original não é alterado.

Indicadores são exibidos em tabela, com métricas dinâmicas calculadas pela API. Respostas vazias, falhas de rede e erros de formato são informados na janela. Fechar a janela cancela a requisição pendente. Redirecionamentos são recusados para evitar encaminhar credenciais; configure a URL final.

## Contrato e pontos de adaptação

Contrato atualizado conforme `QGIS_INTEGRATION_HANDOFF.md`:

- `GET /{scope}` para `sessions`, `devices`, `clusters` e `geofences`.
- `GET /{scope}/{uuid}/indicators` e `/collections?format=geojson`.
- `GET /geofences/{uuid}/table` para mínimo/máximo.
- `start_date` e `end_date` em `yyyy-MM-dd HH:mm:ss`, obrigatórios fora de sessões.

Catálogos usam `{data: [...], success: true}`, UUID interno e nome visível. Médias aceitam objeto ou lista conforme o recurso. Geocercas fecham o anel usando longitude antes de latitude.

As coletas são solicitadas exclusivamente com `format=geojson`, recebendo `FeatureCollection` direto. A leitura OGR usa `FLATTEN_NESTED_ATTRIBUTES=YES` para expor objetos como colunas, por exemplo `collects_temperatura`, sem fixar nomes de métricas. O provedor reúne os campos encontrados em todas as feições; um campo ausente em determinado registro aparece como NULL, não zero. O arquivo GeoJSON mantém o conteúdo original aninhado. Arrays e tipos heterogêneos seguem a representação do OGR; não são transformados em um esquema fixo. A opção de leitura é descrita na [documentação oficial do driver GeoJSON](https://gdal.org/en/stable/drivers/vector/geojson.html).

O 404 com a mensagem documentada `There is no data for the provided parameters.` ou `No data found.` é tratado como ausência de dados nos indicadores/coletas. Outros 404 continuam sendo erro de recurso inexistente ou inacessível, sem tentar distinguir contas. Há mensagens específicas para 401/403, 422 e 429; corpos de erro do backend não são exibidos. O JSON alternativo de coletas não é usado pelo plugin.

## Desenvolvimento e validação manual

- `j3m_connect.py`: lifecycle, menu e barra de ferramentas.
- `dialog.py`: construção da interface Qt e fluxo de navegação. `dialog.ui` é legado e não é carregado nem empacotado.
- `settings.py`: URL e cofre de autenticação QGIS.
- `api.py`: HTTP assíncrono via QgsNetworkAccessManager, timeout configurável em segundos e sem limite de tamanho de resposta.
- `adapters.py`: adaptação simples das respostas em desenvolvimento.
- `layers.py`: validação e carregamento de GeoJSON via OGR.
- `scripts/package.py`: empacotamento local, sem dependências.

Use o Python fornecido pelo QGIS para executar código que importe `qgis`. A interface é construída em `dialog.py`. Após alterações, desabilite/habilite o plugin e reinicie o QGIS para recarregar todos os módulos com segurança.

Para validar GeoJSON sem API, no console Python do QGIS:

```python
from j3m_connect.layers import add_geojson_layer
sample = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"exemplo": "Validação local"},
     "geometry": {"type": "Point", "coordinates": [-46.63, -23.55]}}
]}
layer = add_geojson_layer(sample, "J3M — validação local")
iface.setActiveLayer(layer)
iface.zoomToActiveLayer()
```

Verifique também a abertura/fechamento da janela, desativação do complemento, configuração incompleta, URL inválida e respostas 401/403, 404, 500, JSON inválido e ausência de dados quando houver API de desenvolvimento disponível. Não há testes unitários nesta etapa.

## Estado e limitações

Estrutura instalável e fluxos adaptados aos exemplos fornecidos da API; a conexão com o servidor publicado ainda depende da validação com credenciais válidas. Não inclui edição, envio de coletas, criação de sessões, processamento espacial, filtros avançados ou sincronização offline. Catálogos ficam em memória durante o uso da janela.

As camadas são cópias locais estáticas em GeoJSON, armazenadas em `j3m_connect/layers` dentro do perfil ativo do QGIS. Esses arquivos permanecem após fechar o plugin, permitindo reabrir projetos; não os apague enquanto houver projetos referenciando-os. Cada carregamento gera um arquivo novo. Para compartilhar um projeto, exporte/empacote também as camadas. Os dados locais não são criptografados pelo plugin. Respostas vazias não criam camadas. Coleções com geometrias mistas dependem do suporte do OGR/QGIS e não são divididas automaticamente.

Distribuição local pronta. Publicação no catálogo oficial ainda requer definir e preencher email de manutenção e URL real do repositório em `metadata.txt`; estes dados não foram inventados.

Validação inicial executada com PyQGIS **3.44.13** no Windows, em modo sem janela e perfil temporário: imports/sintaxe, formulário Qt, lifecycle com interface simulada, cofre de autenticação real, HTTP contra servidor local temporário e camada GeoJSON via OGR. A API J3M real e a interação visual no QGIS Desktop ainda precisam ser verificadas. As demais versões declaradas não foram executadas neste ambiente.

Os exemplos fornecidos em 14/09/2026 também foram validados nesse ambiente: sessões por UUID/nome, indicadores com campos dinâmicos e GeoJSON com registros adicionais contendo métricas novas, ausentes e nulas. A verificação local confirmou as colunas OGR, a preservação do GeoJSON no disco e as respostas HTTP 401/404/422/429, incluindo a distinção de ausência de dados. Os arquivos temporários de validação não integram o repositório ou o pacote.

## Licença e referências

GPL-3.0-or-later, conforme `LICENSE`. Estrutura baseada na [documentação oficial de plugins QGIS](https://docs.qgis.org/3.40/en/docs/pyqgis_developer_cookbook/plugins/plugins.html), com credenciais no [sistema de autenticação QGIS](https://docs.qgis.org/3.40/en/docs/pyqgis_developer_cookbook/authentication.html).
