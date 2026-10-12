"""Boundary, session and concurrent-action regressions against real MySQL."""
import csv
import io
import re
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from db import connect, execute
from manage import SCHEMA
from messages import SQL_ERRORS
from test_integration import WarehouseTests


class AuditEdges(WarehouseTests):
    def receipt(self, **changes):
        data = dict(MaNCC=1, NgayChungTu='2026-10-11', lines=[dict(MaSP=1, MaViTri=1, SoLuongNhan=1, SoLuongLoi=0, DonGiaNhap='0.00')])
        return dict(data, **changes)

    def test_validation_uses_human_labels_and_rolls_back(self):
        before = self.state()
        for value in [0, float('inf'), float('-inf'), float('nan'), [], {}, True, '2147483648']:
            data = self.receipt()
            data['lines'][0]['SoLuongNhan'] = value
            error = self.mutate(self.manager, 'documents/incoming', data, expected=400)['error']
            self.assertIn('Số lượng thực nhận', error)
            self.assertNotIn('SoLuongNhan', error)
        error = self.mutate(self.admin, 'catalog/suppliers', {}, expected=400)['error']
        self.assertIn('Tên nhà cung cấp', error)
        error = self.mutate(self.manager, 'documents/incoming', self.receipt(MaNCC=99999), expected=400)['error']
        self.assertIn('Nhà cung cấp', error)
        self.assertEqual(self.state()['incoming'], before['incoming'])
        self.assertEqual(self.state()['ledger'], before['ledger'])

    def test_text_limits_with_unicode(self):
        product = dict(MaLoai=1, SKU='EDGE-UNICODE', TenSP='Ổ cứng thử nghiệm 🖥', LoaiMatHang='NGUYEN_LIEU', DonViTinh='cái', MoTa='ế'*500)
        ident = self.mutate(self.admin, 'catalog/products', product)['id']
        self.assertEqual(next(p for p in self.state()['products'] if p['MaSP'] == ident)['MoTa'], 'ế'*500)
        self.mutate(self.admin, f'catalog/products/{ident}', dict(product, MoTa='ế'*501), method='PUT', expected=400)
        self.mutate(self.admin, 'catalog/categories', dict(TenLoai='Nhóm thử', MoTa='ế'*256), expected=400)
        self.mutate(self.admin, 'catalog/suppliers', dict(TenNCC='ế'*150))
        self.mutate(self.admin, 'catalog/suppliers', dict(TenNCC='ế'*151), expected=400)
        data = self.receipt(GhiChu='ế'*255)
        data['lines'][0]['KetQuaKiemTra'] = 'ế'*255
        receipt = self.create('incoming', data)
        self.mutate(self.manager, f'documents/incoming/{receipt}', dict(data, GhiChu='ế'*256), method='PUT', expected=400)
        self.assertEqual(next(p for p in self.state()['incoming'] if p['MaPN'] == receipt)['GhiChu'], 'ế'*255)

    def test_invalid_dates_and_timezone_conversion(self):
        for value in ['0001-01-01', '2026-02-30', '2026-10-11T00:00:00', 123]:
            self.mutate(self.manager, 'documents/incoming', self.receipt(NgayChungTu=value), expected=400)
        job = dict(MaBOM=1, MaNVNhan=2, SoLuongYeuCau=1)
        for value, expected in [('2026-10-11T23:30:00Z', '2026-10-12 06:30:00'), ('2026-10-11T10:00:00+09:00', '2026-10-11 08:00:00'), ('2026-10-11T10:00:00', '2026-10-11 10:00:00')]:
            ident = self.create('jobs', dict(job, HanMongMuon=value))
            self.assertEqual(next(j for j in self.state()['jobs'] if j['MaYC'] == ident)['HanMongMuon'], expected)
        for value in ['0001-01-01T00:00:00', '9999-12-31T23:59:00-12:00', 'invalid', {'bad': True}]:
            self.mutate(self.manager, 'documents/jobs', dict(job, HanMongMuon=value), expected=400)
        self.assertEqual(self.manager.get('/api/report?from=0001-01-01&to=2027-01-01').status_code, 400)

    def test_failed_account_switch_removes_previous_session(self):
        token = self.manager.get('/api/session').json['csrf']
        response = self.manager.post('/api/login', json=dict(username='admin', password='wrong'), headers={'X-CSRF-Token': token})
        self.assertEqual(response.status_code, 401)
        self.assertIsNone(self.manager.get('/api/session').json['user'])
        self.assertEqual(self.manager.get('/api/state').status_code, 401)
        response = self.manager.post('/api/login', json=dict(username='quanly', password='Demo@12345'), headers={'X-CSRF-Token': token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.manager.get('/api/state').status_code, 200)

    def test_password_preserves_leading_and_trailing_spaces(self):
        password = '  Spaced@12345  '
        self.mutate(self.admin, 'accounts/3', dict(VaiTro='NHAN_VIEN', TrangThai='HOAT_DONG', password=password), method='PUT')
        client = self.app.test_client()
        token = client.get('/api/session').json['csrf']
        response = client.post('/api/login', json=dict(username='nhanvien_khac', password=password), headers={'X-CSRF-Token': token})
        self.assertEqual(response.status_code, 200)
        token = response.json['csrf']
        response = client.post('/api/login', json=dict(username='nhanvien_khac', password=password.strip()), headers={'X-CSRF-Token': token})
        self.assertEqual(response.status_code, 401)
        self.assertIsNone(client.get('/api/session').json['user'])

    def test_business_error_is_accented_and_does_not_change_stock(self):
        job = self.job(qty=1)
        self.action('jobs', job, 'cancel', reason='Kiểm thử hủy')
        before = self.state()
        error = self.action('jobs', job, 'receive', self.employee, expected=409)['error']
        self.assertIn('Yêu cầu', error)
        self.assertNotIn('Khong phai', error)
        self.assertEqual(self.state()['inventory'], before['inventory'])

    def test_accept_reject_and_approve_reject_races_have_one_winner(self):
        job = self.job(qty=1)
        self.action('outgoing', self.allocate(job, cpu=1, ram=2), 'approve')
        result = self.result(job, good=1, faulty=0)
        shipment = self.shipment()
        clients = [self.login('quanly'), self.login('quanly')]
        for kind, ident, first, done in [('results', result, 'accept', 'DA_TIEP_NHAN'), ('outgoing', shipment, 'approve', 'DA_THUC_HIEN')]:
            before = self.state()
            barrier = threading.Barrier(2)
            def perform(index):
                client = clients[index]
                token = client.get('/api/session').json['csrf']
                barrier.wait()
                action = first if index == 0 else 'reject'
                return client.post(f'/api/actions/{kind}/{ident}/{action}', json={'reason': 'Kiểm thử đồng thời'}, headers={'X-CSRF-Token': token})
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(perform, range(2)))
            self.assertEqual(sorted(r.status_code for r in responses), [200, 409], [r.json for r in responses])
            after = self.state()
            key = 'MaKQ' if kind == 'results' else 'MaPX'
            self.assertEqual(next(r for r in after[kind] if r[key] == ident)['TrangThai'], done if responses[0].status_code == 200 else 'TU_CHOI')
            self.assertEqual(len(after['ledger'])-len(before['ledger']), 1 if responses[0].status_code == 200 else 0)

    def test_csv_neutralizes_formulas_hidden_after_control_characters(self):
        c = connect(admin=True, database=self.database)
        try:
            for value in ['=1+1', '\t=1+1', '\r@SUM(1)', '  +1', 'Tên sản phẩm hợp lệ']:
                execute(c, 'UPDATE SAN_PHAM SET TenSP=%s WHERE MaSP=1', (value,))
                response = self.manager.get('/api/report?from=2026-01-01&to=2027-01-01&format=csv')
                self.assertEqual(response.status_code, 200)
                records = list(csv.DictReader(io.StringIO(response.data.decode('utf-8-sig'))))
                name = next(r['TenSP'] for r in records if r['SKU'] == 'CPU-001')
                self.assertEqual(name, value if value.startswith('Tên') else "'"+value)
        finally:
            c.close()


class DiagnosticCoverage(unittest.TestCase):
    def test_all_legacy_business_diagnostics_have_vietnamese_messages(self):
        messages = set(re.findall(r"MESSAGE_TEXT='([^']+)'", SCHEMA.read_text(encoding='utf-8')))
        self.assertEqual(messages-set(SQL_ERRORS), set())
        self.assertTrue(all(message.endswith('.') and not message.isascii() for message in SQL_ERRORS.values()))


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite(AuditEdges(name) for name in sorted(AuditEdges.__dict__) if name.startswith('test_'))
    suite.addTests(loader.loadTestsFromTestCase(DiagnosticCoverage))
    return suite


if __name__ == '__main__':
    unittest.main(verbosity=2)
