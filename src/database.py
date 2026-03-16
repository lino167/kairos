import sqlite3
import json
import os
from datetime import datetime

class KairosDatabase:
    def __init__(self, db_path="data/kairos.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Tabela de Partidas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS matches (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    last_score TEXT,
                    final_score TEXT,
                    status TEXT DEFAULT 'live', -- live, finished
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Tabela de Snapshots Completos (Tratados)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS event_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id TEXT,
                    live_score TEXT,
                    market_data_json TEXT, -- JSON completo tratado
                    ai_analysis_json TEXT,
                    intensity_level TEXT, -- Red2, Red3
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (match_id) REFERENCES matches (id)
                )
            ''')
            conn.commit()

    def save_snapshot(self, snapshot, ai_data, intensity="Red2"):
        """
        Trata e salva o snapshot no banco de dados.
        """
        match_id = snapshot.get("id")
        match_name = snapshot.get("match_name")
        live_score = snapshot.get("live_score")
        
        # Tratamento de dados: limpeza básica antes de salvar o JSON
        treated_markets = {}
        for m_name, m_data in snapshot.get("markets", {}).items():
            treated_markets[m_name] = {
                "opening": m_data.get("opening_odds"),
                "current": m_data.get("current_main_line"),
                "drops_count": len(m_data.get("recent_drops", [])),
                "drops": m_data.get("recent_drops", [])
            }

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Upsert Match
            cursor.execute('''
                INSERT INTO matches (id, name, last_score)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET 
                    last_score = excluded.last_score,
                    name = excluded.name
            ''', (match_id, match_name, live_score))

            # Insert Snapshot
            cursor.execute('''
                INSERT INTO event_snapshots (match_id, live_score, market_data_json, ai_analysis_json, intensity_level)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                match_id, 
                live_score, 
                json.dumps(treated_markets), 
                json.dumps(ai_data),
                intensity
            ))
            conn.commit()
            print(f"      [DB] Snapshot salvo para {match_name} (Intensidade: {intensity})")

    def get_pending_matches(self):
        """Retorna IDs de partidas que ainda estão 'live' para checagem de resultado final."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM matches WHERE status = 'live'")
            return [row[0] for row in cursor.fetchall()]

    def finalize_match(self, match_id, final_score):
        """Marca a partida como finalizada e salva o placar real."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE matches 
                SET final_score = ?, status = 'finished' 
                WHERE id = ?
            ''', (final_score, match_id))
            conn.commit()
            print(f"      [DB] Partida {match_id} FINALIZADA com placar: {final_score}")
