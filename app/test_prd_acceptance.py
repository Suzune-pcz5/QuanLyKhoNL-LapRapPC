"""Executable AT01-AT12 from PRD v1.0, against disposable real databases."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pymysql

from test_integration import WarehouseTests
from db import call, connect, execute, one, rows, settings
import manage

class PRDAcceptance(WarehouseTests):
    def test_AT01_received_20_RAM_2_faulty(self):
        data = dict(MaNCC=1, NgayChungTu='2026-10-10', lines=[dict(MaSP=2, MaViTri=1, SoLuongNhan=20, SoLuongLoi=2, DonGiaNhap='400000', KetQuaKiemTra='Đủ 20 RAM, 2 lỗi')])
        before = self.quantity('RAM-001')
        receipt = self.create('incoming', data)
        self.assertEqual(self.quantity('RAM-001'), before)
        self.action('incoming', receipt, 'commit')
        after = self.quantity('RAM-001')
        self.assertEqual((after['SoLuongThucTe']-before['SoLuongThucTe'], after['SoLuongKhongBan']-before['SoLuongKhongBan'], after['SoLuongKhaDung']-before['SoLuongKhaDung']), (20,2,18))

    def test_AT02_snapshot_3_CPU_6_RAM_survives_new_BOM(self):
        job = self.job()
        before = next(j for j in self.state()['jobs'] if j['MaYC']==job)['needs']
        self.assertEqual({n['SKU']:n['SoLuongCan'] for n in before}, {'CPU-001':3,'RAM-001':6})
        bom = self.create('bom', dict(MaSPThanhPham=3, PhienBan=2, TenCauHinh='PRD phiên bản mới', lines=[dict(MaSPLinhKien=1,DinhMuc=1),dict(MaSPLinhKien=2,DinhMuc=3)]))
        self.action('bom', bom, 'publish')
        self.assertEqual(next(j for j in self.state()['jobs'] if j['MaYC']==job)['needs'], before)
        self.assertEqual(len([b for b in self.state()['bom'] if b['MaSPThanhPham']==3 and b['TrangThai']=='DANG_AP_DUNG']), 1)

    def test_AT03_ownership_and_employee_admin_approval_blocked(self):
        job = self.job()
        before = self.state()
        self.action('jobs', job, 'receive', self.other, expected=403)
        outgoing = self.allocate(job)
        for client in (self.employee, self.other, self.admin):
            self.action('outgoing', outgoing, 'approve', client, expected=403)
        self.assertEqual(self.state()['inventory'], before['inventory'])
        self.assertNotIn(job, [j['MaYC'] for j in self.state(self.other)['jobs']])
        self.assertEqual(next(p for p in self.state()['outgoing'] if p['MaPX']==outgoing)['TrangThai'], 'CHO_DUYET')

    def test_AT04_short_RAM_rolls_back_CPU_and_whole_document(self):
        bom = self.create('bom',dict(MaSPThanhPham=3,PhienBan=2,TenCauHinh='PRD thiếu RAM',lines=[dict(MaSPLinhKien=1,DinhMuc=1),dict(MaSPLinhKien=2,DinhMuc=10)]))
        self.action('bom',bom,'publish')
        job = self.job(bom=bom)
        outgoing = self.allocate(job, ram=30)
        before = self.state()
        self.action('outgoing',outgoing,'approve',expected=409)
        after = self.state()
        self.assertEqual(after['inventory'],before['inventory'])
        self.assertEqual(after['ledger'],before['ledger'])
        self.assertEqual(next(j for j in after['jobs'] if j['MaYC']==job)['TrangThai'],'DA_GIAO')

    def test_AT05_repeated_receipt_issuance_acceptance_are_idempotent(self):
        receipt = self.create('incoming',dict(MaNCC=1,NgayChungTu='2026-10-10',lines=[dict(MaSP=1,MaViTri=1,SoLuongNhan=1,SoLuongLoi=0,DonGiaNhap=1)]))
        self.action('incoming',receipt,'commit')
        before = self.state()
        self.assertEqual(self.action('incoming',receipt,'commit')['result'][0]['KetQua'],'DA_XU_LY_TRUOC')
        self.assertEqual((self.state()['inventory'],self.state()['ledger']), (before['inventory'],before['ledger']))
        job = self.job(); outgoing = self.allocate(job);self.action('outgoing',outgoing,'approve')
        before = self.state()
        self.assertEqual(self.action('outgoing',outgoing,'approve')['result'][0]['KetQua'],'DA_XU_LY_TRUOC')
        self.assertEqual((self.state()['inventory'],self.state()['ledger']), (before['inventory'],before['ledger']))
        result = self.result(job);self.action('results',result,'accept')
        before = self.state()
        self.assertEqual(self.action('results',result,'accept')['result'][0]['KetQua'],'DA_XU_LY_TRUOC')
        after = self.state()
        self.assertEqual((after['inventory'],after['ledger'],len(after['incoming'])),(before['inventory'],before['ledger'],len(before['incoming'])))

    def test_AT06_accept_2_good_1_faulty_without_second_component_deduction(self):
        job = self.job();self.action('outgoing',self.allocate(job),'approve')
        before = [r for r in self.state()['inventory'] if r['LoaiMatHang']=='NGUYEN_LIEU']
        result = self.result(job);self.action('results',result,'accept')
        data = self.state()
        self.assertEqual([r for r in data['inventory'] if r['LoaiMatHang']=='NGUYEN_LIEU'], before)
        self.assertEqual(self.quantity('PC-001',2)['SoLuongThucTe'],3)
        self.assertEqual((self.quantity('PC-001',3)['SoLuongThucTe'],self.quantity('PC-001',3)['SoLuongKhongBan']),(2,2))
        internal = next(r for r in data['incoming'] if r['MaNguonKetQua']==result)
        self.assertEqual(internal['TrangThai'],'DA_GHI_NHAN')
        self.assertTrue(all(r['DonGiaNhap'] is None for r in internal['lines']))
        self.action('incoming', internal['MaPN'], 'commit', expected=409)
        self.assertTrue(all(r['SoLuongCon']==0 for r in next(j for j in data['jobs'] if j['MaYC']==job)['materials']))

    def test_AT07_multiple_results_cannot_exceed_plan(self):
        job=self.job();self.action('outgoing',self.allocate(job),'approve')
        self.action('results',self.result(job,2,0),'accept')
        self.assertEqual(next(j for j in self.state()['jobs'] if j['MaYC']==job)['TrangThai'],'DANG_LAP_RAP')
        result=self.result(job,2,0);before=self.state()
        self.action('results',result,'accept',expected=409)
        after=self.state()
        self.assertEqual((after['inventory'],len(after['incoming'])),(before['inventory'],len(before['incoming'])))
        self.action('results',self.result(job,0,1),'accept')
        self.assertEqual(next(j for j in self.state()['jobs'] if j['MaYC']==job)['TrangThai'],'HOAN_THANH')

    def test_AT08_rejection_preserves_stock_history_and_allows_new_request(self):
        job=self.job();outgoing=self.allocate(job);before=self.state()
        self.action('outgoing',outgoing,'reject',reason='PRD sai phân bổ')
        data=self.state()
        self.assertEqual(data['inventory'],before['inventory'])
        old=next(p for p in data['outgoing'] if p['MaPX']==outgoing)
        self.assertEqual((old['TrangThai'],old['LyDoTuChoi']),('TU_CHOI','PRD sai phân bổ'))
        replacement=self.allocate(job);self.assertNotEqual(outgoing,replacement)
        self.action('outgoing',replacement,'approve')
        self.assertEqual(next(p for p in self.state()['outgoing'] if p['MaPX']==outgoing)['TrangThai'],'TU_CHOI')

    def test_AT09_two_shipments_compete_for_last_good_PC(self):
        outgoing=[self.shipment(),self.shipment()]
        def approve(ident):
            c=connect(database=self.database)
            try: call(c,'sp_duyet_xuat',(1,ident));return True
            except pymysql.MySQLError:return False
            finally:c.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(approve,outgoing)),1)
        self.assertEqual(self.quantity('PC-001',2)['SoLuongKhaDung'],0)
        bad=self.create('outgoing',dict(LoaiXuat='THANH_PHAM',TenNguoiNhan='PRD',lines=[dict(MaSP=3,MaViTri=3,SoLuongXuat=1)]),self.employee)
        self.action('outgoing',bad,'send',self.employee);before=self.state()['inventory']
        self.action('outgoing',bad,'approve',expected=409)
        self.assertEqual(self.state()['inventory'],before)

    def test_AT10_period_reports_boundary_and_ledger_reconciliation(self):
        WarehouseTests.test_period_reports_csv_and_ledger_reconciliation(self)
        for start,end in [('2026-10-01','2026-11-01'),('2026-10-01','2027-01-01'),('2026-01-01','2027-01-01')]:
            response=self.manager.get('/api/report',query_string={'from':start,'to':end})
            self.assertEqual(response.status_code,200,response.json)
            self.assertTrue(all(r['TonDauKy']+r['NhapTrongKy']-r['XuatTrongKy']==r['TonCuoiKy'] and r['TonCuoiKy']-r['KhongBanCuoiKy']==r['KhaDungCuoiKy'] for r in response.json['rows']))

    def test_AT11_final_documents_and_ledger_are_immutable(self):
        WarehouseTests.test_draft_edit_delete_and_freeze(self)
        WarehouseTests.test_restricted_database_privileges(self)
        before=self.state()['ledger']
        self.mutate(self.manager,'documents/ledger/1',{},method='PUT',expected=404)
        self.mutate(self.admin,'documents/ledger/1',{},method='DELETE',expected=404)
        self.assertEqual(self.state()['ledger'],before)

    def test_AT12_backup_restores_tables_data_routines_triggers_and_business(self):
        before_c=connect(admin=True,database=self.database)
        try:
            before=manage.database_snapshot(before_c,self.database)
            prior={r['Database'] for r in rows(before_c,'SHOW DATABASES') if r['Database'].startswith('mrp_restore_')}
            with patch.object(manage,'settings',return_value=dict(settings(),database=self.database)):
                filename=self.mutate(self.admin,'backup')['file']
                try:
                    result=self.mutate(self.admin,'restore-test',dict(file=filename))['result']
                    self.assertEqual((result['tables'],result['views'],result['routines'],result['triggers']),(17,4,16,19))
                    self.assertTrue(result['data_matched'] and result['login_verified'] and result['transaction_verified'])
                    self.assertEqual(manage.database_snapshot(before_c,self.database),before)
                    self.assertEqual({r['Database'] for r in rows(before_c,'SHOW DATABASES') if r['Database'].startswith('mrp_restore_')},prior)
                finally:
                    (manage.BASE/'backups'/filename).unlink(missing_ok=True)
        finally:
            before_c.close()


def load_tests(loader, tests, pattern):
    # The inherited integration tests already run in test_integration.
    return unittest.TestSuite(PRDAcceptance(name) for name in sorted(PRDAcceptance.__dict__) if name.startswith('test_AT'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
