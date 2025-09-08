# Kairos Project - Web Scraper para Dropping-Odds

Este projeto é um web scraper desenvolvido para coletar dados de odds em tempo real do site Dropping-Odds.com, com foco na identificação de oportunidades de apostas baseadas em quedas significativas de odds.

## Funcionalidades

- ✅ Extração de IDs de jogos ao vivo da página principal
- ✅ Scraping de dados detalhados de odds de jogos específicos
- ✅ Uso do pandas para análise de dados estruturados
- ✅ Tratamento robusto de erros
- ✅ Análise de oportunidades baseada em drops de odds
- ✅ Estrutura modular para facilitar manutenção e extensão

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

### Execução com a nova estrutura modular:

1. Execute o módulo principal:
```bash
python main.py
```

### Execução com o script original (compatibilidade):

1. Execute o script original:
```bash
python scraper_do.py
```

### O que o sistema faz:

- Busca jogos ao vivo no site Dropping-Odds
- Extrai dados de odds para cada jogo encontrado
- Diferencia tabelas pré-live (coleta odds iniciais) das ao vivo
- Analisa drops significativos de odds (threshold configurável)
- Identifica oportunidades KAIROS baseadas em quedas de odds
- Exibe resultados detalhados no terminal

## Arquitetura Modular

### 📁 scraper/
Módulo responsável pelo web scraping:
- `web_scraper.py`: Funções para extrair dados do site Dropping-Odds
  - `get_live_match_ids()`: Obtém IDs de jogos ao vivo
  - `get_available_table_types()`: Detecta tipos de tabela disponíveis
  - `scrape_event_page()`: Extrai tabelas de uma página específica
  - `scrape_all_available_tables()`: Scraping completo de um evento

### 📁 analyzer/
Módulo responsável pela análise de oportunidades:
- `opportunity_analyzer.py`: Lógica de análise de drops e oportunidades
  - `process_tables_for_opportunity()`: Identifica oportunidades KAIROS
  - Diferencia tabelas pré-live das ao vivo
  - Analisa drops significativos baseados em threshold

### 📁 utils/
Módulo para utilitários gerais (expansível para futuras funcionalidades)

### 📄 main.py
Módulo principal que orquestra todo o sistema:
- Coordena scraping e análise
- Processa múltiplas partidas sequencialmente
- Exibe resultados formatados

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