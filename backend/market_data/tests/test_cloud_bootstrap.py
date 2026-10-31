"""Exercise cloud database roles against the runner's disposable PostgreSQL."""
import importlib.util
import os
from pathlib import Path
import unittest

import psycopg
from psycopg.conninfo import conninfo_to_dict


@unittest.skipUnless(os.getenv('MARKET_TEST_DATABASE_URL'), 'Requires disposable integration cluster')
class CloudBootstrapTests(unittest.TestCase):
    def test_roles_can_do_their_job_but_cannot_write_other_workload_tables(self):
        root=Path(__file__).resolve().parents[3]
        spec=importlib.util.spec_from_file_location('bootstrap',root/'deploy/eks/bootstrap_database.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        args=conninfo_to_dict(os.environ['MARKET_TEST_DATABASE_URL'])
        args.pop('dbname',None)
        args['autocommit']=True
        api={'dbname':'alex_task09','username':'alex_task09_api','password':'test-only-api'}
        etl={'dbname':'alex_task09','username':'alex_task09_etl','password':'test-only-etl'}
        with psycopg.connect(dbname='postgres',**args) as admin:
            self.assertIsNone(admin.execute("SELECT 1 FROM pg_database WHERE datname='alex_task09'").fetchone())
            try:
                module.initialize(args,api,etl,root/'backend/database/migrations/001_schema.sql')
                with self.assertRaisesRegex(ValueError,'already exists'):
                    module.initialize(args,api,etl,root/'backend/database/migrations/001_schema.sql')
                with psycopg.connect(dbname='alex_task09',**{**args,'user':api['username'],'password':api['password']}) as connection:
                    self.assertEqual(connection.execute('SELECT count(*) FROM instruments').fetchone()[0],20)
                    connection.execute('SELECT * FROM daily_prices LIMIT 1')
                    with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                        connection.execute('DELETE FROM daily_prices')
                    with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                        connection.execute('CREATE TABLE forbidden(id int)')
                with psycopg.connect(dbname='alex_task09',**{**args,'user':etl['username'],'password':etl['password']}) as connection:
                    connection.execute('DELETE FROM daily_prices')
                    with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                        connection.execute('DELETE FROM users')
            finally:
                admin.execute('DROP DATABASE IF EXISTS alex_task09 WITH (FORCE)')
                admin.execute('DROP ROLE IF EXISTS alex_task09_api, alex_task09_etl')
