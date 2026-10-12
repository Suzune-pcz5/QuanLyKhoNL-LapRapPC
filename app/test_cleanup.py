"""Temporary database privileges must not accumulate or affect live schemas."""
import secrets
import unittest
from unittest.mock import patch

import manage
import test_integration
import test_regressions
from db import connect, execute, one, settings


class TemporaryGrantTests(unittest.TestCase):
    def setUp(self):
        self.c = connect(admin=True)
        self.addCleanup(self.c.close)
        self.database = 'mrp_test_' + secrets.token_hex(6)
        self.addCleanup(manage.drop_temporary_database, self.c, self.database)

    def test_drop_removes_all_grant_scopes_and_keeps_other_databases(self):
        manage.initialize(self.database)
        before = set(manage.app_grants(self.c))
        target = {g for g in before if manage.grant_database(g) == self.database}
        self.assertTrue(any('UPDATE (' in g for g in target))
        self.assertTrue(any('PROCEDURE ' in g for g in target))
        self.assertEqual(manage.drop_temporary_database(self.c, self.database), len(target))
        self.assertEqual(set(manage.app_grants(self.c)), before-target)
        self.assertIsNone(one(self.c, 'SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s', (self.database,)))
        self.assertEqual(manage.revoke_temporary_grants(self.c, self.database), 0)

    def test_refuses_main_invalid_and_live_databases(self):
        before = set(manage.app_grants(self.c))
        for database in (settings()['database'], 'mysql', 'mrp_test_not_a_random_id', 'mrp_test_123456abcdef`; DROP DATABASE mysql'):
            with self.subTest(database=database):
                with self.assertRaises(ValueError):
                    manage.drop_temporary_database(self.c, database)
                with self.assertRaises(ValueError):
                    manage.revoke_temporary_grants(self.c, database)
        execute(self.c, f'CREATE DATABASE `{self.database}`')
        with self.assertRaisesRegex(ValueError, 'vẫn tồn tại'):
            manage.revoke_temporary_grants(self.c, self.database)
        self.assertEqual(set(manage.app_grants(self.c)), before)
        with patch.object(manage, 'settings', return_value=dict(settings(), database=self.database)):
            with self.assertRaises(ValueError):
                manage.drop_temporary_database(self.c, self.database)
        self.assertIsNotNone(one(self.c, 'SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s', (self.database,)))

    def test_failed_setup_cleans_database_and_grants(self):
        before = set(manage.app_grants(self.c))
        created = []
        def fail_after_initialize(database):
            created.append(database)
            manage.initialize(database)
            raise RuntimeError('Simulated setup failure after grants')
        case = test_integration.WarehouseTests('test_baseline_and_no_secrets_in_state')
        result = unittest.TestResult()
        with patch.object(test_integration, 'initialize', side_effect=fail_after_initialize):
            case.run(result)
        self.assertEqual(len(result.errors), 1, result.errors)
        self.assertIn('Simulated setup failure after grants', result.errors[0][1])
        self.assertEqual(set(manage.app_grants(self.c)), before)
        self.assertIsNone(one(self.c, 'SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s', (created[0],)))
        case = test_regressions.BackupRegressions('test_old_snapshot_verifies_after_new_live_transaction')
        result = unittest.TestResult()
        with patch.object(test_regressions.BackupRegressions, 'restores', side_effect=RuntimeError('Simulated backup setup failure')):
            case.run(result)
        self.assertEqual(len(result.errors), 1, result.errors)
        self.assertIn('Simulated backup setup failure', result.errors[0][1])
        self.assertEqual(set(manage.app_grants(self.c)), before)
        self.assertIsNone(one(self.c, 'SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s', (case.database,)))

    def test_bulk_cleanup_keeps_live_schemas_and_is_repeatable(self):
        stale = 'mrp_test_' + secrets.token_hex(6)
        self.addCleanup(manage.drop_temporary_database, self.c, stale)
        user = settings()['user']
        for database in (self.database, stale):
            execute(self.c, f'CREATE DATABASE `{database}`')
            execute(self.c, f"GRANT SELECT ON `{database}`.* TO %s@'localhost'", (user,))
        execute(self.c, f'DROP DATABASE `{stale}`')
        read_grants = manage.app_grants
        # Limit this regression to its own schemas, not historical runtime grants.
        def own_grants(c):
            return [g for g in read_grants(c) if manage.grant_database(g) in (self.database, stale, settings()['database'])]
        before = set(read_grants(self.c))
        stale_grants = {g for g in before if manage.grant_database(g) == stale}
        with patch.object(manage, 'app_grants', side_effect=own_grants):
            self.assertEqual(manage.cleanup_test_grants(), dict(databases=1, grants=1))
            self.assertEqual(manage.cleanup_test_grants(), dict(databases=0, grants=0))
        self.assertEqual(set(read_grants(self.c)), before-stale_grants)
        self.assertIsNotNone(one(self.c, 'SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s', (self.database,)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
