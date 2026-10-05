-- One-time migration required by credit_system.
-- Separates paid-order entitlements from promotions/admin grants so signup
-- credits never masquerade as a successful payment.

ALTER TABLE `entitlement_grants`
  ADD COLUMN `source` enum('ORDER','PROMOTION','ADMIN')
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'ORDER'
    AFTER `user_id`,
  ADD COLUMN `source_key` varchar(64)
    CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL
    AFTER `source`,
  MODIFY COLUMN `order_id` char(32)
    CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  ADD UNIQUE KEY `uq_grant_source` (`user_id`,`source`,`source_key`);

-- Existing rows remain source=ORDER. Backfill their idempotency key.
UPDATE `entitlement_grants`
SET `source_key` = `order_id`
WHERE `source` = 'ORDER' AND `source_key` IS NULL;
