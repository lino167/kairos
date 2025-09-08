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

### `scrape_event_page(match_id)`
Faz scraping de uma página específica de evento e retorna as tabelas de dados como DataFrames do pandas.

## Contribuição

Contribuições são bem-vindas! Sinta-se à vontade para abrir issues ou pull requests.

## Licença

Este projeto é de código aberto e está disponível sob a licença MIT.