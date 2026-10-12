"""Integration tests against real MySQL in disposable, isolated databases."""
import secrets
import unittest
from concurrent.futures import ThreadPoolExecutor

import pymysql

from db import call, connect, execute, one, rows, settings
from manage import drop_temporary_database, initialize
from server import create_app


class WarehouseTests(unittest.TestCase):
    def setUp(self):
        self.database = 'mrp_test_' + secrets.token_hex(6)
        self.addCleanup(self.cleanup_database)
        initialize(self.database)
        self.app = create_app({'TESTING': True, 'DATABASE': self.database})
        self.addCleanup(lambda: self.app.session_interface.store.path.unlink(missing_ok=True))
        self.manager = self.login('quanly')
        self.employee = self.login('nhanvien')
        self.other = self.login('nhanvien_khac')
        self.admin = self.login('admin')

    def cleanup_database(self):
        # Runs even when setUp fails after creating a database or granting access.
        c = connect(admin=True)
        try:
            drop_temporary_database(c, self.database)
        finally:
            c.close()

    def login(self, username):
        client = self.app.test_client()
        csrf = client.get('/api/session').json['csrf']
        r = client.post('/api/login', json={'username': username, 'password':'Demo@12345'}, headers={'X-CSRF-Token':csrf})
        self.assertEqual(r.status_code,200,r.json)
        return client

    def mutate(self, client, path, data=None, method='POST', expected=200):
        csrf = client.get('/api/session').json['csrf']
        r = client.open('/api/'+path, method=method, json=data or {}, headers={'X-CSRF-Token':csrf})
        self.assertEqual(r.status_code,expected,r.json)
        return r.json

    def state(self, client=None):
        r = (client or self.manager).get('/api/state')
        self.assertEqual(r.status_code,200,r.json)
        return r.json

    def action(self, kind, ident, action, client=None, expected=200, **data):
        return self.mutate(client or self.manager,f'actions/{kind}/{ident}/{action}',data,expected=expected)

    def create(self, kind, data, client=None):
        return self.mutate(client or self.manager,'documents/'+kind,data)['id']

    def quantity(self, sku, location=1):
        return next(r for r in self.state()['inventory'] if r['SKU']==sku and r['MaViTri']==location)

    def job(self, qty=3, bom=1):
        ident=self.create('jobs',dict(MaBOM=bom,SoLuongYeuCau=qty,MaNVNhan=2))
        self.action('jobs',ident,'assign')
        self.action('jobs',ident,'receive',self.employee)
        return ident

    def allocate(self, yc, cpu=3, ram=6):
        ident=self.create('outgoing',dict(LoaiXuat='CAP_PHAT',MaYCLapRap=yc,lines=[dict(MaSP=1,MaViTri=1,SoLuongXuat=cpu),dict(MaSP=2,MaViTri=1,SoLuongXuat=ram)]),self.employee)
        self.action('outgoing',ident,'send',self.employee)
        return ident

    def result(self, yc, good=2, faulty=1):
        ident=self.create('results',dict(MaYC=yc,SoLuongDat=good,SoLuongLoi=faulty,MaViTriDat=2,MaViTriLoi=3),self.employee)
        self.action('results',ident,'send',self.employee)
        return ident

    def shipment(self):
        ident=self.create('outgoing',dict(LoaiXuat='THANH_PHAM',TenNguoiNhan='Bộ phận bán hàng',lines=[dict(MaSP=3,MaViTri=2,SoLuongXuat=1)]),self.employee)
        self.action('outgoing',ident,'send',self.employee)
        return ident

    def test_baseline_and_no_secrets_in_state(self):
        d=self.state(); self.assertEqual(len(d['inventory']),4)
        self.assertEqual(self.quantity('CPU-001')['SoLuongThucTe'],7)
        self.assertEqual(self.quantity('RAM-001')['SoLuongKhongBan'],2)
        self.assertNotIn('MatKhauBam',str(d))
        c=connect(admin=True,database=self.database)
        self.assertEqual(one(c,'SELECT COUNT(*) n FROM information_schema.tables WHERE table_schema=%s AND table_type=%s',(self.database,'BASE TABLE'))['n'],17)
        c.close()

    def test_full_receipt_assembly_shipment_flow(self):
        pn=self.create('incoming',dict(MaNCC=1,NgayChungTu='2026-10-10',lines=[dict(MaSP=1,MaViTri=1,SoLuongNhan=10,SoLuongLoi=0,DonGiaNhap='1800000'),dict(MaSP=2,MaViTri=1,SoLuongNhan=20,SoLuongLoi=2,DonGiaNhap='400000')]))
        self.assertEqual(self.quantity('CPU-001')['SoLuongThucTe'],7)
        self.action('incoming',pn,'commit')
        yc=self.job();px=self.allocate(yc);self.action('outgoing',px,'approve')
        before=self.quantity('CPU-001')['SoLuongThucTe']
        kq=self.result(yc);self.action('results',kq,'accept')
        self.assertEqual(self.quantity('CPU-001')['SoLuongThucTe'],before)
        self.assertEqual(before,14)
        self.assertEqual(self.quantity('RAM-001')['SoLuongThucTe'],28)
        self.assertEqual(self.quantity('RAM-001')['SoLuongKhongBan'],4)
        self.action('outgoing',self.shipment(),'approve')
        self.assertEqual(self.quantity('PC-001',2)['SoLuongThucTe'],2)
        self.assertEqual(self.quantity('PC-001',3)['SoLuongKhongBan'],2)
        self.assertEqual(next(j for j in self.state()['jobs'] if j['MaYC']==yc)['TrangThai'],'HOAN_THANH')

    def test_idempotent_transitions(self):
        yc=self.job();px=self.allocate(yc);self.action('outgoing',px,'approve')
        before=self.state()['inventory'];count=len(self.state()['ledger'])
        b=self.action('outgoing',px,'approve')
        self.assertEqual(b['result'][0]['KetQua'],'DA_XU_LY_TRUOC')
        self.assertEqual(self.state()['inventory'],before);self.assertEqual(len(self.state()['ledger']),count)
        kq=self.result(yc);self.action('results',kq,'accept');before=self.state()['inventory']
        self.action('results',kq,'accept');self.assertEqual(self.state()['inventory'],before)
        pn=next(n['MaPN'] for n in self.state()['incoming'] if n['LoaiNhap']=='NCC')
        self.action('incoming',pn,'commit');self.assertEqual(self.state()['inventory'],before)

    def test_snapshot_unchanged_after_new_bom(self):
        yc=self.job();before=next(j for j in self.state()['jobs'] if j['MaYC']==yc)['needs']
        bom=self.create('bom',dict(MaSPThanhPham=3,PhienBan=2,TenCauHinh='V2',lines=[dict(MaSPLinhKien=1,DinhMuc=1),dict(MaSPLinhKien=2,DinhMuc=3)]))
        self.action('bom',bom,'publish')
        self.assertEqual(next(j for j in self.state()['jobs'] if j['MaYC']==yc)['needs'],before)

    def test_shortage_rolls_back_whole_issuance(self):
        bom=self.create('bom',dict(MaSPThanhPham=3,PhienBan=2,TenCauHinh='Nhiều RAM',lines=[dict(MaSPLinhKien=1,DinhMuc=1),dict(MaSPLinhKien=2,DinhMuc=10)]))
        self.action('bom',bom,'publish');yc=self.job(bom=bom);px=self.allocate(yc,ram=30)
        before=self.state()['inventory'];count=len(self.state()['ledger'])
        self.action('outgoing',px,'approve',expected=409)
        self.assertEqual(self.state()['inventory'],before);self.assertEqual(len(self.state()['ledger']),count)
        self.assertEqual(next(j for j in self.state()['jobs'] if j['MaYC']==yc)['TrangThai'],'DA_GIAO')

    def test_result_over_plan_blocked(self):
        yc=self.job();px=self.allocate(yc);self.action('outgoing',px,'approve')
        a=self.result(yc,2,0);b=self.result(yc,2,0)
        self.action('results',a,'accept');before=self.state()['inventory']
        self.action('results',b,'accept',expected=409);self.assertEqual(self.state()['inventory'],before)

    def test_rejection_preserves_stock_and_allows_new_issuance(self):
        yc=self.job();px=self.allocate(yc);before=self.state()['inventory']
        self.action('outgoing',px,'reject',reason='Sai vị trí');self.assertEqual(self.state()['inventory'],before)
        px2=self.allocate(yc);self.action('outgoing',px2,'approve')
        self.assertEqual(self.quantity('CPU-001')['SoLuongThucTe'],4)

    def test_cancel_only_before_allocation(self):
        yc=self.job();self.allocate(yc);self.action('jobs',yc,'cancel',reason='Đổi kế hoạch')
        self.assertEqual(next(j for j in self.state()['jobs'] if j['MaYC']==yc)['TrangThai'],'HUY')
        yc=self.job();px=self.allocate(yc);self.action('outgoing',px,'approve')
        self.action('jobs',yc,'cancel',expected=409,reason='Không hợp lệ')

    def test_faulty_pc_cannot_ship(self):
        px=self.create('outgoing',dict(LoaiXuat='THANH_PHAM',TenNguoiNhan='Test',lines=[dict(MaSP=3,MaViTri=3,SoLuongXuat=1)]),self.employee)
        self.action('outgoing',px,'send',self.employee);before=self.state()['inventory']
        self.action('outgoing',px,'approve',expected=409);self.assertEqual(self.state()['inventory'],before)

    def test_two_connections_compete_for_last_good_pc(self):
        a=self.shipment();b=self.shipment()
        def approve(ident):
            c=connect(database=self.database)
            try: call(c,'sp_duyet_xuat',(1,ident));return True
            except pymysql.MySQLError:return False
            finally:c.close()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(approve,[a,b]))
        self.assertEqual(sum(results),1)
        self.assertEqual(self.quantity('PC-001',2)['SoLuongKhaDung'],0)

    def test_auth_roles_csrf_and_id_tampering(self):
        anon=self.app.test_client();self.assertEqual(anon.get('/api/state').status_code,401)
        self.assertEqual(self.manager.post('/api/documents/jobs',json={}).status_code,403)
        yc=self.job()
        self.action('jobs',yc,'receive',self.other,expected=403)
        self.action('jobs',yc,'assign',self.employee,expected=403)
        self.action('jobs',yc,'assign',self.admin,expected=403)
        self.assertNotIn(yc,[j['MaYC'] for j in self.state(self.other)['jobs']])
        self.assertEqual(self.employee.get('/api/report?from=2026-01-01&to=2027-01-01').status_code,403)

    def test_locked_account_existing_session_invalidated(self):
        self.mutate(self.admin,'accounts/2',dict(VaiTro='NHAN_VIEN',TrangThai='KHOA'),method='PUT')
        self.assertEqual(self.employee.get('/api/state').status_code,401)

    def test_client_cannot_forge_status_or_identity(self):
        yc=self.create('jobs',dict(MaBOM=1,SoLuongYeuCau=3,MaNVNhan=2,MaNVGiao=3,TrangThai='HOAN_THANH'))
        r=next(j for j in self.state()['jobs'] if j['MaYC']==yc)
        self.assertEqual(r['TrangThai'],'NHAP');self.assertEqual(r['MaNVGiao'],1)

    def test_draft_edit_delete_and_freeze(self):
        b=dict(MaNCC=1,NgayChungTu='2026-10-10',lines=[dict(MaSP=1,MaViTri=1,SoLuongNhan=5,SoLuongLoi=0,DonGiaNhap=1)])
        pn=self.create('incoming',b);b['lines'][0]['SoLuongNhan']=8
        self.mutate(self.manager,f'documents/incoming/{pn}',b,method='PUT');self.action('incoming',pn,'commit')
        self.assertEqual(self.quantity('CPU-001')['SoLuongThucTe'],15)
        self.mutate(self.manager,f'documents/incoming/{pn}',b,method='PUT',expected=409)
        self.mutate(self.manager,f'documents/incoming/{pn}',method='DELETE',expected=409)
        temp=self.create('incoming',b);self.mutate(self.manager,f'documents/incoming/{temp}',method='DELETE')

    def test_restricted_database_privileges(self):
        c=connect(database=self.database)
        for sql in ["UPDATE TON_KHO SET SoLuongThucTe=999","DELETE FROM BIEN_DONG_KHO","INSERT INTO CT_NHU_CAU_LAP_RAP VALUES(1,1,99,99)","UPDATE PHIEU_XUAT SET TrangThai='NHAP'","CALL sp_ghi_bien_dong(1,1,999,0,'NHAP_NCC',1,NULL,1)"]:
            with self.assertRaises(pymysql.MySQLError):execute(c,sql)
            c.rollback()
        c.close()

    def test_period_reports_csv_and_ledger_reconciliation(self):
        r=self.manager.get('/api/report?from=2026-01-01&to=2027-01-01');self.assertEqual(r.status_code,200,r.json)
        for line in r.json['rows']:
            self.assertEqual(line['TonDauKy']+line['NhapTrongKy']-line['XuatTrongKy'],line['TonCuoiKy'])
        d=self.state();c=connect(database=self.database)
        end=one(c,'SELECT MAX(ThoiDiem) t FROM BIEN_DONG_KHO')['t']
        from datetime import timedelta
        a=call(c,'sp_bao_cao_kho',(1,end,end+timedelta(seconds=1)))
        b=call(c,'sp_bao_cao_kho',(1,end-timedelta(days=1),end))
        last=one(c,'SELECT * FROM BIEN_DONG_KHO WHERE ThoiDiem=%s',(end,))
        self.assertTrue(any(int(x['XuatTrongKy'])==1 for x in a))
        self.assertTrue(any(int(x['TonCuoiKy'])==2 for x in b if x['MaSP']==3 and x['MaViTri']==2))
        for inv in d['inventory']:
            sums=one(c,'SELECT SUM(DeltaThucTe) tt,SUM(DeltaKhongBan) loi FROM BIEN_DONG_KHO WHERE MaSP=%s AND MaViTri=%s',(inv['MaSP'],inv['MaViTri']))
            self.assertEqual(sums['tt'],inv['SoLuongThucTe']);self.assertEqual(sums['loi'],inv['SoLuongKhongBan'])
        c.close()
        csv=self.manager.get('/api/report?from=2026-01-01&to=2027-01-01&format=csv')
        self.assertEqual(csv.status_code,200);self.assertTrue(csv.data.startswith(b'\xef\xbb\xbf'));self.assertIn('attachment',csv.headers['Content-Disposition'])

    def test_catalog_identity_and_accounts(self):
        p=self.state(self.admin)['products'][0]
        self.mutate(self.admin,'catalog/products/1',{**p,'SKU':'CHANGED'},method='PUT',expected=409)
        nv=self.mutate(self.admin,'catalog/employees',dict(HoTen='Test Account',TrangThai='DANG_LAM'))['id']
        tk=self.mutate(self.admin,'accounts',dict(MaNV=nv,TenDangNhap='test_new',password='Test@12345',VaiTro='NHAN_VIEN'))['id']
        self.mutate(self.admin,f'accounts/{tk}',method='DELETE')
        self.mutate(self.admin,'accounts/2',method='DELETE',expected=409)
        self.mutate(self.admin,'accounts/4',dict(VaiTro='NHAN_VIEN',TrangThai='HOAT_DONG'),method='PUT',expected=400)

    def test_inactive_location_blocks_approval(self):
        px=self.shipment();loc=self.state(self.admin)['locations'][1]
        self.mutate(self.admin,'catalog/locations/2',{**loc,'TrangThai':'NGUNG'},method='PUT')
        before=self.state()['inventory'];self.action('outgoing',px,'approve',expected=409)
        self.assertEqual(self.state()['inventory'],before)

    def test_atomic_draft_save_rolls_back_invalid_detail(self):
        before=len(self.state()['incoming'])
        b=dict(MaNCC=1,NgayChungTu='2026-10-10',lines=[dict(MaSP=1,MaViTri=1,SoLuongNhan=5,SoLuongLoi=0,DonGiaNhap=1),dict(MaSP=2,MaViTri=1,SoLuongNhan=1,SoLuongLoi=2,DonGiaNhap=1)])
        self.mutate(self.manager,'documents/incoming',b,expected=400)
        self.assertEqual(len(self.state()['incoming']),before)
        self.assertEqual(self.quantity('CPU-001')['SoLuongThucTe'],7)

    def test_label_cleanup_preserves_history_and_passwords(self):
        from seed_labels import normalize_seed_labels
        c=connect(admin=True,database=self.database)
        tables=['TON_KHO','BIEN_DONG_KHO','BOM','CT_BOM','PHIEU_XUAT','CT_PHIEU_XUAT','CT_NHU_CAU_LAP_RAP']
        before={t:rows(c,f'SELECT * FROM {t}') for t in tables}
        accounts=rows(c,'SELECT MaTK,MaNV,MatKhauBam,VaiTro,TrangThai,NgayTao FROM TAI_KHOAN ORDER BY MaTK')
        execute(c,"UPDATE TAI_KHOAN SET TenDangNhap='demo_quanly' WHERE MaTK=1")
        execute(c,"UPDATE SAN_PHAM SET SKU='CPU-DEMO',TenSP='Tên sản phẩm tự đặt' WHERE MaSP=1")
        normalize_seed_labels(c)
        self.assertEqual(one(c,'SELECT TenDangNhap FROM TAI_KHOAN WHERE MaTK=1')['TenDangNhap'],'quanly')
        self.assertEqual(one(c,'SELECT TenSP FROM SAN_PHAM WHERE MaSP=1')['TenSP'],'Tên sản phẩm tự đặt')
        self.assertEqual(accounts,rows(c,'SELECT MaTK,MaNV,MatKhauBam,VaiTro,TrangThai,NgayTao FROM TAI_KHOAN ORDER BY MaTK'))
        for table in tables:self.assertEqual(before[table],rows(c,f'SELECT * FROM {table}'))
        snapshot=rows(c,'SELECT * FROM SAN_PHAM ORDER BY MaSP')
        normalize_seed_labels(c)
        self.assertEqual(snapshot,rows(c,'SELECT * FROM SAN_PHAM ORDER BY MaSP'))
        with self.assertRaises(pymysql.MySQLError):execute(c,"UPDATE BOM SET TenCauHinh='Changed' WHERE MaBOM=1")
        with self.assertRaises(pymysql.MySQLError):execute(c,"UPDATE PHIEU_XUAT SET TenNguoiNhan='Changed' WHERE MaPX=2")
        c.close()

    def test_label_cleanup_collision_is_atomic(self):
        from seed_labels import normalize_seed_labels
        c=connect(admin=True,database=self.database)
        execute(c,"UPDATE TAI_KHOAN SET TenDangNhap='demo_quanly' WHERE MaTK=1")
        nv=execute(c,"INSERT INTO NHAN_VIEN(HoTen) VALUES('Existing user')")
        execute(c,"INSERT INTO TAI_KHOAN(MaNV,TenDangNhap,MatKhauBam,VaiTro) VALUES(%s,'quanly','hash','ADMIN')",(nv,))
        execute(c,"UPDATE SAN_PHAM SET SKU='CPU-DEMO' WHERE MaSP=1")
        with self.assertRaises(RuntimeError):normalize_seed_labels(c)
        self.assertEqual(one(c,'SELECT TenDangNhap FROM TAI_KHOAN WHERE MaTK=1')['TenDangNhap'],'demo_quanly')
        self.assertEqual(one(c,'SELECT SKU FROM SAN_PHAM WHERE MaSP=1')['SKU'],'CPU-DEMO')
        c.close()

    def test_concurrent_edit_and_send_parent_lock(self):
        from threading import Barrier
        b=dict(LoaiXuat='THANH_PHAM',TenNguoiNhan='Race test',lines=[dict(MaSP=3,MaViTri=2,SoLuongXuat=1)])
        ident=self.create('outgoing',b,self.employee)
        barrier=Barrier(2)
        def worker(edit):
            client=self.login('nhanvien')
            csrf=client.get('/api/session').json['csrf']
            barrier.wait()
            if edit:
                changed={**b,'lines':[dict(MaSP=3,MaViTri=2,SoLuongXuat=2)]}
                return client.put(f'/api/documents/outgoing/{ident}',json=changed,headers={'X-CSRF-Token':csrf})
            return client.post(f'/api/actions/outgoing/{ident}/send',json={},headers={'X-CSRF-Token':csrf})
        with ThreadPoolExecutor(max_workers=2) as pool:
            edit=pool.submit(worker,True);send=pool.submit(worker,False)
            edit_result,send_result=edit.result(),send.result()
        self.assertIn(edit_result.status_code,(200,409),edit_result.json)
        self.assertEqual(send_result.status_code,200,send_result.json)
        r=next(p for p in self.state()['outgoing'] if p['MaPX']==ident)
        self.assertEqual(r['TrangThai'],'CHO_DUYET')
        self.assertEqual(r['lines'][0]['SoLuongXuat'],2 if edit_result.status_code==200 else 1)


if __name__ == '__main__': unittest.main(verbosity=2)
