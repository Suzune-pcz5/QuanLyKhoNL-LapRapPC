"""Regressions for the defects reproduced during the second QA round.

Every case uses a disposable real MySQL database; backup probes never touch
the application's live data. Run with python -m unittest test_regressions -v.
"""
import secrets
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pymysql
import manage
from db import connect, execute, rows, settings
from test_integration import WarehouseTests


class WorkflowRegressions(WarehouseTests):
    def receipt(self):
        return dict(MaNCC=1, NgayChungTu='2026-10-10', lines=[dict(MaSP=1, MaViTri=1, SoLuongNhan=2, SoLuongLoi=0, DonGiaNhap='1.50')])

    def test_inspection_note_survives_omitted_field_and_can_be_cleared(self):
        data = self.receipt()
        note = 'Đã kiểm tra <đủ linh kiện> và tem bảo hành'
        data['lines'][0]['KetQuaKiemTra'] = note
        receipt = self.create('incoming', data)
        del data['lines'][0]['KetQuaKiemTra']
        data['GhiChu'] = 'Chỉ sửa thông tin phiếu'
        self.mutate(self.manager, f'documents/incoming/{receipt}', data, method='PUT')
        saved = next(r for r in self.state()['incoming'] if r['MaPN'] == receipt)
        self.assertEqual(saved['lines'][0]['KetQuaKiemTra'], note)
        data['lines'][0]['KetQuaKiemTra'] = ''
        self.mutate(self.manager, f'documents/incoming/{receipt}', data, method='PUT')
        saved = next(r for r in self.state()['incoming'] if r['MaPN'] == receipt)
        self.assertIsNone(saved['lines'][0]['KetQuaKiemTra'])

    def test_inspection_note_does_not_move_to_another_product(self):
        data = self.receipt()
        data['lines'][0]['KetQuaKiemTra'] = 'Chỉ dành cho CPU'
        receipt = self.create('incoming', data)
        data['lines'][0]['MaSP'] = 2
        del data['lines'][0]['KetQuaKiemTra']
        self.mutate(self.manager, f'documents/incoming/{receipt}', data, method='PUT')
        saved = next(r for r in self.state()['incoming'] if r['MaPN'] == receipt)
        self.assertIsNone(saved['lines'][0]['KetQuaKiemTra'])

    def test_stopped_location_is_excluded_from_issuable_needs(self):
        job = self.job(qty=3)
        location = next(r for r in self.state(self.admin)['locations'] if r['MaViTri'] == 1)
        location['TrangThai'] = 'NGUNG'
        self.mutate(self.admin, 'catalog/locations/1', location, method='PUT')
        data = self.state()
        needs = next(r for r in data['jobs'] if r['MaYC'] == job)['needs']
        self.assertEqual([(r['SoLuongKhaDung'], r['SoLuongThieu']) for r in needs], [(0, 3), (0, 6)])
        self.assertEqual(next(r for r in data['inventory'] if r['MaSP'] == 1)['SoLuongThucTe'], 7)
        location['TrangThai'] = 'HOAT_DONG'
        self.mutate(self.admin, 'catalog/locations/1', location, method='PUT')
        needs = next(r for r in self.state()['jobs'] if r['MaYC'] == job)['needs']
        self.assertEqual([r['SoLuongThieu'] for r in needs], [0, 0])

    def test_stopped_product_is_excluded_from_issuable_needs(self):
        job = self.job()
        product = next(r for r in self.state(self.admin)['products'] if r['MaSP'] == 1)
        product['TrangThai'] = 'NGUNG'
        self.mutate(self.admin, 'catalog/products/1', product, method='PUT')
        need = next(r for r in next(j for j in self.state()['jobs'] if j['MaYC'] == job)['needs'] if r['MaSPLinhKien'] == 1)
        self.assertEqual((need['SoLuongKhaDung'], need['SoLuongThieu']), (0, 3))

    def test_lock_and_role_change_blocked_until_job_cancelled(self):
        job = self.job()
        for data in [dict(VaiTro='NHAN_VIEN', TrangThai='KHOA'), dict(VaiTro='QUAN_LY_KHO', TrangThai='HOAT_DONG')]:
            error = self.mutate(self.admin, 'accounts/2', data, method='PUT', expected=409)
            self.assertIn('#'+str(job), error['error'])
        self.assertEqual(self.employee.get('/api/state').status_code, 200)
        self.action('jobs', job, 'cancel', reason='Hủy trước khi cấp vật liệu')
        self.mutate(self.admin, 'accounts/2', dict(VaiTro='NHAN_VIEN', TrangThai='KHOA'), method='PUT')
        self.assertEqual(self.employee.get('/api/state').status_code, 401)

    def test_deactivate_employee_blocked_after_materials_issued(self):
        job = self.job()
        self.action('outgoing', self.allocate(job), 'approve')
        employee = next(r for r in self.state(self.admin)['employees'] if r['MaNV'] == 2)
        employee['TrangThai'] = 'NGUNG_LAM'
        self.mutate(self.admin, 'catalog/employees/2', employee, method='PUT', expected=409)
        self.action('results', self.result(job), 'accept')
        self.mutate(self.admin, 'catalog/employees/2', employee, method='PUT')
        self.assertEqual(self.employee.get('/api/state').status_code, 401)

    def test_password_change_allowed_with_active_job_and_relogin(self):
        self.job()
        self.mutate(self.admin, 'accounts/2', dict(VaiTro='NHAN_VIEN', TrangThai='HOAT_DONG', password='Changed@12345'), method='PUT')
        self.assertEqual(self.employee.get('/api/state').status_code, 401)
        csrf = self.employee.get('/api/session').json['csrf']
        result = self.employee.post('/api/login', json=dict(username='nhanvien', password='Changed@12345'), headers={'X-CSRF-Token': csrf})
        self.assertEqual(result.status_code, 200)

    def test_assignment_competing_with_lock_or_deactivation_never_strands_job(self):
        for change in ('account', 'employee'):
            for _ in range(3):
                job = self.create('jobs', dict(MaBOM=1, SoLuongYeuCau=1, MaNVNhan=2))
                employee = next(r for r in self.state(self.admin)['employees'] if r['MaNV'] == 2)
                barrier = threading.Barrier(2)
                def assign():
                    token = self.manager.get('/api/session').json['csrf']
                    barrier.wait()
                    return self.manager.post(f'/api/actions/jobs/{job}/assign', json={}, headers={'X-CSRF-Token': token})
                def deactivate():
                    token = self.admin.get('/api/session').json['csrf']
                    path = '/api/accounts/2' if change == 'account' else '/api/catalog/employees/2'
                    data = dict(VaiTro='NHAN_VIEN', TrangThai='KHOA') if change == 'account' else dict(employee, TrangThai='NGUNG_LAM')
                    barrier.wait()
                    return self.admin.put(path, json=data, headers={'X-CSRF-Token': token})
                with ThreadPoolExecutor(max_workers=2) as pool:
                    assigned, changed = pool.submit(assign), pool.submit(deactivate)
                    assigned, changed = assigned.result(), changed.result()
                self.assertEqual(sorted([assigned.status_code, changed.status_code]), [200, 409], (assigned.json, changed.json))
                saved = next(j for j in self.state()['jobs'] if j['MaYC'] == job)
                self.assertEqual(saved['TrangThai'], 'DA_GIAO' if assigned.status_code == 200 else 'NHAP')
                if assigned.status_code == 200:
                    self.action('jobs', job, 'cancel', reason='Kết thúc kiểm thử đồng thời')
                self.mutate(self.admin, 'accounts/2', dict(VaiTro='NHAN_VIEN', TrangThai='HOAT_DONG'), method='PUT')
                self.mutate(self.admin, 'catalog/employees/2', dict(employee, TrangThai='DANG_LAM'), method='PUT')


class BackupRegressions(WarehouseTests):
    def setUp(self):
        super().setUp()
        self.config_patch = patch.object(manage, 'settings', return_value=dict(settings(), database=self.database))
        self.addCleanup(self.config_patch.stop)
        self.config_patch.start()
        self.files = []
        self.previous_restores = self.restores()

    def restores(self):
        c = connect(admin=True)
        try:
            return {r['Database'] for r in rows(c, 'SHOW DATABASES') if r['Database'].startswith('mrp_restore_')}
        finally:
            c.close()

    def snapshot(self):
        c = connect(admin=True, database=self.database)
        try:
            return manage.database_snapshot(c, self.database)
        finally:
            c.close()

    def backup(self):
        filename = manage.backup()
        self.files.append(manage.BASE / 'backups' / filename)
        self.assertEqual(self.restores(), self.previous_restores)
        return filename

    def tearDown(self):
        self.config_patch.stop()
        for path in self.files:
            path.unlink(missing_ok=True)
        super().tearDown()

    def verify(self, filename):
        before = self.snapshot()
        result = manage.verify_restore(filename)
        self.assertEqual(self.snapshot(), before, 'Verification changed the source database')
        self.assertEqual(self.restores(), self.previous_restores, 'Temporary restore database leaked')
        self.assertTrue(result['login_verified'] and result['transaction_verified'] and result['temporary_database_removed'])
        self.assertEqual((result['tables'], result['views'], result['routines'], result['triggers']), (17, 4, 16, 19))
        return result

    def test_old_snapshot_verifies_after_new_live_transaction(self):
        filename = self.backup()
        receipt = self.create('incoming', dict(MaNCC=1, NgayChungTu='2026-10-10', lines=[dict(MaSP=1, MaViTri=1, SoLuongNhan=1, SoLuongLoi=0, DonGiaNhap=1)]))
        self.action('incoming', receipt, 'commit')
        self.assertTrue(self.verify(filename)['data_matched'])

    def test_changed_password_and_absent_default_manager_supported(self):
        self.mutate(self.admin, 'accounts/1', dict(VaiTro='QUAN_LY_KHO', TrangThai='HOAT_DONG', password='Changed@12345'), method='PUT')
        c = connect(admin=True, database=self.database)
        execute(c, "UPDATE TAI_KHOAN SET TenDangNhap='renamed_manager',TrangThai='KHOA' WHERE MaTK=1")
        execute(c, "UPDATE SAN_PHAM SET TrangThai='NGUNG'")
        execute(c, "UPDATE VI_TRI_KHO SET TrangThai='NGUNG'")
        execute(c, "UPDATE NHA_CUNG_CAP SET TrangThai='NGUNG'")
        c.close()
        self.assertTrue(self.verify(self.backup())['data_matched'])

    def test_qualified_schema_text_and_unicode_are_preserved(self):
        c = connect(admin=True, database=self.database)
        note = f"Đủ tem: `{self.database}`. không phải định danh; 'ký tự' và \\ dấu gạch"
        execute(c, 'UPDATE SAN_PHAM SET MoTa=%s WHERE MaSP=1', (note,))
        c.close()
        self.assertTrue(self.verify(self.backup())['data_matched'])

    def test_corrupt_backup_is_rejected_and_api_can_retry(self):
        filename = self.backup()
        path = manage.BASE / 'backups' / filename
        original = path.read_text(encoding='utf-8')
        path.write_text(original + '\n-- changed\n', encoding='utf-8')
        error = self.mutate(self.admin, 'restore-test', dict(file=filename), expected=409)
        self.assertIn('đã bị thay đổi', error['error'])
        self.assertEqual(self.restores(), self.previous_restores)
        path.write_text(original, encoding='utf-8', newline='\n')
        result = self.mutate(self.admin, 'restore-test', dict(file=filename))
        self.assertTrue(result['result']['data_matched'])
        self.assertEqual(self.restores(), self.previous_restores)

    def test_legacy_dump_is_supported_with_explicit_integrity_limit(self):
        filename = self.backup()
        path = manage.BASE / 'backups' / filename
        original = path.read_text(encoding='utf-8')
        path.write_text(original.partition('\n')[2], encoding='utf-8')
        result = self.verify(filename)
        self.assertTrue(result['legacy_backup'])
        self.assertFalse(result['data_matched'])

    def test_failed_sql_import_removes_temporary_database(self):
        path = manage.BASE / 'backups' / ('mrp_broken_' + secrets.token_hex(6) + '.sql')
        self.files.append(path)
        path.write_text('CREATE TABLE probe (id INT);\nINVALID SQL;\n', encoding='utf-8')
        with self.assertRaises(pymysql.ProgrammingError):
            manage.verify_restore(path.name)
        self.assertEqual(self.restores(), self.previous_restores)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(cls(name) for cls in (WorkflowRegressions, BackupRegressions) for name in sorted(cls.__dict__) if name.startswith('test_'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
