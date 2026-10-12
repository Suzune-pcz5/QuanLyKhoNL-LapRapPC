"""Stock diagnostics and non-destructive upgrades, using disposable MySQL DBs."""
import re
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import migrations
from db import connect, execute, one, sql_statements
from manage import SCHEMA, database_snapshot
from test_integration import WarehouseTests


class PRDFixes(WarehouseTests):
    def legacy_routine(self, c):
        source = next(sql for sql in sql_statements(SCHEMA.read_text(encoding='utf-8')) if sql.startswith('CREATE PROCEDURE sp_ghi_bien_dong('))
        source = re.sub(r"  IF p_TT<0 AND p_Loi=0 THEN\n.*?  END IF;\n", '', source, flags=re.S)
        self.assertNotIn(migrations.STOCK_MARKER, source)
        execute(c, 'DROP PROCEDURE sp_ghi_bien_dong')
        execute(c, source)
        return one(c, 'SHOW CREATE PROCEDURE sp_ghi_bien_dong')['Create Procedure']

    def test_material_shortage_names_line_and_rolls_back_whole_document(self):
        job = self.job(qty=7)
        outgoing = self.allocate(job, cpu=7, ram=14)
        before = self.state()
        error = self.action('outgoing', outgoing, 'approve', expected=409)
        self.assertEqual(error['code'], 'INSUFFICIENT_STOCK')
        self.assertEqual(error['details'], dict(sku='RAM-001', location='LK-A1', required=14, available=12, missing=2))
        self.assertEqual(error['error'], 'RAM-001 tại LK-A1: cần 14, khả dụng 12, thiếu 2.')
        after = self.state()
        self.assertEqual(after['inventory'], before['inventory'])
        self.assertEqual(after['ledger'], before['ledger'])
        self.assertEqual(next(j for j in after['jobs'] if j['MaYC'] == job)['TrangThai'], 'DA_GIAO')

    def test_finished_and_faulty_stock_shortages_show_correct_available_quantity(self):
        for location, available in [(2, 1), (3, 0)]:
            outgoing = self.create('outgoing', dict(LoaiXuat='THANH_PHAM', TenNguoiNhan='Bộ phận kiểm thử', lines=[dict(MaSP=3, MaViTri=location, SoLuongXuat=2)]), self.employee)
            self.action('outgoing', outgoing, 'send', self.employee)
            before = self.state()
            error = self.action('outgoing', outgoing, 'approve', expected=409)
            self.assertEqual(error['details'], dict(sku='PC-001', location='TP-A1' if location == 2 else 'LOI-A1', required=2, available=available, missing=2-available))
            self.assertEqual(self.state()['inventory'], before['inventory'])
            self.assertEqual(self.state()['ledger'], before['ledger'])

    def test_concurrent_approvals_report_stock_from_the_locked_row(self):
        outgoing = [self.shipment(), self.shipment()]
        clients = [self.login('quanly'), self.login('quanly')]
        barrier = threading.Barrier(2)
        def approve(index):
            client = clients[index]
            token = client.get('/api/session').json['csrf']
            barrier.wait()
            return client.post(f'/api/actions/outgoing/{outgoing[index]}/approve', json={}, headers={'X-CSRF-Token': token})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(approve, range(2)))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        error = next(r.json for r in responses if r.status_code == 409)
        self.assertEqual(error['details']['available'], 0)
        self.assertEqual(error['details']['missing'], 1)
        self.assertEqual(self.quantity('PC-001', 2)['SoLuongKhaDung'], 0)

    def test_upgrade_preserves_data_and_can_be_repeated(self):
        c = connect(admin=True, database=self.database)
        rollback = None
        try:
            self.legacy_routine(c)
            before = database_snapshot(c, self.database)
            result = migrations.upgrade_stock_diagnostics(c, self.database)
            self.assertTrue(result['changed'])
            rollback = Path(result['rollback'])
            self.assertTrue(rollback.is_file())
            self.assertEqual(database_snapshot(c, self.database), before)
            self.assertEqual(migrations.upgrade_stock_diagnostics(c, self.database), dict(changed=False))
            self.assertIn(migrations.STOCK_MARKER, one(c, 'SHOW CREATE PROCEDURE sp_ghi_bien_dong')['Create Procedure'])
            self.test_finished_and_faulty_stock_shortages_show_correct_available_quantity()
        finally:
            c.close()
            if rollback:
                rollback.unlink(missing_ok=True)

    def test_failed_upgrade_restores_the_previous_procedure(self):
        c = connect(admin=True, database=self.database)
        try:
            original = self.legacy_routine(c)
            before = database_snapshot(c, self.database)
            def fail_replacement(connection, sql, args=()):
                if sql.startswith('CREATE PROCEDURE') and migrations.STOCK_MARKER in sql:
                    raise RuntimeError('Simulated CREATE failure')
                return execute(connection, sql, args)
            with patch.object(migrations, 'execute', side_effect=fail_replacement):
                with self.assertRaisesRegex(RuntimeError, 'Simulated CREATE failure'):
                    migrations.upgrade_stock_diagnostics(c, self.database)
            self.assertEqual(one(c, 'SHOW CREATE PROCEDURE sp_ghi_bien_dong')['Create Procedure'], original)
            self.assertEqual(database_snapshot(c, self.database), before)
        finally:
            c.close()
            for path in (migrations.RUNTIME / 'migrations').glob(f'{self.database}_stock_*.sql'):
                path.unlink()


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(PRDFixes(name) for name in sorted(PRDFixes.__dict__) if name.startswith('test_'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
