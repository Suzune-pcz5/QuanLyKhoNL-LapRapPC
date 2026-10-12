"""Boundary and concurrency checks against disposable MySQL databases."""
import unittest
from concurrent.futures import ThreadPoolExecutor

from test_integration import WarehouseTests
from db import call, connect


class SidecaseTests(WarehouseTests):
    def receipt(self, **changes):
        data = dict(MaNCC=1, NgayChungTu='2026-10-10', lines=[dict(MaSP=1, MaViTri=1, SoLuongNhan=1, SoLuongLoi=0, DonGiaNhap='1.00')])
        data.update(changes)
        return data

    def test_receipt_rejects_bad_numbers_and_duplicate_lines_atomically(self):
        before = self.state()
        for field, value in [('SoLuongNhan', 0), ('SoLuongNhan', -1), ('SoLuongNhan', 1.5), ('SoLuongNhan', True), ('SoLuongNhan', 2147483648), ('SoLuongLoi', 2), ('DonGiaNhap', '-1'), ('DonGiaNhap', 'NaN'), ('DonGiaNhap', '1.001')]:
            with self.subTest(field=field, value=value):
                data = self.receipt()
                data['lines'][0][field] = value
                self.mutate(self.manager, 'documents/incoming', data, expected=400)
        data = self.receipt()
        data['lines'] *= 2
        self.mutate(self.manager, 'documents/incoming', data, expected=400)
        after = self.state()
        self.assertEqual(before['inventory'], after['inventory'])
        self.assertEqual(len(before['incoming']), len(after['incoming']))

    def test_bad_json_missing_and_unknown_ids_are_handled(self):
        csrf = self.manager.get('/api/session').json['csrf']
        for data in [[], 'bad', None, 123]:
            with self.subTest(data=data):
                response = self.manager.post('/api/documents/incoming', json=data, headers={'X-CSRF-Token': csrf})
                self.assertEqual(response.status_code, 400, response.json)
        self.action('incoming', 2147483647, 'commit', expected=404)
        self.mutate(self.manager, 'documents/unknown', {}, expected=404)

    def test_bom_rejects_empty_duplicate_and_finished_goods_components(self):
        data = dict(MaSPThanhPham=3, PhienBan=2, TenCauHinh='QA', lines=[])
        self.mutate(self.manager, 'documents/bom', data, expected=400)
        for lines in [[dict(MaSPLinhKien=1, DinhMuc=1)] * 2, [dict(MaSPLinhKien=3, DinhMuc=1)], [dict(MaSPLinhKien=1, DinhMuc=0)]]:
            with self.subTest(lines=lines):
                self.mutate(self.manager, 'documents/bom', {**data, 'lines': lines}, expected=400)

    def test_cannot_send_allocation_before_accepting_job(self):
        yc = self.create('jobs', dict(MaBOM=1, SoLuongYeuCau=3, MaNVNhan=2))
        self.action('jobs', yc, 'assign')
        px = self.create('outgoing', dict(LoaiXuat='CAP_PHAT', MaYCLapRap=yc, lines=[dict(MaSP=1, MaViTri=1, SoLuongXuat=3), dict(MaSP=2, MaViTri=1, SoLuongXuat=6)]), self.employee)
        self.action('outgoing', px, 'send', self.employee, expected=409)

    def test_allocation_must_equal_snapshot_exactly(self):
        yc = self.job()
        before = self.state()['inventory']
        for cpu, ram in [(2, 6), (4, 6), (3, 5), (3, 7)]:
            with self.subTest(cpu=cpu, ram=ram):
                px = self.create('outgoing', dict(LoaiXuat='CAP_PHAT', MaYCLapRap=yc, lines=[dict(MaSP=1, MaViTri=1, SoLuongXuat=cpu), dict(MaSP=2, MaViTri=1, SoLuongXuat=ram)]), self.employee)
                self.action('outgoing', px, 'send', self.employee, expected=409)
        self.assertEqual(before, self.state()['inventory'])

    def test_two_draft_allocations_only_one_can_be_pending(self):
        yc = self.job()
        data = dict(LoaiXuat='CAP_PHAT', MaYCLapRap=yc, lines=[dict(MaSP=1, MaViTri=1, SoLuongXuat=3), dict(MaSP=2, MaViTri=1, SoLuongXuat=6)])
        a = self.create('outgoing', data, self.employee)
        b = self.create('outgoing', data, self.employee)
        self.action('outgoing', a, 'send', self.employee)
        self.action('outgoing', b, 'send', self.employee, expected=409)
        self.action('outgoing', a, 'reject', reason='QA')
        self.action('outgoing', b, 'send', self.employee)
        self.action('outgoing', b, 'approve')
        self.assertEqual(self.quantity('CPU-001')['SoLuongThucTe'], 4)

    def test_split_allocation_across_locations(self):
        loc = self.mutate(self.admin, 'catalog/locations', dict(MaViTriHienThi='QA-CPU', TrangThai='HOAT_DONG'))['id']
        pn = self.create('incoming', self.receipt(lines=[dict(MaSP=1, MaViTri=loc, SoLuongNhan=1, SoLuongLoi=0, DonGiaNhap=1)]))
        self.action('incoming', pn, 'commit')
        yc = self.job()
        px = self.create('outgoing', dict(LoaiXuat='CAP_PHAT', MaYCLapRap=yc, lines=[dict(MaSP=1, MaViTri=1, SoLuongXuat=2), dict(MaSP=1, MaViTri=loc, SoLuongXuat=1), dict(MaSP=2, MaViTri=1, SoLuongXuat=6)]), self.employee)
        self.action('outgoing', px, 'send', self.employee)
        self.action('outgoing', px, 'approve')
        self.assertEqual(self.quantity('CPU-001', loc)['SoLuongThucTe'], 0)
        self.assertEqual(self.quantity('CPU-001')['SoLuongThucTe'], 5)

    def test_reject_result_does_not_consume_material_or_create_receipt(self):
        yc = self.job()
        self.action('outgoing', self.allocate(yc), 'approve')
        kq = self.result(yc)
        before = self.state()
        self.action('results', kq, 'reject', reason='QA: kiểm lại chất lượng')
        after = self.state()
        self.assertEqual(before['inventory'], after['inventory'])
        self.assertEqual(len(before['incoming']), len(after['incoming']))
        self.action('results', self.result(yc), 'accept')
        self.assertEqual(next(j for j in self.state()['jobs'] if j['MaYC'] == yc)['TrangThai'], 'HOAN_THANH')

    def test_partial_results_then_completion_and_same_good_faulty_location(self):
        yc = self.job()
        self.action('outgoing', self.allocate(yc), 'approve')
        self.action('results', self.result(yc, 1, 0), 'accept')
        self.assertEqual(next(j for j in self.state()['jobs'] if j['MaYC'] == yc)['TrangThai'], 'DANG_LAP_RAP')
        kq = self.create('results', dict(MaYC=yc, SoLuongDat=1, SoLuongLoi=1, MaViTriDat=2, MaViTriLoi=2), self.employee)
        self.action('results', kq, 'send', self.employee)
        self.action('results', kq, 'accept')
        self.assertEqual(self.quantity('PC-001', 2)['SoLuongThucTe'], 4)
        self.assertEqual(self.quantity('PC-001', 2)['SoLuongKhongBan'], 1)
        self.assertEqual(next(j for j in self.state()['jobs'] if j['MaYC'] == yc)['TrangThai'], 'HOAN_THANH')

    def test_concurrent_results_cannot_exceed_plan(self):
        yc = self.job()
        self.action('outgoing', self.allocate(yc), 'approve')
        a, b = self.result(yc, 2, 0), self.result(yc, 2, 0)
        def accept(ident):
            c = connect(database=self.database)
            try:
                call(c, 'sp_tiep_nhan_ket_qua', (1, ident))
                return True
            except Exception:
                return False
            finally:
                c.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            accepted = list(pool.map(accept, [a, b]))
        self.assertEqual(sum(accepted), 1)
        self.assertEqual(next(j for j in self.state()['jobs'] if j['MaYC'] == yc)['accepted'], 2)

    def test_product_disabled_after_sending_blocks_approval(self):
        px = self.shipment()
        p = next(p for p in self.state(self.admin)['products'] if p['MaSP'] == 3)
        self.mutate(self.admin, 'catalog/products/3', {**p, 'TrangThai': 'NGUNG'}, method='PUT')
        before = self.state()['inventory']
        self.action('outgoing', px, 'approve', expected=409)
        self.assertEqual(before, self.state()['inventory'])

    def test_role_change_and_password_change_invalidate_permissions(self):
        self.mutate(self.admin, 'accounts/1', dict(VaiTro='NHAN_VIEN', TrangThai='HOAT_DONG'), method='PUT')
        self.mutate(self.manager, 'documents/incoming', self.receipt(), expected=403)
        self.mutate(self.admin, 'accounts/2', dict(VaiTro='NHAN_VIEN', TrangThai='HOAT_DONG', password='Changed@12345'), method='PUT')
        self.assertEqual(self.employee.get('/api/state').status_code, 401)
        client = self.app.test_client()
        csrf = client.get('/api/session').json['csrf']
        r = client.post('/api/login', json=dict(username='nhanvien', password='Changed@12345'), headers={'X-CSRF-Token': csrf})
        self.assertEqual(r.status_code, 200, r.json)

    def test_report_invalid_periods_filters_and_csv_formula_escape(self):
        for period in [('bad', '2027-01-01'), ('2027-01-01', '2026-01-01'), ('2026-01-01', '2026-01-01'), ('2026-01-01T00:00:00Z', '2027-01-01T00:00:00Z')]:
            with self.subTest(period=period):
                r = self.manager.get('/api/report', query_string={'from': period[0], 'to': period[1]})
                self.assertEqual(r.status_code, 400, r.json)
        p = next(p for p in self.state(self.admin)['products'] if p['MaSP'] == 1)
        self.mutate(self.admin, 'catalog/products/1', {**p, 'TenSP': '=1+1'}, method='PUT')
        csv = self.manager.get('/api/report?from=2026-01-01&to=2027-01-01&format=csv').data.decode('utf-8-sig')
        self.assertIn("'=1+1", csv)
        r = self.manager.get('/api/report?from=2026-01-01&to=2027-01-01&type=THANH_PHAM&location=2')
        self.assertTrue(all(x['LoaiMatHang'] == 'THANH_PHAM' and x['MaViTri'] == 2 for x in r.json['rows']))

def load_tests(loader, tests, pattern):
    return unittest.TestSuite(SidecaseTests(name) for name in sorted(SidecaseTests.__dict__) if name.startswith('test_'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
