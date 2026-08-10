from __future__ import annotations

import os
import hmac
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from typing import Any

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from sqlalchemy import func, inspect, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.mutable import MutableList
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()
load_dotenv()


REQUIRED_DATABASE_TABLES = {
    "machines",
    "machine_metadata",
    "errors",
    "maintenance",
    "maintenance_config",
    "users",
    "humidity_logs",
    "voltage_events",
}

REQUIRED_DATABASE_COLUMNS = {
    "machine_metadata": {
        "is_archived",
        "archived_at",
        "archived_by",
        "archive_note",
    },
    "maintenance": {
        "serial_number_snapshot",
        "item_name_snapshot",
        "performed_by_snapshot",
    },
}


def env_flag(name: str, default: bool = False) -> bool:
    fallback = "1" if default else "0"
    return os.getenv(name, fallback).strip().lower() in {"1", "true", "yes", "on"}


def normalize_database_url(database_url: str) -> str:
    """Make Railway's PostgreSQL URL use the installed Psycopg 3 driver."""
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_machine_id(raw_id: Any) -> str:
    value = str(raw_id or "").strip()
    return value.split("-")[-1].strip().upper()


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def seconds_between(start: datetime | None, end: datetime | None = None) -> float:
    if not start:
        return 0.0
    return max(0.0, ((end or utcnow()) - start).total_seconds())


class Machine(db.Model):
    __tablename__ = "machines"

    machine_id = db.Column(db.String(50), primary_key=True)
    status = db.Column(db.String(20), nullable=False, default="stopped")
    last_update = db.Column(db.DateTime)
    start_time = db.Column(db.DateTime)
    total_active_time = db.Column(db.Float, nullable=False, default=0.0)
    current_session_start = db.Column(db.DateTime)
    last_heartbeat = db.Column(db.DateTime)
    completed_treatments = db.Column(db.Integer, nullable=False, default=0)
    pump_status = db.Column(db.String(20), nullable=False, default="stopped")
    pump_last_heartbeat = db.Column(db.DateTime)
    dialysis_session_start = db.Column(db.DateTime)
    total_dialysis_time = db.Column(db.Float, nullable=False, default=0.0)
    completed_dialysis = db.Column(db.Integer, nullable=False, default=0)

    metadata_record = db.relationship(
        "MachineMetadata",
        back_populates="machine",
        uselist=False,
        cascade="all, delete-orphan",
    )


class MachineMetadata(db.Model):
    __tablename__ = "machine_metadata"

    machine_id = db.Column(
        db.String(50), db.ForeignKey("machines.machine_id"), primary_key=True
    )
    serial_number = db.Column(db.String(50), nullable=False)
    hospital_name = db.Column(db.String(100), nullable=False)
    unit_number = db.Column(db.Integer, nullable=False)
    region = db.Column(db.String(50), nullable=False)
    subregion = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(10), nullable=False)
    installation_date = db.Column(db.Date)
    registered_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
    is_archived = db.Column(db.Boolean, nullable=False, default=False)
    archived_at = db.Column(db.DateTime)
    archived_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    archive_note = db.Column(db.Text)

    machine = db.relationship("Machine", back_populates="metadata_record")


class ErrorLog(db.Model):
    __tablename__ = "errors"

    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.String(50), db.ForeignKey("machines.machine_id"))
    error_code = db.Column(db.String(20))
    type = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime)
    server_received_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class Maintenance(db.Model):
    __tablename__ = "maintenance"

    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.String(50), db.ForeignKey("machines.machine_id"))
    item = db.Column(db.String(50), nullable=False)
    dialysis_count = db.Column(db.Integer, nullable=False, default=0)
    timestamp = db.Column(db.DateTime, nullable=False, default=utcnow)
    description = db.Column(db.Text, nullable=False)
    performed_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    serial_number_snapshot = db.Column(db.String(50), nullable=False)
    item_name_snapshot = db.Column(db.String(100), nullable=False)
    performed_by_snapshot = db.Column(db.String(50), nullable=False)


class MaintenanceConfig(db.Model):
    __tablename__ = "maintenance_config"

    id = db.Column(db.Integer, primary_key=True)
    item_code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    threshold_type = db.Column(db.String(20), nullable=False)
    threshold_value = db.Column(db.Integer, nullable=False)
    time_unit = db.Column(db.String(10))
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    assigned_regions = db.Column(
        MutableList.as_mutable(db.JSON), nullable=False, default=list
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class HumidityLog(db.Model):
    __tablename__ = "humidity_logs"

    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.String(50), db.ForeignKey("machines.machine_id"))
    humidity = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=utcnow)


class VoltageEvent(db.Model):
    __tablename__ = "voltage_events"

    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.String(50), db.ForeignKey("machines.machine_id"))
    event_type = db.Column(db.String(20), nullable=False)
    voltage = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, nullable=False, default=utcnow)


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    declared_app_env = os.getenv("APP_ENV", "development").strip().lower()
    is_railway = bool(
        os.getenv("RAILWAY_PROJECT_ID") or os.getenv("RAILWAY_ENVIRONMENT_ID")
    )
    is_production = declared_app_env == "production" or is_railway
    app_env = "production" if is_production else declared_app_env
    raw_database_url = os.getenv("DATABASE_URL", "").strip()
    if is_production and not raw_database_url:
        raise RuntimeError("DATABASE_URL wajib diisi pada environment production.")
    database_url = normalize_database_url(
        raw_database_url or "sqlite:///hd_monitoring.db"
    )

    secret_key = os.getenv("SECRET_KEY", "").strip()
    if is_production and (
        not secret_key or secret_key == "change-this-secret-key"
    ):
        raise RuntimeError(
            "SECRET_KEY production wajib diisi dengan nilai acak yang kuat."
        )
    if is_production and env_flag("SEED_DEMO_DATA"):
        raise RuntimeError("SEED_DEMO_DATA tidak boleh aktif di production.")

    app.config.from_mapping(
        APP_ENV=app_env,
        SECRET_KEY=secret_key or "development-only-secret-key",
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            "pool_pre_ping": True,
            "pool_recycle": 300,
        },
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=is_production,
        AUTO_CREATE_TABLES=env_flag("AUTO_CREATE_TABLES", not is_production),
        VALIDATE_DATABASE_SCHEMA=env_flag(
            "VALIDATE_DATABASE_SCHEMA", is_production
        ),
        BOOTSTRAP_ADMIN=env_flag("BOOTSTRAP_ADMIN", True),
        HEARTBEAT_TIMEOUT_SECONDS=int(os.getenv("HEARTBEAT_TIMEOUT_SECONDS", "390")),
        PUMP_HEARTBEAT_TIMEOUT_SECONDS=int(
            os.getenv("PUMP_HEARTBEAT_TIMEOUT_SECONDS", "180")
        ),
        ACTIVE_SESSION_THRESHOLD_SECONDS=int(
            os.getenv("ACTIVE_SESSION_THRESHOLD_SECONDS", "60")
        ),
        DIALYSIS_SESSION_THRESHOLD_SECONDS=int(
            os.getenv("DIALYSIS_SESSION_THRESHOLD_SECONDS", "14400")
        ),
        ERROR_LOG_LIMIT=int(os.getenv("ERROR_LOG_LIMIT", "300")),
        DEVICE_API_KEY=os.getenv("DEVICE_API_KEY", ""),
        JSON_SORT_KEYS=False,
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    register_routes(app)
    register_cli(app)

    with app.app_context():
        if app.config["AUTO_CREATE_TABLES"]:
            db.create_all()
        elif app.config["VALIDATE_DATABASE_SCHEMA"]:
            validate_database_schema()

        if app.config["BOOTSTRAP_ADMIN"]:
            ensure_admin()

        if env_flag("SEED_DEMO_DATA") and not app.config.get("TESTING"):
            if Machine.query.count() == 0:
                seed_demo_data()

    return app


def register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db_command() -> None:
        db.create_all()
        ensure_admin()
        print("Database initialized.")

    @app.cli.command("seed-demo")
    def seed_demo_command() -> None:
        seed_demo_data()
        print("Demo data inserted.")


def ensure_admin() -> None:
    if User.query.count() != 0:
        return

    username = os.getenv("ADMIN_USERNAME", "admin").strip() or "admin"
    password = os.getenv("ADMIN_PASSWORD", "")
    if not password:
        if create_app_config("APP_ENV") == "production":
            raise RuntimeError(
                "ADMIN_PASSWORD wajib diisi untuk membuat admin pertama."
            )
        password = "admin123"

    user = User(username=username, role="admin", assigned_regions=[])
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        # Beberapa worker Gunicorn dapat mulai bersamaan. Jika worker lain sudah
        # membuat admin yang sama, worker ini cukup melanjutkan startup.
        db.session.rollback()
        if not User.query.filter_by(username=username).first():
            raise


def validate_database_schema() -> None:
    database_inspector = inspect(db.engine)
    existing_tables = set(database_inspector.get_table_names())
    missing_tables = sorted(REQUIRED_DATABASE_TABLES - existing_tables)
    if missing_tables:
        raise RuntimeError(
            "Schema PostgreSQL belum lengkap. Jalankan database/schema.sql. "
            f"Tabel yang belum ada: {', '.join(missing_tables)}"
        )
    missing_columns = []
    for table_name, required_columns in REQUIRED_DATABASE_COLUMNS.items():
        existing_columns = {
            column["name"] for column in database_inspector.get_columns(table_name)
        }
        for column_name in sorted(required_columns - existing_columns):
            missing_columns.append(f"{table_name}.{column_name}")
    if missing_columns:
        raise RuntimeError(
            "Schema PostgreSQL perlu dimigrasikan. Jalankan "
            "database/migrate_maintenance_history_archive.sql. Kolom yang belum "
            f"ada: {', '.join(missing_columns)}"
        )


def current_user() -> User | None:
    user_id = session.get("user_id")
    return db.session.get(User, user_id) if user_id else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
                return jsonify({"ok": False, "error": "Authentication required"}), 401
            return redirect(url_for("login", next=request.full_path))
        return view(*args, **kwargs)

    return wrapped


def roles_required(*roles: str):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user or user.role not in roles:
                if request.path.startswith("/api/") or request.path.startswith(
                    "/admin/api/"
                ):
                    return jsonify({"ok": False, "error": "Access denied"}), 403
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


def device_key_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        from flask import current_app

        expected = current_app.config.get("DEVICE_API_KEY", "")
        supplied = request.headers.get("X-API-Key", "")
        if expected and not hmac.compare_digest(expected, supplied):
            return jsonify({"ok": False, "error": "Device API key tidak valid"}), 401
        return view(*args, **kwargs)

    return wrapped


def json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def get_json() -> dict[str, Any]:
    return request.get_json(silent=True) or {}


def get_or_create_machine(machine_id: str) -> Machine:
    machine = db.session.get(Machine, machine_id)
    if not machine:
        machine = Machine(machine_id=machine_id, status="stopped", pump_status="stopped")
        db.session.add(machine)
        db.session.flush()
    return machine


def trim_error_logs(machine_id: str) -> None:
    """Keep only the newest configured number of error logs for one machine."""
    limit = max(1, int(create_app_config("ERROR_LOG_LIMIT")))
    keep_ids = [
        row.id
        for row in (
            ErrorLog.query.with_entities(ErrorLog.id)
            .filter_by(machine_id=machine_id)
            .order_by(ErrorLog.server_received_at.desc(), ErrorLog.id.desc())
            .limit(limit)
            .all()
        )
    ]
    if keep_ids:
        (
            ErrorLog.query.filter(
                ErrorLog.machine_id == machine_id,
                ErrorLog.id.notin_(keep_ids),
            ).delete(synchronize_session=False)
        )


def finalize_active_session(machine: Machine, end_time: datetime) -> None:
    duration = seconds_between(machine.current_session_start, end_time)
    machine.total_active_time = (machine.total_active_time or 0) + duration
    if duration >= create_app_config("ACTIVE_SESSION_THRESHOLD_SECONDS"):
        machine.completed_treatments = (machine.completed_treatments or 0) + 1
    machine.current_session_start = None
    machine.status = "stopped"


def finalize_dialysis_session(machine: Machine, end_time: datetime) -> None:
    duration = seconds_between(machine.dialysis_session_start, end_time)
    machine.total_dialysis_time = (machine.total_dialysis_time or 0) + duration
    if duration >= create_app_config("DIALYSIS_SESSION_THRESHOLD_SECONDS"):
        machine.completed_dialysis = (machine.completed_dialysis or 0) + 1
    machine.dialysis_session_start = None
    machine.pump_status = "stopped"


def create_app_config(key: str):
    from flask import current_app

    return current_app.config[key]


def reconcile_timeouts() -> None:
    now = utcnow()
    active_timeout = timedelta(
        seconds=create_app_config("HEARTBEAT_TIMEOUT_SECONDS")
    )
    pump_timeout = timedelta(
        seconds=create_app_config("PUMP_HEARTBEAT_TIMEOUT_SECONDS")
    )
    changed = False
    for machine in Machine.query.all():
        if (
            machine.status == "running"
            and machine.last_heartbeat
            and now - machine.last_heartbeat > active_timeout
        ):
            finalize_active_session(machine, machine.last_heartbeat)
            changed = True
        if (
            machine.pump_status == "running"
            and machine.pump_last_heartbeat
            and now - machine.pump_last_heartbeat > pump_timeout
        ):
            finalize_dialysis_session(machine, machine.pump_last_heartbeat)
            changed = True
    if changed:
        db.session.commit()


def user_can_access_machine(user: User, machine: Machine | None) -> bool:
    if not machine:
        return False
    if user.role != "teknisi":
        return True
    metadata = machine.metadata_record
    return bool(metadata and metadata.subregion in (user.assigned_regions or []))


def load_machine_dashboard_batch(user: User):
    """Load all dashboard dependencies in a fixed number of batch queries."""
    machine_query = db.session.query(Machine, MachineMetadata).outerjoin(
        MachineMetadata, Machine.machine_id == MachineMetadata.machine_id
    )
    if user.role == "teknisi":
        allowed = user.assigned_regions or []
        if not allowed:
            machine_query = machine_query.filter(db.false())
        else:
            machine_query = machine_query.filter(MachineMetadata.subregion.in_(allowed))

    machine_rows = machine_query.order_by(Machine.machine_id).all()
    if not machine_rows:
        return machine_rows, [], {}, {}

    machine_ids = [machine.machine_id for machine, _metadata in machine_rows]
    configs = (
        MaintenanceConfig.query.filter_by(active=True)
        .order_by(MaintenanceConfig.name)
        .all()
    )

    humidity_ranked = (
        db.session.query(
            HumidityLog.machine_id,
            HumidityLog.humidity,
            func.row_number()
            .over(
                partition_by=HumidityLog.machine_id,
                order_by=(HumidityLog.timestamp.desc(), HumidityLog.id.desc()),
            )
            .label("row_number"),
        )
        .filter(HumidityLog.machine_id.in_(machine_ids))
        .subquery()
    )
    humidity_rows = (
        db.session.query(humidity_ranked.c.machine_id, humidity_ranked.c.humidity)
        .filter(humidity_ranked.c.row_number == 1)
        .all()
    )
    humidity_map = {row.machine_id: row.humidity for row in humidity_rows}

    maintenance_map: dict[tuple[str, str], dict[str, Any]] = {}
    config_codes = [config.item_code for config in configs]
    if config_codes:
        maintenance_ranked = (
            db.session.query(
                Maintenance.machine_id,
                Maintenance.item,
                Maintenance.dialysis_count,
                Maintenance.timestamp,
                func.row_number()
                .over(
                    partition_by=(Maintenance.machine_id, Maintenance.item),
                    order_by=(Maintenance.timestamp.desc(), Maintenance.id.desc()),
                )
                .label("row_number"),
            )
            .filter(
                Maintenance.machine_id.in_(machine_ids),
                Maintenance.item.in_(config_codes),
            )
            .subquery()
        )
        maintenance_rows = (
            db.session.query(
                maintenance_ranked.c.machine_id,
                maintenance_ranked.c.item,
                maintenance_ranked.c.dialysis_count,
                maintenance_ranked.c.timestamp,
            )
            .filter(maintenance_ranked.c.row_number == 1)
            .all()
        )
        maintenance_map = {
            (row.machine_id, row.item): {
                "dialysis_count": row.dialysis_count,
                "timestamp": row.timestamp,
            }
            for row in maintenance_rows
        }

    return machine_rows, configs, humidity_map, maintenance_map


def maintenance_status(
    machine: Machine,
    metadata: MachineMetadata | None,
    configs: list[MaintenanceConfig],
    maintenance_map: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    if metadata and metadata.is_archived:
        return []
    output: list[dict[str, Any]] = []
    now = utcnow()
    for config in configs:
        last = maintenance_map.get((machine.machine_id, config.item_code))
        required = False
        progress = 0
        threshold_label = ""
        if config.threshold_type == "treatment_count":
            baseline = last["dialysis_count"] if last else 0
            progress = max(0, (machine.completed_dialysis or 0) - baseline)
            required = progress >= config.threshold_value
            threshold_label = f"{config.threshold_value} treatment"
        else:
            baseline_dt = (
                last["timestamp"]
                if last
                else (
                    datetime.combine(metadata.installation_date, datetime.min.time())
                    if metadata and metadata.installation_date
                    else metadata.registered_at if metadata else None
                )
            )
            unit = config.time_unit or "months"
            unit_days = 30 if unit == "months" else 1
            elapsed_days = int(seconds_between(baseline_dt, now) // 86400)
            progress = elapsed_days
            required = (
                baseline_dt is None
                or elapsed_days >= config.threshold_value * unit_days
            )
            threshold_label = f"{config.threshold_value} {unit}"
        if required:
            output.append(
                {
                    "config_id": config.id,
                    "item_code": config.item_code,
                    "name": config.name,
                    "description": config.description or "",
                    "threshold_type": config.threshold_type,
                    "threshold_value": config.threshold_value,
                    "threshold_label": threshold_label,
                    "progress": progress,
                    "required": True,
                }
            )
    return output


def iso_utc(value: datetime | None) -> str | None:
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def machine_to_dict(
    machine: Machine,
    metadata: MachineMetadata | None,
    humidity: float | None,
    configs: list[MaintenanceConfig],
    maintenance_map: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    active_now = (
        seconds_between(machine.current_session_start)
        if machine.status == "running"
        else 0
    )
    dialysis_now = (
        seconds_between(machine.dialysis_session_start)
        if machine.pump_status == "running"
        else 0
    )
    required = maintenance_status(machine, metadata, configs, maintenance_map)
    return {
        "machine_id": machine.machine_id,
        "status": machine.status,
        "pump_status": machine.pump_status,
        "last_update": iso_utc(machine.last_update),
        "last_heartbeat": iso_utc(machine.last_heartbeat),
        "current_session_start": iso_utc(machine.current_session_start),
        "dialysis_session_start": iso_utc(machine.dialysis_session_start),
        "current_active_seconds": int(active_now),
        "total_active_seconds": int((machine.total_active_time or 0) + active_now),
        "completed_treatments": machine.completed_treatments or 0,
        "current_dialysis_seconds": int(dialysis_now),
        "total_dialysis_seconds": int(
            (machine.total_dialysis_time or 0) + dialysis_now
        ),
        "completed_dialysis": machine.completed_dialysis or 0,
        "humidity": humidity,
        "metadata": {
            "serial_number": metadata.serial_number if metadata else machine.machine_id,
            "hospital_name": metadata.hospital_name if metadata else "Belum terdaftar",
            "unit_number": metadata.unit_number if metadata else None,
            "region": metadata.region if metadata else "Tanpa Region",
            "subregion": metadata.subregion if metadata else "Tanpa Subregion",
            "category": metadata.category if metadata else "Non-KSO",
            "is_archived": bool(metadata.is_archived) if metadata else False,
            "archived_at": iso_utc(metadata.archived_at) if metadata else None,
            "archive_note": metadata.archive_note if metadata else None,
            "installation_date": (
                metadata.installation_date.isoformat()
                if metadata and metadata.installation_date
                else None
            ),
        },
        "maintenance_required": required,
        "maintenance_count": len(required),
    }


def metadata_payload(record: MachineMetadata) -> dict[str, Any]:
    return {
        "machine_id": record.machine_id,
        "serial_number": record.serial_number,
        "hospital_name": record.hospital_name,
        "unit_number": record.unit_number,
        "region": record.region,
        "subregion": record.subregion,
        "category": record.category,
        "is_archived": bool(record.is_archived),
        "archived_at": iso_utc(record.archived_at),
        "archive_note": record.archive_note,
        "installation_date": (
            record.installation_date.isoformat() if record.installation_date else None
        ),
    }


def validate_metadata(data: dict[str, Any], partial: bool = False) -> tuple[dict, str | None]:
    fields = [
        "machine_id",
        "serial_number",
        "hospital_name",
        "unit_number",
        "region",
        "subregion",
        "category",
        "installation_date",
    ]
    if not partial:
        missing = [field for field in fields if data.get(field) in (None, "")]
        if missing:
            return {}, f"Field wajib: {', '.join(missing)}"
    clean = {key: data.get(key) for key in fields if key in data}
    if "machine_id" in clean:
        clean["machine_id"] = normalize_machine_id(clean["machine_id"])
    if "unit_number" in clean:
        try:
            clean["unit_number"] = int(clean["unit_number"])
        except (TypeError, ValueError):
            return {}, "Nomor unit harus berupa angka"
    if "category" in clean and clean["category"] not in {"KSO", "Non-KSO"}:
        return {}, "Kategori harus KSO atau Non-KSO"
    if "installation_date" in clean:
        try:
            clean["installation_date"] = date.fromisoformat(clean["installation_date"])
        except (TypeError, ValueError):
            return {}, "Tanggal instalasi tidak valid"
    return clean, None


def parse_date_filter(value: str, label: str) -> tuple[date | None, str | None]:
    if not value:
        return None, None
    try:
        return date.fromisoformat(value), None
    except ValueError:
        return None, f"{label} harus menggunakan format YYYY-MM-DD"


def maintenance_history_base_query(user: User):
    query = (
        db.session.query(Maintenance, MachineMetadata, MaintenanceConfig, User)
        .outerjoin(
            MachineMetadata,
            Maintenance.machine_id == MachineMetadata.machine_id,
        )
        .outerjoin(
            MaintenanceConfig,
            Maintenance.item == MaintenanceConfig.item_code,
        )
        .outerjoin(User, Maintenance.performed_by == User.id)
    )
    if user.role == "teknisi":
        allowed = user.assigned_regions or []
        if not allowed:
            return query.filter(db.false())
        query = query.filter(MachineMetadata.subregion.in_(allowed))
    return query


def maintenance_history_payload(
    maintenance: Maintenance,
    metadata: MachineMetadata | None,
    config: MaintenanceConfig | None,
    performer: User | None,
) -> dict[str, Any]:
    return {
        "id": maintenance.id,
        "timestamp": iso_utc(maintenance.timestamp),
        "machine_id": maintenance.machine_id,
        "serial_number": (
            maintenance.serial_number_snapshot
            or (metadata.serial_number if metadata else None)
            or maintenance.machine_id
        ),
        "item_code": maintenance.item,
        "item_name": (
            maintenance.item_name_snapshot
            or (config.name if config else None)
            or maintenance.item
        ),
        "performed_by": (
            maintenance.performed_by_snapshot
            or (performer.username if performer else None)
            or "User tidak tersedia"
        ),
        "description": maintenance.description or "",
        "region": metadata.region if metadata else "Tanpa Region",
        "subregion": metadata.subregion if metadata else "Tanpa Subregion",
        "is_archived": bool(metadata.is_archived) if metadata else False,
    }


def register_routes(app: Flask) -> None:
    @app.context_processor
    def inject_user():
        return {"current_user": current_user()}

    @app.get("/login")
    def login():
        if current_user():
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.post("/login")
    def login_post():
        data = request.form if request.form else get_json()
        user = User.query.filter_by(username=str(data.get("username", "")).strip()).first()
        if not user or not user.check_password(str(data.get("password", ""))):
            if request.is_json:
                return json_error("Username atau password salah", 401)
            return render_template("login.html", error="Username atau password salah"), 401
        session.clear()
        session["user_id"] = user.id
        destination = request.args.get("next")
        return redirect(destination or url_for("dashboard"))

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    @login_required
    def dashboard():
        return render_template("dashboard.html")

    @app.get("/admin")
    @roles_required("admin", "viewer")
    def admin_metadata():
        return render_template("admin_metadata.html")

    @app.get("/admin/users")
    @roles_required("admin", "viewer")
    def admin_users():
        return render_template("admin_users.html")

    @app.get("/admin/maintenance")
    @roles_required("admin", "viewer")
    def admin_maintenance():
        return render_template("admin_maintenance.html")

    @app.get("/maintenance-history")
    @login_required
    def maintenance_history():
        return render_template("maintenance_history.html")

    @app.post("/update")
    @device_key_required
    def update_machine():
        data = get_json()
        machine_id = normalize_machine_id(data.get("machine_id"))
        status = str(data.get("status", "")).lower()
        if not machine_id or status not in {"running", "stopped"}:
            return json_error("machine_id dan status running/stopped wajib diisi")
        now = utcnow()
        machine = get_or_create_machine(machine_id)
        if status == "running" and machine.status != "running":
            machine.current_session_start = now
            machine.start_time = machine.start_time or now
        elif status == "stopped" and machine.status == "running":
            finalize_active_session(machine, now)
        machine.status = status
        machine.last_update = now
        machine.last_heartbeat = now
        db.session.commit()
        return jsonify({"ok": True, "machine_id": machine_id, "status": status})

    @app.post("/pump-status")
    @device_key_required
    def pump_status():
        data = get_json()
        machine_id = normalize_machine_id(data.get("machine_id"))
        status = str(data.get("pump_status", "")).lower()
        if not machine_id or status not in {"running", "stopped"}:
            return json_error("machine_id dan pump_status running/stopped wajib diisi")
        now = utcnow()
        machine = get_or_create_machine(machine_id)
        if status == "running" and machine.pump_status != "running":
            machine.dialysis_session_start = now
        elif status == "stopped" and machine.pump_status == "running":
            finalize_dialysis_session(machine, now)
        machine.pump_status = status
        machine.pump_last_heartbeat = now
        machine.last_update = now
        db.session.commit()
        return jsonify({"ok": True, "machine_id": machine_id, "pump_status": status})

    @app.post("/error-log")
    @device_key_required
    def error_log():
        data = get_json()
        machine_id = normalize_machine_id(data.get("machine_id"))
        if not machine_id or data.get("error_code") is None:
            return json_error("machine_id dan error_code wajib diisi")
        get_or_create_machine(machine_id)
        db.session.add(
            ErrorLog(
                machine_id=machine_id,
                error_code=str(data.get("error_code")),
                type=str(data.get("type", "error_log")),
                timestamp=parse_datetime(data.get("timestamp")) or utcnow(),
            )
        )
        db.session.flush()
        trim_error_logs(machine_id)
        db.session.commit()
        return jsonify({"ok": True}), 201

    @app.post("/humidity")
    @device_key_required
    def humidity():
        data = get_json()
        machine_id = normalize_machine_id(data.get("machine_id"))
        try:
            humidity_value = float(data.get("humidity"))
        except (TypeError, ValueError):
            return json_error("humidity harus berupa angka")
        if not machine_id or not 0 <= humidity_value <= 100:
            return json_error("machine_id wajib dan humidity harus 0-100")
        get_or_create_machine(machine_id)
        db.session.add(HumidityLog(machine_id=machine_id, humidity=humidity_value))
        db.session.commit()
        return jsonify({"ok": True}), 201

    @app.post("/voltage")
    @device_key_required
    def voltage():
        data = get_json()
        machine_id = normalize_machine_id(data.get("machine_id"))
        event = str(data.get("event", "")).lower()
        if not machine_id or event not in {
            "spike",
            "overvoltage",
            "undervoltage",
            "error",
        }:
            return json_error("Event harus spike/overvoltage/undervoltage/error")
        try:
            voltage_value = (
                float(data["voltage"]) if data.get("voltage") is not None else None
            )
        except (TypeError, ValueError):
            return json_error("voltage harus berupa angka")
        get_or_create_machine(machine_id)
        db.session.add(
            VoltageEvent(
                machine_id=machine_id, event_type=event, voltage=voltage_value
            )
        )
        db.session.commit()
        return jsonify({"ok": True}), 201

    @app.get("/api/machines")
    @login_required
    def machines_api():
        reconcile_timeouts()
        user = current_user()
        machine_rows, configs, humidity_map, maintenance_map = (
            load_machine_dashboard_batch(user)
        )
        machines = [
            machine_to_dict(
                machine,
                metadata,
                humidity_map.get(machine.machine_id),
                configs,
                maintenance_map,
            )
            for machine, metadata in machine_rows
        ]
        return jsonify(
            {
                "ok": True,
                "server_time": iso_utc(utcnow()),
                "role": user.role,
                "machines": machines,
            }
        )

    @app.get("/api/voltage-summary/<machine_id>")
    @login_required
    def voltage_summary(machine_id: str):
        normalized = normalize_machine_id(machine_id)
        machine = db.session.get(Machine, normalized)
        if not user_can_access_machine(current_user(), machine):
            return json_error("Mesin tidak ditemukan atau di luar wilayah akses", 404)
        events = VoltageEvent.query.filter_by(machine_id=normalized).all()
        groups = {}
        for event_type in ("spike", "overvoltage", "undervoltage", "error"):
            matching = [item for item in events if item.event_type == event_type]
            latest = max(matching, key=lambda item: item.timestamp) if matching else None
            groups[event_type] = {
                "count": len(matching),
                "last_timestamp": iso_utc(latest.timestamp) if latest else None,
                "last_voltage": latest.voltage if latest else None,
            }
        return jsonify({"ok": True, "machine_id": normalized, "summary": groups})

    @app.get("/api/humidity-log/<machine_id>")
    @login_required
    def humidity_log(machine_id: str):
        normalized = normalize_machine_id(machine_id)
        machine = db.session.get(Machine, normalized)
        if not user_can_access_machine(current_user(), machine):
            return json_error("Mesin tidak ditemukan atau di luar wilayah akses", 404)
        rows = (
            HumidityLog.query.filter_by(machine_id=normalized)
            .order_by(HumidityLog.timestamp.desc())
            .limit(300)
            .all()
        )
        rows.reverse()
        return jsonify(
            {
                "ok": True,
                "machine_id": normalized,
                "logs": [
                    {"humidity": row.humidity, "timestamp": iso_utc(row.timestamp)}
                    for row in rows
                ],
            }
        )

    @app.get("/api/maintenance-history")
    @login_required
    def maintenance_history_api():
        user = current_user()
        query = maintenance_history_base_query(user)

        date_from, error = parse_date_filter(
            request.args.get("date_from", "").strip(), "Tanggal awal"
        )
        if error:
            return json_error(error)
        date_to, error = parse_date_filter(
            request.args.get("date_to", "").strip(), "Tanggal akhir"
        )
        if error:
            return json_error(error)
        if date_from and date_to and date_from > date_to:
            return json_error("Tanggal awal tidak boleh melebihi tanggal akhir")
        if date_from:
            query = query.filter(
                Maintenance.timestamp
                >= datetime.combine(date_from, datetime.min.time())
            )
        if date_to:
            query = query.filter(
                Maintenance.timestamp
                < datetime.combine(date_to + timedelta(days=1), datetime.min.time())
            )

        search = request.args.get("search", "").strip()
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Maintenance.machine_id.ilike(pattern),
                    Maintenance.serial_number_snapshot.ilike(pattern),
                    MachineMetadata.serial_number.ilike(pattern),
                )
            )
        region = request.args.get("region", "").strip()
        if region:
            query = query.filter(MachineMetadata.region == region)
        subregion = request.args.get("subregion", "").strip()
        if subregion:
            query = query.filter(MachineMetadata.subregion == subregion)
        item_code = request.args.get("item_code", "").strip()
        if item_code:
            query = query.filter(Maintenance.item == item_code)
        performer_name = request.args.get("performed_by", "").strip()
        if performer_name:
            pattern = f"%{performer_name}%"
            query = query.filter(
                or_(
                    Maintenance.performed_by_snapshot.ilike(pattern),
                    User.username.ilike(pattern),
                )
            )

        try:
            page = max(1, int(request.args.get("page", "1")))
            per_page = min(100, max(10, int(request.args.get("per_page", "50"))))
        except ValueError:
            return json_error("page dan per_page harus berupa angka")

        total = query.count()
        rows = (
            query.order_by(Maintenance.timestamp.desc(), Maintenance.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return jsonify(
            {
                "ok": True,
                "history": [maintenance_history_payload(*row) for row in rows],
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "pages": max(1, (total + per_page - 1) // per_page),
                },
            }
        )

    @app.get("/api/maintenance-history/filters")
    @login_required
    def maintenance_history_filters_api():
        base_query = maintenance_history_base_query(current_user())
        regions = [
            row.region
            for row in (
                base_query.with_entities(MachineMetadata.region.label("region"))
                .filter(MachineMetadata.region.isnot(None))
                .distinct()
                .order_by(MachineMetadata.region)
                .all()
            )
        ]
        subregions = [
            row.subregion
            for row in (
                base_query.with_entities(MachineMetadata.subregion.label("subregion"))
                .filter(MachineMetadata.subregion.isnot(None))
                .distinct()
                .order_by(MachineMetadata.subregion)
                .all()
            )
        ]
        item_rows = (
            base_query.with_entities(
                Maintenance.item.label("item_code"),
                func.max(Maintenance.item_name_snapshot).label("snapshot_name"),
                func.max(MaintenanceConfig.name).label("config_name"),
            )
            .group_by(Maintenance.item)
            .order_by(Maintenance.item)
            .all()
        )
        performer_rows = (
            base_query.with_entities(
                func.coalesce(
                    Maintenance.performed_by_snapshot,
                    User.username,
                    "User tidak tersedia",
                ).label("performer")
            )
            .distinct()
            .order_by("performer")
            .all()
        )
        return jsonify(
            {
                "ok": True,
                "regions": regions,
                "subregions": subregions,
                "items": [
                    {
                        "item_code": row.item_code,
                        "name": row.snapshot_name or row.config_name or row.item_code,
                    }
                    for row in item_rows
                ],
                "performers": [row.performer for row in performer_rows],
            }
        )

    @app.post("/maintenance-done")
    @roles_required("admin", "teknisi")
    def maintenance_done():
        data = get_json()
        machine_id = normalize_machine_id(data.get("machine_id"))
        item_code = str(data.get("item_code", "")).strip()
        description = str(data.get("description", "")).strip()
        if not description:
            return json_error("Catatan maintenance wajib diisi")
        if len(description) > 2000:
            return json_error("Catatan maintenance maksimal 2000 karakter")
        machine = db.session.get(Machine, machine_id)
        config = MaintenanceConfig.query.filter_by(item_code=item_code, active=True).first()
        if not machine or not config:
            return json_error("Mesin atau item maintenance tidak ditemukan", 404)
        if not user_can_access_machine(current_user(), machine):
            return json_error("Mesin tidak ditemukan atau di luar wilayah akses", 404)
        metadata = machine.metadata_record
        performer = current_user()
        db.session.add(
            Maintenance(
                machine_id=machine_id,
                item=item_code,
                dialysis_count=machine.completed_dialysis or 0,
                description=description,
                performed_by=performer.id,
                serial_number_snapshot=(
                    metadata.serial_number if metadata else machine_id
                ),
                item_name_snapshot=config.name,
                performed_by_snapshot=performer.username,
            )
        )
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/metadata", methods=["GET", "POST"])
    @roles_required("admin", "viewer")
    def metadata_collection():
        if request.method == "GET":
            rows = MachineMetadata.query.order_by(
                MachineMetadata.region,
                MachineMetadata.subregion,
                MachineMetadata.hospital_name,
                MachineMetadata.unit_number,
            ).all()
            return jsonify({"ok": True, "metadata": [metadata_payload(row) for row in rows]})
        if current_user().role != "admin":
            return json_error("Viewer hanya memiliki akses baca", 403)
        clean, error = validate_metadata(get_json())
        if error:
            return json_error(error)
        if db.session.get(MachineMetadata, clean["machine_id"]):
            return json_error("Machine ID sudah memiliki metadata", 409)
        get_or_create_machine(clean["machine_id"])
        record = MachineMetadata(**clean)
        db.session.add(record)
        db.session.commit()
        return jsonify({"ok": True, "metadata": metadata_payload(record)}), 201

    @app.route("/api/metadata/<machine_id>", methods=["GET", "PUT"])
    @roles_required("admin", "viewer")
    def metadata_item(machine_id: str):
        normalized = normalize_machine_id(machine_id)
        record = db.session.get(MachineMetadata, normalized)
        if not record:
            return json_error("Metadata tidak ditemukan", 404)
        if request.method == "GET":
            return jsonify({"ok": True, "metadata": metadata_payload(record)})
        if current_user().role != "admin":
            return json_error("Viewer hanya memiliki akses baca", 403)
        clean, error = validate_metadata(get_json(), partial=True)
        if error:
            return json_error(error)
        clean.pop("machine_id", None)
        for key, value in clean.items():
            setattr(record, key, value)
        db.session.commit()
        return jsonify({"ok": True, "metadata": metadata_payload(record)})

    @app.post("/api/metadata/<machine_id>/archive")
    @roles_required("admin")
    def archive_metadata(machine_id: str):
        normalized = normalize_machine_id(machine_id)
        record = db.session.get(MachineMetadata, normalized)
        if not record:
            return json_error("Metadata tidak ditemukan", 404)
        if record.is_archived:
            return json_error("Mesin sudah diarsipkan", 409)
        note = str(get_json().get("archive_note", "")).strip()
        if not note:
            return json_error("Alasan arsip wajib diisi")
        if len(note) > 1000:
            return json_error("Alasan arsip maksimal 1000 karakter")
        record.is_archived = True
        record.archived_at = utcnow()
        record.archived_by = current_user().id
        record.archive_note = note
        db.session.commit()
        return jsonify({"ok": True, "metadata": metadata_payload(record)})

    @app.post("/api/metadata/<machine_id>/restore")
    @roles_required("admin")
    def restore_metadata(machine_id: str):
        normalized = normalize_machine_id(machine_id)
        record = db.session.get(MachineMetadata, normalized)
        if not record:
            return json_error("Metadata tidak ditemukan", 404)
        if not record.is_archived:
            return json_error("Mesin tidak sedang diarsipkan", 409)
        record.is_archived = False
        db.session.commit()
        return jsonify({"ok": True, "metadata": metadata_payload(record)})

    @app.route("/admin/api/users", methods=["GET", "POST"])
    @roles_required("admin", "viewer")
    def users_collection():
        if request.method == "GET":
            return jsonify(
                {
                    "ok": True,
                    "users": [
                        {
                            "id": user.id,
                            "username": user.username,
                            "role": user.role,
                            "assigned_regions": user.assigned_regions or [],
                        }
                        for user in User.query.order_by(User.username).all()
                    ],
                }
            )
        if current_user().role != "admin":
            return json_error("Viewer hanya memiliki akses baca", 403)
        data = get_json()
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))
        role = str(data.get("role", "")).lower()
        if not username or not password or role not in {"admin", "teknisi", "viewer"}:
            return json_error("Username, password, dan role valid wajib diisi")
        if User.query.filter_by(username=username).first():
            return json_error("Username sudah digunakan", 409)
        regions = data.get("assigned_regions", [])
        if isinstance(regions, str):
            regions = [x.strip() for x in regions.split(",") if x.strip()]
        user = User(username=username, role=role, assigned_regions=regions if role == "teknisi" else [])
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return jsonify({"ok": True, "id": user.id}), 201

    @app.route("/admin/api/users/<int:user_id>", methods=["GET", "PUT", "DELETE"])
    @roles_required("admin", "viewer")
    def users_item(user_id: int):
        target = db.session.get(User, user_id)
        if not target:
            return json_error("User tidak ditemukan", 404)
        if request.method == "GET":
            return jsonify(
                {
                    "ok": True,
                    "user": {
                        "id": target.id,
                        "username": target.username,
                        "role": target.role,
                        "assigned_regions": target.assigned_regions or [],
                    },
                }
            )
        if current_user().role != "admin":
            return json_error("Viewer hanya memiliki akses baca", 403)
        if request.method == "DELETE":
            if target.id == current_user().id:
                return json_error("Akun yang sedang digunakan tidak dapat dihapus")
            db.session.delete(target)
            db.session.commit()
            return jsonify({"ok": True})
        data = get_json()
        username = str(data.get("username", target.username)).strip()
        role = str(data.get("role", target.role)).lower()
        if role not in {"admin", "teknisi", "viewer"}:
            return json_error("Role tidak valid")
        duplicate = User.query.filter(User.username == username, User.id != target.id).first()
        if duplicate:
            return json_error("Username sudah digunakan", 409)
        regions = data.get("assigned_regions", target.assigned_regions or [])
        if isinstance(regions, str):
            regions = [x.strip() for x in regions.split(",") if x.strip()]
        target.username = username
        target.role = role
        target.assigned_regions = regions if role == "teknisi" else []
        if data.get("password"):
            target.set_password(str(data["password"]))
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/maintenance-config", methods=["GET", "POST"])
    @roles_required("admin", "viewer")
    def maintenance_config_collection():
        if request.method == "GET":
            return jsonify(
                {
                    "ok": True,
                    "configs": [
                        maintenance_config_payload(row)
                        for row in MaintenanceConfig.query.order_by(
                            MaintenanceConfig.item_code
                        ).all()
                    ],
                }
            )
        if current_user().role != "admin":
            return json_error("Viewer hanya memiliki akses baca", 403)
        clean, error = validate_maintenance_config(get_json())
        if error:
            return json_error(error)
        if MaintenanceConfig.query.filter_by(item_code=clean["item_code"]).first():
            return json_error("Item code sudah digunakan", 409)
        row = MaintenanceConfig(**clean)
        db.session.add(row)
        db.session.commit()
        return jsonify({"ok": True, "config": maintenance_config_payload(row)}), 201

    @app.route(
        "/api/maintenance-config/<int:config_id>", methods=["GET", "PUT", "DELETE"]
    )
    @roles_required("admin", "viewer")
    def maintenance_config_item(config_id: int):
        row = db.session.get(MaintenanceConfig, config_id)
        if not row:
            return json_error("Konfigurasi tidak ditemukan", 404)
        if request.method == "GET":
            return jsonify({"ok": True, "config": maintenance_config_payload(row)})
        if current_user().role != "admin":
            return json_error("Viewer hanya memiliki akses baca", 403)
        if request.method == "DELETE":
            db.session.delete(row)
            db.session.commit()
            return jsonify({"ok": True})
        clean, error = validate_maintenance_config(get_json(), partial=True)
        if error:
            return json_error(error)
        for key, value in clean.items():
            setattr(row, key, value)
        db.session.commit()
        return jsonify({"ok": True, "config": maintenance_config_payload(row)})

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "service": "HD Machine Monitoring"})


def validate_maintenance_config(
    data: dict[str, Any], partial: bool = False
) -> tuple[dict, str | None]:
    fields = [
        "item_code",
        "name",
        "description",
        "threshold_type",
        "threshold_value",
        "time_unit",
        "active",
    ]
    if not partial:
        required = ["item_code", "name", "threshold_type", "threshold_value"]
        missing = [key for key in required if data.get(key) in ("", None)]
        if missing:
            return {}, f"Field wajib: {', '.join(missing)}"
    clean = {key: data.get(key) for key in fields if key in data}
    if "item_code" in clean:
        clean["item_code"] = str(clean["item_code"]).strip().lower().replace(" ", "_")
    if "threshold_type" in clean and clean["threshold_type"] not in {
        "treatment_count",
        "time_interval",
    }:
        return {}, "Tipe threshold tidak valid"
    if "threshold_value" in clean:
        try:
            clean["threshold_value"] = int(clean["threshold_value"])
            if clean["threshold_value"] <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return {}, "Nilai threshold harus bilangan bulat positif"
    threshold_type = clean.get("threshold_type", data.get("threshold_type"))
    if threshold_type == "time_interval":
        if clean.get("time_unit", data.get("time_unit")) not in {"days", "months"}:
            return {}, "Satuan waktu harus days atau months"
    elif "time_unit" in clean:
        clean["time_unit"] = None
    if "active" in clean:
        clean["active"] = bool(clean["active"])
    return clean, None


def maintenance_config_payload(row: MaintenanceConfig) -> dict[str, Any]:
    return {
        "id": row.id,
        "item_code": row.item_code,
        "name": row.name,
        "description": row.description or "",
        "threshold_type": row.threshold_type,
        "threshold_value": row.threshold_value,
        "time_unit": row.time_unit,
        "active": row.active,
    }


def seed_demo_data() -> None:
    if Machine.query.count():
        return
    demo_rows = [
        ("XT-098989", "RSUD Bekasi", 3, "Jawa Barat", "Bekasi", "Non-KSO", 48),
        ("XT-098978", "RSUD Bekasi", 1, "Jawa Barat", "Bekasi", "Non-KSO", 38),
        ("XT-098999", "RSUD Bekasi", 2, "Jawa Barat", "Bekasi", "KSO", 210),
        ("XT-736374", "RSUD Bekasi", 4, "Jawa Barat", "Bekasi", "KSO", 221),
        ("XT-8878758", "RSUD Bekasi", 5, "Jawa Barat", "Bekasi", "Non-KSO", 19),
        ("XT-201001", "RSUD Kab Bekasi", 1, "Jawa Barat", "Bekasi", "Non-KSO", 51),
        ("XT-301001", "RS Bandung", 1, "Jawa Barat", "Bandung", "KSO", 45),
        ("XT-301002", "RS Bandung", 2, "Jawa Barat", "Bandung", "Non-KSO", 76),
        ("XT-401001", "RS Cianjur", 1, "Jawa Barat", "Cianjur", "Non-KSO", 22),
        ("XT-501001", "RS Surabaya", 1, "Jawa Timur", "Surabaya", "Non-KSO", 201),
        ("XT-501002", "RS Surabaya", 2, "Jawa Timur", "Surabaya", "KSO", 31),
        ("XT-601001", "RS Pontianak", 1, "Kalimantan Barat", "Pontianak", "KSO", 42),
        ("XT-701001", "RS Kupang", 1, "NTT", "Kupang", "Non-KSO", 69),
        ("XT-801001", "RS Medan", 1, "Sumatera Utara", "Medan", "Non-KSO", 92),
        ("XT-901001", "RS Jakarta", 1, "Jabodetabek", "Jakarta", "Non-KSO", 18),
    ]
    demo_rows.extend(
        [
            (
                f"XT-99{index:04d}",
                f"RS Mitra {index:03d}",
                1,
                "Lainnya",
                f"Kota {index:03d}",
                "KSO" if index % 3 == 0 else "Non-KSO",
                120 + index,
            )
            for index in range(1, 101)
        ]
    )
    today = date.today()
    for serial_number, hospital, unit, region, subregion, category, dialysis_count in demo_rows:
        machine_id = normalize_machine_id(serial_number)
        machine = Machine(
            machine_id=machine_id,
            status="stopped",
            pump_status="stopped",
            last_update=utcnow() - timedelta(minutes=10 + unit),
            total_active_time=float((unit + 1) * 18520),
            total_dialysis_time=float((unit + 1) * 14400),
            completed_treatments=dialysis_count + 8,
            completed_dialysis=dialysis_count,
        )
        requires_demo_maintenance = (
            region == "Lainnya"
            or serial_number in {"XT-098999", "XT-736374", "XT-501001"}
        )
        machine.metadata_record = MachineMetadata(
            machine_id=machine_id,
            serial_number=serial_number,
            hospital_name=hospital,
            unit_number=unit,
            region=region,
            subregion=subregion,
            category=category,
            installation_date=(
                today - timedelta(days=400 + unit * 10)
                if requires_demo_maintenance
                else today - timedelta(days=45 + unit)
            ),
        )
        db.session.add(machine)
        for point in range(24):
            db.session.add(
                HumidityLog(
                    machine_id=machine_id,
                    humidity=58 + ((point * 3 + unit) % 14),
                    timestamp=utcnow() - timedelta(minutes=(24 - point) * 15),
                )
            )
    db.session.add_all(
        [
            MaintenanceConfig(
                item_code="filter_inlet",
                name="Filter Endotoksin",
                description="Ganti filter endotoksin sesuai jumlah treatment.",
                threshold_type="treatment_count",
                threshold_value=100,
            ),
            MaintenanceConfig(
                item_code="filter_internal",
                name="Filter Internal",
                description="Pemeriksaan filter di dalam mesin.",
                threshold_type="time_interval",
                threshold_value=6,
                time_unit="months",
            ),
        ]
    )
    if not User.query.filter_by(username="teknisi").first():
        technician = User(
            username="teknisi", role="teknisi", assigned_regions=["Bekasi", "Bandung"]
        )
        technician.set_password("teknisi123")
        db.session.add(technician)
    if not User.query.filter_by(username="viewer").first():
        viewer = User(username="viewer", role="viewer", assigned_regions=[])
        viewer.set_password("viewer123")
        db.session.add(viewer)
    db.session.flush()
    demo_user = User.query.filter_by(username="admin").first()
    for machine_id in ("098989", "098999", "736374"):
        db.session.add(
            VoltageEvent(
                machine_id=machine_id,
                event_type="spike",
                voltage=242.0,
                timestamp=utcnow() - timedelta(days=2),
            )
        )
    db.session.commit()


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
