#!/usr/bin/env python3
"""Deterministic geography eligibility tests."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix='zeli-geo-'))
os.environ['ZELI_DB_PATH'] = str(TMP / 'recruitment.db')
os.environ.pop('ZELI_ENV', None)
os.environ.pop('RAILWAY_ENVIRONMENT', None)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server


class GeographyEvalTests(unittest.TestCase):
    def ev(self, required, candidate):
        return server.evaluate_geography(required, candidate)

    def test_latam_bogota_met(self):
        r = self.ev('Latin America', 'Bogotá, Colombia')
        self.assertEqual(r['status'], 'MET')
        self.assertIn('Bogotá', r['evidence'])

    def test_latam_panama_city_panama_met(self):
        r = self.ev('Latin America', 'Panama City, Panama')
        self.assertEqual(r['status'], 'MET')

    def test_latam_cincinnati_not_met(self):
        r = self.ev('Latin America', 'Cincinnati, Ohio, USA')
        self.assertEqual(r['status'], 'NOT_MET')
        self.assertIn('Cincinnati', r['evidence'])

    def test_latam_bengaluru_not_met(self):
        r = self.ev('Latin America', 'Bengaluru, India')
        self.assertEqual(r['status'], 'NOT_MET')
        self.assertIn('Bengaluru', r['evidence'])
        self.assertIn('Latin America', r['reason'])

    def test_latam_blank_unknown(self):
        r = self.ev('Latin America', '')
        self.assertEqual(r['status'], 'UNKNOWN')
        self.assertEqual(r['evidence'], '')

    def test_worldwide_cincinnati_unrestricted(self):
        r = self.ev('Worldwide', 'Cincinnati, Ohio')
        self.assertEqual(r['status'], 'MET')
        self.assertIn('unrestricted', r['reason'].lower())

    def test_nashville_city_met(self):
        r = self.ev('Nashville, Tennessee, USA', 'Nashville, TN')
        self.assertEqual(r['status'], 'MET')

    def test_nashville_usa_unknown(self):
        r = self.ev('Nashville, Tennessee, USA', 'USA')
        self.assertEqual(r['status'], 'UNKNOWN')

    def test_nashville_london_not_met(self):
        r = self.ev('Nashville, Tennessee, USA', 'London, UK')
        self.assertEqual(r['status'], 'NOT_MET')

    def test_openalex_us_cannot_prove_nashville(self):
        r = self.ev('Nashville, Tennessee, USA', 'US')
        self.assertEqual(r['status'], 'UNKNOWN')

    def test_openalex_us_meets_usa(self):
        r = self.ev('USA', 'US')
        self.assertEqual(r['status'], 'MET')

    def test_openalex_us_outside_latam(self):
        r = self.ev('Latin America', 'US')
        self.assertEqual(r['status'], 'NOT_MET')

    def test_does_not_infer_from_name_or_company(self):
        r = self.ev('Latin America', '')
        self.assertEqual(r['status'], 'UNKNOWN')
        parsed = server.parse_geo('Jose Garcia')
        self.assertTrue(parsed.get('ambiguous') or not parsed.get('country'))


class GeographyPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.init_db()

    def _run(self, location, work_setup='Remote'):
        criteria = server.compile_brief('Software Engineer', 'Python services', '', location, work_setup)
        plan = server.build_search_plan(criteria, 'Software Engineer', 'Python services', '', location, work_setup)
        rid = 'run_' + os.urandom(3).hex()
        con = server.db(); ts = server.now()
        con.execute('''insert into runs(id,recruiter_token,recruiter_name,recruiter_key,role,location,work_setup,brief,context,criteria_json,search_plan_json,status,created_at,updated_at,published_at)
          values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
          (rid,'tok','Tester','tester','Software Engineer',location,work_setup,'Python services','',json.dumps(criteria),json.dumps(plan),'OPERATOR_REVIEW',ts,ts,None))
        con.commit()
        return con, rid, criteria, con.execute('select * from runs where id=?',(rid,)).fetchone()

    def _hit(self, name, location, url):
        return {'name':name,'title':'Engineer','company':'','location':location,'profile_url':url,
                'summary':'explicit location only','skills':['Python'],'source_type':'public_web',
                'source_url':url,'source_title':name,'snippet':'','query':'python'}

    def test_public_graph_reevaluated_per_run(self):
        con = server.db()
        cached = self._hit('Cached Person', 'Bengaluru, India', 'https://example.com/cached-geo')
        pid = server.upsert_public_person(con, cached, 'public_web', cached['source_url'], 'brave', 'python', 1)
        self.assertTrue(pid)
        con.commit(); con.close()

        con, rid_latam, criteria, run = self._run('Latin America')
        cid,_,geo = server.stage_hit(con, run, criteria, cached, 1)
        self.assertEqual(geo['status'], 'NOT_MET')
        row = con.execute('select geo_status,geo_evidence from candidates where id=?',(cid,)).fetchone()
        self.assertEqual(row['geo_status'], 'NOT_MET')
        self.assertIn('Bengaluru', row['geo_evidence'])
        con.commit(); con.close()

        con, rid_world, criteria2, run2 = self._run('Worldwide')
        cid2,_,geo2 = server.stage_hit(con, run2, criteria2, cached, 1)
        self.assertEqual(geo2['status'], 'MET')
        row2 = con.execute('select geo_status from candidates where id=?',(cid2,)).fetchone()
        self.assertEqual(row2['geo_status'], 'MET')
        con.commit(); con.close()

        con, rid_nash, criteria3, run3 = self._run('Nashville, Tennessee, USA')
        cid3,_,geo3 = server.stage_hit(con, run3, criteria3, cached, 1)
        self.assertEqual(geo3['status'], 'NOT_MET')
        con.commit(); con.close()

    def test_not_met_normal_approve_is_not_publishable(self):
        con, rid, criteria, run = self._run('Latin America')
        hit = self._hit('India Person', 'Bengaluru, India', 'https://example.com/india-approve-geo')
        cid,_,geo = server.stage_hit(con, run, criteria, hit, 1)
        self.assertEqual(geo['status'], 'NOT_MET')
        row = con.execute('select * from candidates where id=?',(cid,)).fetchone()
        refused = server.apply_operator_approve(con, row, confirm_geo_override=False)
        self.assertFalse(refused.get('ok'))
        self.assertTrue(refused.get('needs_geo_override'))
        after = con.execute('select operator_status,geo_override,published from candidates where id=?',(cid,)).fetchone()
        self.assertEqual(after['operator_status'], 'PENDING')
        self.assertEqual(after['geo_override'], 0)
        self.assertEqual(after['published'], 0)
        eligible = con.execute("""select count(*) n from candidates where run_id=? and operator_status='APPROVED'
          and (coalesce(geo_status,'UNKNOWN')<>'NOT_MET' or coalesce(geo_override,0)=1)""",(rid,)).fetchone()['n']
        self.assertEqual(eligible, 0)
        confirmed = server.apply_operator_approve(con, row, confirm_geo_override=True)
        self.assertTrue(confirmed.get('ok'))
        overridden = con.execute('select operator_status,geo_override from candidates where id=?',(cid,)).fetchone()
        self.assertEqual(overridden['operator_status'], 'APPROVED')
        self.assertEqual(overridden['geo_override'], 1)
        con.close()

    def test_not_met_cannot_publish_accidentally(self):
        con, rid, criteria, run = self._run('Latin America')
        hit = self._hit('India Person', 'Bengaluru, India', 'https://example.com/india-geo')
        cid,_,geo = server.stage_hit(con, run, criteria, hit, 1)
        self.assertEqual(geo['status'], 'NOT_MET')
        con.execute("update candidates set operator_status='APPROVED',geo_override=0 where id=?",(cid,))
        con.commit()
        eligible = con.execute("""select count(*) n from candidates where run_id=? and operator_status='APPROVED'
          and (coalesce(geo_status,'UNKNOWN')<>'NOT_MET' or coalesce(geo_override,0)=1)""",(rid,)).fetchone()['n']
        self.assertEqual(eligible, 0)
        con.execute("""update candidates set published=case
          when operator_status='APPROVED' and (coalesce(geo_status,'UNKNOWN')<>'NOT_MET' or coalesce(geo_override,0)=1) then 1
          else 0 end where run_id=?""",(rid,))
        pub = con.execute('select published from candidates where id=?',(cid,)).fetchone()['published']
        self.assertEqual(pub, 0)
        still = con.execute('select id from candidates where id=?',(cid,)).fetchone()
        self.assertIsNotNone(still)
        con.close()

    def test_search_plan_keeps_geography_across_rounds(self):
        criteria = server.compile_brief('Software Engineer', 'Python', '', 'Latin America', 'Remote')
        plan = server.build_search_plan(criteria, 'Software Engineer', 'Python', '', 'Latin America', 'Remote')
        self.assertEqual(plan['location_hint'], 'Latin America')
        self.assertEqual(plan['geography']['region'], 'latin_america')
        for rd in plan['rounds']:
            for q in rd['queries']:
                self.assertIn('Latin America', q)
        self.assertEqual(server.github_location_query('Latin America'), '')
        self.assertEqual(server.github_location_query('Nashville, Tennessee, USA'), 'Nashville')

    def test_legacy_migration_adds_geo_columns(self):
        old_path = TMP / 'legacy-geo.db'
        import sqlite3
        con = sqlite3.connect(old_path)
        con.executescript('''
        CREATE TABLE runs(
          id TEXT PRIMARY KEY, recruiter_token TEXT NOT NULL, recruiter_name TEXT, recruiter_key TEXT NOT NULL,
          role TEXT NOT NULL, brief TEXT NOT NULL, context TEXT, criteria_json TEXT NOT NULL,
          search_plan_json TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, published_at TEXT
        );
        CREATE TABLE candidates(
          id TEXT PRIMARY KEY, run_id TEXT NOT NULL, name TEXT NOT NULL, title TEXT, company TEXT, location TEXT,
          profile_url TEXT, summary TEXT, skills_json TEXT NOT NULL DEFAULT '[]', evidence_json TEXT NOT NULL,
          verify_json TEXT NOT NULL, base_score REAL NOT NULL, learned_adjustment REAL NOT NULL DEFAULT 0,
          score REAL NOT NULL, evidence_coverage REAL NOT NULL, search_round INTEGER NOT NULL,
          operator_status TEXT NOT NULL DEFAULT 'PENDING', operator_note TEXT, rank_order INTEGER NOT NULL DEFAULT 999,
          published INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE public_people(
          id TEXT PRIMARY KEY, name TEXT NOT NULL, title TEXT, company TEXT, location TEXT, profile_url TEXT,
          first_seen_at TEXT NOT NULL, last_updated_at TEXT NOT NULL
        );
        CREATE TABLE public_person_sources(
          id INTEGER PRIMARY KEY AUTOINCREMENT, public_person_id TEXT NOT NULL, source_type TEXT NOT NULL,
          source_url TEXT, snippet TEXT, query TEXT, cached_at TEXT NOT NULL
        );
        ''')
        con.commit(); con.close()
        old = server.DB_PATH
        server.DB_PATH = old_path
        try:
            server.init_db()
            con = sqlite3.connect(old_path); con.row_factory = sqlite3.Row
            run_cols = {r['name'] for r in con.execute('PRAGMA table_info(runs)')}
            cand_cols = {r['name'] for r in con.execute('PRAGMA table_info(candidates)')}
            self.assertIn('location', run_cols)
            self.assertIn('work_setup', run_cols)
            self.assertIn('geo_status', cand_cols)
            self.assertIn('geo_evidence', cand_cols)
            self.assertIn('geo_reason', cand_cols)
            self.assertIn('geo_override', cand_cols)
            con.close()
        finally:
            server.DB_PATH = old


if __name__ == '__main__':
    unittest.main(verbosity=2)
