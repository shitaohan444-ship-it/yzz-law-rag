\pset pager off
\set ON_ERROR_STOP on

\echo ===== R2-03A POSTGRES PRESIGNED URL AUDIT =====
\echo

DROP TABLE IF EXISTS pg_temp.presigned_url_audit;

CREATE TEMP TABLE presigned_url_audit (
    table_schema text,
    table_name text,
    column_name text,
    matched_rows bigint
);

SELECT format(
    'INSERT INTO pg_temp.presigned_url_audit ' ||
    'SELECT %L, %L, %L, COUNT(*) ' ||
    'FROM %I.%I ' ||
    'WHERE CAST(%I AS text) ~* %L;',
    c.table_schema,
    c.table_name,
    c.column_name,
    c.table_schema,
    c.table_name,
    c.column_name,
    'X-Amz-(Algorithm|Credential|Date|Expires|Signature|SignedHeaders)'
)
FROM information_schema.columns AS c
WHERE c.table_schema = 'oa'
  AND c.data_type IN (
      'character varying',
      'text',
      'json',
      'jsonb'
  )
ORDER BY
    c.table_name,
    c.ordinal_position
\gexec

\echo ===== 1. AUDITED COLUMN COUNT =====

SELECT COUNT(*) AS audited_column_count
FROM pg_temp.presigned_url_audit;

\echo
\echo ===== 2. MATCHED TABLE AND COLUMN COUNT =====

SELECT COUNT(*) AS matched_column_count
FROM pg_temp.presigned_url_audit
WHERE matched_rows > 0;

\echo
\echo ===== 3. MATCH DETAILS =====

SELECT
    table_schema,
    table_name,
    column_name,
    matched_rows
FROM pg_temp.presigned_url_audit
WHERE matched_rows > 0
ORDER BY
    matched_rows DESC,
    table_name,
    column_name;

\echo
\echo ===== 4. TOTAL MATCHED ROW REFERENCES =====

SELECT COALESCE(SUM(matched_rows), 0) AS total_matched_row_references
FROM pg_temp.presigned_url_audit
WHERE matched_rows > 0;
