-- Migrasi untuk database HD Machine Monitoring yang SUDAH berisi delapan tabel.
-- Aman dijalankan ulang: kolom, constraint, dan index hanya ditambahkan jika belum ada.

BEGIN;

ALTER TABLE machine_metadata
    ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN IF NOT EXISTS archived_by INTEGER,
    ADD COLUMN IF NOT EXISTS archive_note TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_machine_metadata_archived_by'
          AND conrelid = 'machine_metadata'::regclass
    ) THEN
        ALTER TABLE machine_metadata
            ADD CONSTRAINT fk_machine_metadata_archived_by
            FOREIGN KEY (archived_by) REFERENCES users(id);
    END IF;
END
$$;

ALTER TABLE maintenance
    ADD COLUMN IF NOT EXISTS serial_number_snapshot VARCHAR(50),
    ADD COLUMN IF NOT EXISTS item_name_snapshot VARCHAR(100),
    ADD COLUMN IF NOT EXISTS performed_by_snapshot VARCHAR(50);

-- Isi snapshot untuk riwayat lama sebelum kolom diwajibkan NOT NULL.
UPDATE maintenance AS m
SET serial_number_snapshot = COALESCE(
        NULLIF(BTRIM(m.serial_number_snapshot), ''),
        mm.serial_number,
        m.machine_id,
        'Mesin tidak tersedia'
    )
FROM machine_metadata AS mm
WHERE mm.machine_id = m.machine_id
  AND (m.serial_number_snapshot IS NULL OR BTRIM(m.serial_number_snapshot) = '');

UPDATE maintenance
SET serial_number_snapshot = COALESCE(
        NULLIF(BTRIM(serial_number_snapshot), ''),
        machine_id,
        'Mesin tidak tersedia'
    )
WHERE serial_number_snapshot IS NULL OR BTRIM(serial_number_snapshot) = '';

UPDATE maintenance AS m
SET item_name_snapshot = COALESCE(
        NULLIF(BTRIM(m.item_name_snapshot), ''),
        mc.name,
        m.item
    )
FROM maintenance_config AS mc
WHERE mc.item_code = m.item
  AND (m.item_name_snapshot IS NULL OR BTRIM(m.item_name_snapshot) = '');

UPDATE maintenance
SET item_name_snapshot = COALESCE(
        NULLIF(BTRIM(item_name_snapshot), ''),
        item,
        'Item tidak tersedia'
    )
WHERE item_name_snapshot IS NULL OR BTRIM(item_name_snapshot) = '';

UPDATE maintenance AS m
SET performed_by_snapshot = COALESCE(
        NULLIF(BTRIM(m.performed_by_snapshot), ''),
        u.username,
        'User tidak tersedia'
    )
FROM users AS u
WHERE u.id = m.performed_by
  AND (m.performed_by_snapshot IS NULL OR BTRIM(m.performed_by_snapshot) = '');

UPDATE maintenance
SET performed_by_snapshot = COALESCE(
        NULLIF(BTRIM(performed_by_snapshot), ''),
        'User tidak tersedia'
    )
WHERE performed_by_snapshot IS NULL OR BTRIM(performed_by_snapshot) = '';

UPDATE maintenance
SET description = 'Catatan tidak tersedia (riwayat lama)'
WHERE description IS NULL OR BTRIM(description) = '';

ALTER TABLE maintenance
    ALTER COLUMN description SET NOT NULL,
    ALTER COLUMN serial_number_snapshot SET NOT NULL,
    ALTER COLUMN item_name_snapshot SET NOT NULL,
    ALTER COLUMN performed_by_snapshot SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_metadata_archive_region_subregion
    ON machine_metadata (is_archived, region, subregion);

CREATE INDEX IF NOT EXISTS idx_maintenance_history_time
    ON maintenance (timestamp DESC, id DESC);

COMMIT;
