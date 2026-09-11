"""DAO mixin: immutable session manifests and append-only methodology events."""
from src.casefile.training import digest


class TrainingRepo:
    def configure_training(self, unit_id, config):
        import json
        # Called only by an explicit operator command, never by model tools.
        return self.conn.execute('INSERT INTO operator_decisions '
            '(unit_id, kind, question, answer, decided_at) '
            "VALUES (%s, 'training_scope', %s, %s, now()) RETURNING id",
            (unit_id, f"Training Suite — {config['reviewer']}: {config['reason']}",
             json.dumps(config, ensure_ascii=False))).fetchone()['id']

    def knowledge_context(self, unit_id, session_id, manifest):
        from src.casefile.repo import _json
        with self.conn.transaction():
            session = self.conn.execute('SELECT unit_id FROM model_sessions WHERE id = %s',
                                        (session_id,)).fetchone()
            if not session or session['unit_id'] != unit_id:
                raise ValueError('session_outside_unit')
            self.conn.execute('INSERT INTO knowledge_contexts (unit_id,session_id,manifest) '
                              'VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                              (unit_id, session_id, _json(manifest)))
            old = self.conn.execute('SELECT manifest FROM knowledge_contexts WHERE session_id=%s',
                                    (session_id,)).fetchone()['manifest']
            if digest(old) != digest(manifest):
                raise ValueError('immutable_context_mismatch')

    def knowledge_event(self, unit_id, session_id, kind, detail):
        from src.casefile.repo import _json
        if detail.get('claim_id') is not None and not self.claim_existe(unit_id, detail['claim_id']):
            raise ValueError('claim_outside_unit')
        if detail.get('research_id') is not None and not self.conn.execute(
                'SELECT id FROM research_items WHERE id=%s AND unit_id=%s',
                (detail['research_id'], unit_id)).fetchone():
            raise ValueError('research_outside_unit')
        return self.conn.execute('INSERT INTO knowledge_events (unit_id,session_id,kind,detail) '
                                 'VALUES (%s,%s,%s,%s) RETURNING id',
                                 (unit_id, session_id, kind, _json(detail))).fetchone()['id']

    def knowledge_audit(self, unit_id):
        return {'contexts': self.conn.execute('SELECT * FROM knowledge_contexts WHERE unit_id=%s '
                    'ORDER BY session_id', (unit_id,)).fetchall(),
                'events': self.conn.execute('SELECT * FROM knowledge_events WHERE unit_id=%s '
                    'ORDER BY id', (unit_id,)).fetchall()}
