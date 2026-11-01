"""Reset the existing quanly web account password on configured Aiven MySQL."""

import getpass
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))

from db import connect, one
from werkzeug.security import check_password_hash, generate_password_hash


def main():
    project = Path(__file__).resolve().parent
    original = Path(os.environ["LOCALAPPDATA"]) / "HTTTDN-Demo/cloud/aiven-warehouse.json"
    local_private = project / ".local" / "aiven-reset-private.json"
    config = next((path for path in (original, local_private) if path.is_file()), None)
    if config is not None:
        values = json.loads(config.read_text(encoding="utf-8-sig"))
        ca = values.get("MYSQL_SSL_CA")
        if ca and not Path(ca).is_absolute():
            values["MYSQL_SSL_CA"] = str(config.parent / ca)
    else:
        # Last resort when neither local saved credential file is available.
        profile = project / ".local" / "aiven-connection.json"
        if not profile.is_file():
            raise SystemExit(
                "Khong tim thay cau hinh MySQL. Can file .local/aiven-connection.json "
                "trong thu muc du an."
            )
        values = json.loads(profile.read_text(encoding="utf-8-sig"))
        if not isinstance(values, dict) or any(
            key not in {
                "MYSQL_HOST", "MYSQL_PORT", "MYSQL_DATABASE",
                "MYSQL_STATE_DATABASE", "MYSQL_ADMIN_USER", "MYSQL_SSL_CA"
            } or not isinstance(value, str)
            for key, value in values.items()
        ):
            raise SystemExit("File cau hinh ket noi toi thieu khong hop le.")
        values["MYSQL_SSL_CA"] = str(profile.parent / values["MYSQL_SSL_CA"])
        values["MYSQL_ADMIN_PASSWORD"] = getpass.getpass("Mat khau quan tri MySQL Aiven: ")
        if not values["MYSQL_ADMIN_PASSWORD"]:
            raise SystemExit("Chua nhap mat khau quan tri Aiven.")

    # Load the chosen connection settings without importing the Flask
    # initialization stack (which this one-off task does not need).
    if not isinstance(values, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in values.items()
    ):
        raise SystemExit("File cau hinh MySQL khong hop le.")
    # The reset script uses admin credentials only; provide the values
    # required by the shared connection settings parser when using the
    # minimal local private profile.
    values.setdefault("MYSQL_USER", "unused_for_reset")
    values.setdefault("MYSQL_PASSWORD", "unused_for_reset")
    values.setdefault("SECRET_KEY", "not-used-for-reset-account-script" * 2)
    values.setdefault("APP_ORIGIN", "https://setup.invalid")
    os.environ.update(values)
    password = getpass.getpass("Mat khau moi (it nhat 12 ky tu): ")
    confirmation = getpass.getpass("Nhap lai mat khau: ")
    if len(password) < 12 or len(password) > 255 or password != confirmation:
        raise SystemExit("Mat khau phai tu 12-255 ky tu va hai lan nhap phai trung nhau.")

    db = connect(admin=True)
    try:
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT MaTK FROM TAI_KHOAN WHERE TenDangNhap=%s",
                ("quanly",),
            )
            row = cursor.fetchone()
            if row is None:
                raise SystemExit("Khong tim thay tai khoan quanly. Khong thay doi gi.")

            cursor.execute(
                "UPDATE TAI_KHOAN SET MatKhauBam=%s WHERE MaTK=%s",
                (generate_password_hash(password), row["MaTK"]),
            )
    finally:
        db.close()

    db = connect(admin=True)
    try:
        row = one(db, "SELECT MatKhauBam FROM TAI_KHOAN WHERE TenDangNhap=%s", ("quanly",))
        if row is None or not check_password_hash(row["MatKhauBam"], password):
            raise SystemExit("Da ghi nhung kiem tra mat khau moi that bai.")
    finally:
        db.close()

    print("DA DOI MAT KHAU QUANLY THANH CONG!")
    # The fallback credential is needed only until the password reset works.
    if local_private.is_file():
        try:
            local_private.unlink()
        except OSError:
            print("Luu y: hay xoa file .local/aiven-reset-private.json sau khi xong.")


if __name__ == "__main__":
    main()
