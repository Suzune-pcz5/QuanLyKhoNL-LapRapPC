"""Repeatable routine, trigger and label upgrades without rebuilding tables."""
from datetime import datetime

from db import ROOT, RUNTIME, execute, one, sql_statements


def normalize_unit_labels(c):
    """Correct the exact legacy unit spelling; leave all other product data intact."""
    c.begin()
    try:
        with c.cursor() as cursor:
            cursor.execute('UPDATE SAN_PHAM SET DonViTinh=%s WHERE CAST(DonViTinh AS BINARY)=CAST(%s AS BINARY)', ('cái', 'cai'))
            changed = cursor.rowcount
        c.commit()
        return changed
    except Exception:
        c.rollback()
        raise

STOCK_ROUTINE = 'sp_ghi_bien_dong'
STOCK_MARKER = 'MRP_STOCK_SHORTAGE|'
FROZEN_NOTES_MARKER = 'MRP_FROZEN_NOTES_V1'
FROZEN_NOTES_GUARD = 'NOT(CAST(NEW.GhiChu AS BINARY)<=>CAST(OLD.GhiChu AS BINARY))'
FROZEN_NOTES_TRIGGERS = ('trg_phieu_nhap_freeze', 'trg_phieu_xuat_freeze', 'trg_ket_qua_lap_rap_freeze')
FROZEN_HEADERS_MARKER = 'MRP_FROZEN_HEADERS_V1'
FROZEN_HEADER_GUARDS = {
    'trg_phieu_xuat_freeze': 'NOT(CAST(NEW.TenNguoiNhan AS BINARY)<=>CAST(OLD.TenNguoiNhan AS BINARY))',
    'trg_bom_freeze': 'NOT(CAST(NEW.TenCauHinh AS BINARY)<=>CAST(OLD.TenCauHinh AS BINARY))',
    'trg_yeu_cau_lap_rap_freeze': 'NOT(NEW.HanMongMuon<=>OLD.HanMongMuon)',
}


def upgrade_frozen_headers(c, database):
    """Close the remaining header guards without touching document contents."""
    if not database.replace('_', '').isalnum():
        raise ValueError('Invalid database name')
    c.select_db(database)
    originals = {name: one(c, f'SHOW CREATE TRIGGER {name}')['SQL Original Statement'] for name in FROZEN_HEADER_GUARDS}
    pending = [name for name, sql in originals.items() if FROZEN_HEADERS_MARKER not in sql or FROZEN_HEADER_GUARDS[name] not in sql]
    if not pending:
        return dict(changed=False)
    statements = list(sql_statements((ROOT / 'docs/mrp/schema_MRP_HTTTDN_17_bang.sql').read_text(encoding='utf-8')))
    replacements = {name: next(sql for sql in statements if sql.startswith(f'CREATE TRIGGER {name} ')) for name in pending}
    if any(FROZEN_HEADERS_MARKER not in sql or FROZEN_HEADER_GUARDS[name] not in sql for name, sql in replacements.items()):
        raise RuntimeError('Missing frozen header migration in schema')
    folder = RUNTIME / 'migrations'
    folder.mkdir(parents=True, exist_ok=True)
    rollback = folder / f'{database}_frozen_headers_{datetime.now():%Y%m%d_%H%M%S_%f}.sql'
    rollback.write_text('DELIMITER $$\n' + ''.join(f'DROP TRIGGER IF EXISTS {name}$$\n{originals[name]}$$\n' for name in pending) + 'DELIMITER ;\n', encoding='utf-8')
    touched = []
    try:
        for name in pending:
            execute(c, f'DROP TRIGGER {name}')
            touched.append(name)
            execute(c, replacements[name])
    except Exception as error:
        failures = []
        for name in reversed(touched):
            try:
                execute(c, f'DROP TRIGGER IF EXISTS {name}')
                execute(c, originals[name])
            except Exception:
                failures.append(name)
        if failures:
            raise RuntimeError(f'Chưa phục hồi được trigger {", ".join(failures)}. Dùng bản rollback {rollback}.') from error
        raise
    return dict(changed=True, triggers=len(pending), rollback=str(rollback))


def upgrade_frozen_notes(c, database):
    """Replace only our freeze triggers, restoring all touched definitions on failure."""
    if not database.replace('_', '').isalnum():
        raise ValueError('Invalid database name')
    c.select_db(database)
    originals = {name: one(c, f'SHOW CREATE TRIGGER {name}')['SQL Original Statement'] for name in FROZEN_NOTES_TRIGGERS}
    pending = [name for name, sql in originals.items() if FROZEN_NOTES_MARKER not in sql or FROZEN_NOTES_GUARD not in sql]
    if not pending:
        return dict(changed=False)
    schema = (ROOT / 'docs/mrp/schema_MRP_HTTTDN_17_bang.sql').read_text(encoding='utf-8')
    statements = list(sql_statements(schema))
    replacements = {name: next(sql for sql in statements if sql.startswith(f'CREATE TRIGGER {name} ')) for name in pending}
    if any(FROZEN_NOTES_MARKER not in sql or FROZEN_NOTES_GUARD not in sql for sql in replacements.values()):
        raise RuntimeError('Missing frozen notes migration in schema')
    folder = RUNTIME / 'migrations'
    folder.mkdir(parents=True, exist_ok=True)
    rollback = folder / f'{database}_frozen_notes_{datetime.now():%Y%m%d_%H%M%S_%f}.sql'
    rollback.write_text('DELIMITER $$\n' + ''.join(f'DROP TRIGGER IF EXISTS {name}$$\n{originals[name]}$$\n' for name in pending) + 'DELIMITER ;\n', encoding='utf-8')
    touched = []
    try:
        for name in pending:
            execute(c, f'DROP TRIGGER {name}')
            touched.append(name)
            execute(c, replacements[name])
    except Exception as error:
        failures = []
        for name in reversed(touched):
            try:
                execute(c, f'DROP TRIGGER IF EXISTS {name}')
                execute(c, originals[name])
            except Exception:
                failures.append(name)
        if failures:
            raise RuntimeError(f'Chưa phục hồi được trigger {", ".join(failures)}. Dùng bản rollback {rollback}.') from error
        raise
    return dict(changed=True, triggers=len(pending), rollback=str(rollback))


def upgrade_stock_diagnostics(c, database):
    """Keep the old definition for rollback; this internal routine has no app grant."""
    if not database.replace('_', '').isalnum():
        raise ValueError('Invalid database name')
    c.select_db(database)
    original = one(c, f'SHOW CREATE PROCEDURE {STOCK_ROUTINE}')['Create Procedure']
    if STOCK_MARKER in original:
        return dict(changed=False)
    schema = (ROOT / 'docs/mrp/schema_MRP_HTTTDN_17_bang.sql').read_text(encoding='utf-8')
    replacement = next(sql for sql in sql_statements(schema) if sql.startswith(f'CREATE PROCEDURE {STOCK_ROUTINE}('))
    if STOCK_MARKER not in replacement:
        raise RuntimeError('Missing stock diagnostic migration in schema')
    folder = RUNTIME / 'migrations'
    folder.mkdir(parents=True, exist_ok=True)
    rollback = folder / f'{database}_stock_{datetime.now():%Y%m%d_%H%M%S_%f}.sql'
    rollback.write_text(f'DELIMITER $$\nDROP PROCEDURE IF EXISTS {STOCK_ROUTINE}$$\n{original}$$\nDELIMITER ;\n', encoding='utf-8')
    # MySQL routine DDL auto-commits; restore explicitly if CREATE fails after DROP.
    execute(c, f'DROP PROCEDURE {STOCK_ROUTINE}')
    try:
        execute(c, replacement)
    except Exception:
        execute(c, original)
        raise
    return dict(changed=True, rollback=str(rollback))
