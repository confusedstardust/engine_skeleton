-- READ ONLY. Select target database explicitly in the client before running.
SELECT DATABASE() AS selected_database, VERSION() AS mysql_version,
       @@sql_mode AS sql_mode, @@time_zone AS session_time_zone,
       @@innodb_file_per_table AS innodb_file_per_table;
SHOW VARIABLES WHERE Variable_name IN ('innodb_large_prefix','innodb_file_format','innodb_default_row_format');
SELECT TABLE_NAME, ENGINE, TABLE_COLLATION, ROW_FORMAT
FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME;
SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLLATION_NAME,COLUMN_DEFAULT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('users','accounts','auth_sessions','verification_codes')
ORDER BY TABLE_NAME,ORDINAL_POSITION;
SELECT TABLE_NAME,CONSTRAINT_NAME,CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME,CONSTRAINT_NAME;
SHOW CREATE TABLE users;
SHOW CREATE TABLE accounts;
SHOW CREATE TABLE auth_sessions;
SHOW CREATE TABLE verification_codes;
-- Expected: these business names do NOT already exist. Nonempty result => stop.
SELECT TABLE_NAME AS collision_stop_and_review
FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()
AND TABLE_NAME IN ('games','generation_jobs','game_versions','assets','asset_files',
'asset_usages','game_likes','game_favorites','outbox_events','products','purchase_orders',
'payment_attempts','payment_notifications','refunds','entitlement_grants',
'credit_reservations','credit_allocations','credit_ledger');
