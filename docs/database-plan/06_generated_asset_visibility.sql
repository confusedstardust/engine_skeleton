-- AI-generated assets are permanent shared library entries.
-- User uploads remain private and are never promoted by this migration.

START TRANSACTION;

UPDATE assets
SET visibility = 'PUBLIC', updated_at = CURRENT_TIMESTAMP(3)
WHERE source_type = 'GENERATED'
  AND visibility <> 'PUBLIC';

COMMIT;

SELECT source_type, visibility, COUNT(*) AS asset_count
FROM assets
WHERE source_type IN ('GENERATED', 'UPLOADED')
GROUP BY source_type, visibility
ORDER BY source_type, visibility;
