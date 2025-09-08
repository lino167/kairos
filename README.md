# Kairos - Dropping Odds Scraper

Um script Python para fazer web scraping do site Dropping-Odds e extrair dados de odds de jogos ao vivo.

## Funcionalidades

- ✅ Extração de IDs de jogos ao vivo da página principal
- ✅ Scraping de dados detalhados de odds de jogos específicos
- ✅ Uso do pandas para análise de dados estruturados
- ✅ Tratamento robusto de erros

## Instalação

1. Clone o repositório:
```bash
git clone https://github.com/lino167/kairos.git
cd kairos
```

2. Crie um ambiente virtual:
```bash
python -m venv venv
```

3. Ative o ambiente virtual:
```bash
# Windows
.\venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

4. Instale as dependências:
```bash
pip install -r requirements.txt
```

## Uso

Execute o script principal:
```bash
python scraper_do.py
```

O script irá:
1. Buscar todos os IDs de jogos ao vivo
2. Fazer scraping da primeira página de evento encontrada
3. Exibir as tabelas de dados extraídas

## Estrutura do Projeto

- `scraper_do.py` - Script principal com funções de web scraping
- `requirements.txt` - Dependências do projeto
- `.gitignore` - Arquivos a serem ignorados pelo Git

## Dependências

- `requests` - Para requisições HTTP
- `beautifulsoup4` - Para parsing de HTML
- `pandas` - Para manipulação de dados
- `lxml` - Parser XML/HTML para pandas

## Funções Principais

### `get_live_match_ids()`
Extrai os IDs dos jogos ao vivo da página principal do Dropping-Odds.

### `scrape_event_page(match_id, table_type=None)`
Faz scraping de uma página específica de evento e retorna as tabelas de dados como DataFrames do pandas.

**Parâmetros:**
- `match_id` (str): ID do jogo para fazer scraping
- `table_type` (str, opcional): Tipo de tabela para extrair. Opções:
  - `None`: Página padrão do evento (dados de total/over-under)
  - `'total'`: Odds de total de gols (Over/Under)
  - `'handicap'`: Odds de handicap asiático
  - `'total_ht'`: Odds de total de gols no primeiro tempo
  - `'1x2_ht'`: Odds 1x2 do primeiro tempo
  - `'1x2'`: Odds 1x2 (Casa/Empate/Visitante)

**Exemplos de URLs geradas:**
- `https://dropping-odds.com/event.php?id=10226978` (padrão - dados de total)
- `https://dropping-odds.com/event.php?id=10226978&t=total`
- `https://dropping-odds.com/event.php?id=10226978&t=handicap`
- `https://dropping-odds.com/event.php?id=10226978&t=total_ht`
- `https://dropping-odds.com/event.php?id=10226978&t=1x2_ht`

## Exemplos de Uso

### Uso Básico
```python
from scraper_do import get_live_match_ids, scrape_event_page

# Obter IDs dos jogos ao vivo
match_ids = get_live_match_ids()
print(f"Jogos encontrados: {match_ids}")

# Fazer scraping da página padrão do primeiro jogo
if match_ids:
    tables = scrape_event_page(match_ids[0])
    print(f"Encontradas {len(tables)} tabelas")
```

### Scraping de Diferentes Tipos de Tabelas
```python
# Scraping de odds de total de gols
total_tables = scrape_event_page(match_id, 'total')

# Scraping de odds de handicap
handicap_tables = scrape_event_page(match_id, 'handicap')

# Scraping de odds do primeiro tempo
ht_tables = scrape_event_page(match_id, 'total_ht')
ht_1x2_tables = scrape_event_page(match_id, '1x2_ht')
```

### Exemplo Completo
Veja o arquivo `example_usage.py` para um exemplo completo de como usar todas as funcionalidades.

```bash
python example_usage.py
```

## Contribuição

Contribuições são bem-vindas! Sinta-se à vontade para abrir issues ou pull requests.

## Licença

Este projeto é de código aberto e está disponível sob a licença MIT.