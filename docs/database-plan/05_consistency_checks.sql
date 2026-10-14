-- READ ONLY. Run after 01 + 02 + 03. Unexpected rows indicate investigation.
-- These checks detect drift; they do not repair it and cannot validate OSS existence.
SET time_zone = '+00:00';

-- 1. Cached engagement counts vs facts.
SELECT g.id,g.like_count,COALESCE(l.n,0) AS actual_likes,
       g.favorite_count,COALESCE(f.n,0) AS actual_favorites
FROM games g
LEFT JOIN (SELECT game_id,COUNT(*) n FROM game_likes GROUP BY game_id) l ON l.game_id=g.id
LEFT JOIN (SELECT game_id,COUNT(*) n FROM game_favorites GROUP BY game_id) f ON f.game_id=g.id
WHERE g.like_count<>COALESCE(l.n,0) OR g.favorite_count<>COALESCE(f.n,0);

-- 2. Published game must have an approved, usable same-game version.
SELECT g.id,g.status,g.current_version_id,v.status AS version_status,v.review_status
FROM games g LEFT JOIN game_versions v ON v.id=g.current_version_id
WHERE g.status='PUBLISHED' AND g.deleted_at IS NULL
AND (v.id IS NULL OR v.game_id<>g.id OR v.status<>'READY' OR v.review_status<>'APPROVED');

-- 3. Ready versions referencing files not ready.
SELECT u.game_version_id,u.logical_path,u.asset_file_id,f.status
FROM asset_usages u JOIN game_versions v ON v.id=u.game_version_id
JOIN asset_files f ON f.id=u.asset_file_id
WHERE v.status='READY' AND f.status<>'READY';

-- 4. Order amounts and local success relation.
SELECT id,total_fen,discount_fen,payable_fen,status FROM purchase_orders
WHERE payable_fen=0 OR quantity=0 OR total_fen<>discount_fen+payable_fen;
SELECT o.id,o.status,o.paid_attempt_id,p.status AS payment_status
FROM purchase_orders o LEFT JOIN payment_attempts p ON p.id=o.paid_attempt_id
WHERE o.status IN ('PAID','PARTIALLY_REFUNDED','REFUNDED')
AND (p.id IS NULL OR p.order_id<>o.id OR p.status<>'SUCCESS' OR p.paid_total_fen<>o.payable_fen OR p.paid_total_fen IS NULL);
SELECT id,order_id,status FROM payment_attempts
WHERE status='SUCCESS' AND (transaction_id IS NULL OR paid_total_fen IS NULL OR paid_total_fen<>expected_fen);

-- 5. Multiple successful payments: financial exception, not a reason to delete rows.
SELECT order_id,COUNT(*) AS successful_attempts FROM payment_attempts
WHERE status='SUCCESS' GROUP BY order_id HAVING COUNT(*)>1;

-- 6. Refund counters must agree with refund detail rows.
SELECT p.id,p.paid_total_fen,p.refunded_fen,p.refund_reserved_fen,
       COALESCE(r.done,0) actual_refunded,COALESCE(r.pending,0) actual_reserved
FROM payment_attempts p LEFT JOIN (
  SELECT payment_attempt_id,
  SUM(CASE WHEN status='SUCCESS' THEN amount_fen ELSE 0 END) done,
  SUM(CASE WHEN status IN ('REQUESTED','PROCESSING','UNKNOWN') THEN amount_fen ELSE 0 END) pending
  FROM refunds GROUP BY payment_attempt_id
) r ON r.payment_attempt_id=p.id
WHERE p.refunded_fen<>COALESCE(r.done,0) OR p.refund_reserved_fen<>COALESCE(r.pending,0)
   OR p.refunded_fen+p.refund_reserved_fen>COALESCE(p.paid_total_fen,0);

-- 7. Grant conservation and ledger reconciliation.
SELECT id,user_id FROM entitlement_grants WHERE kind='CREDITS'
AND units_granted<>units_available+units_reserved+units_consumed+units_revoked;
SELECT e.id,e.user_id FROM entitlement_grants e LEFT JOIN (
 SELECT grant_id,SUM(delta_available) a,SUM(delta_reserved) r,SUM(delta_consumed) c,SUM(delta_revoked) v
 FROM credit_ledger GROUP BY grant_id
) l ON l.grant_id=e.id
WHERE e.kind='CREDITS' AND (e.units_available<>COALESCE(l.a,0) OR e.units_reserved<>COALESCE(l.r,0)
 OR e.units_consumed<>COALESCE(l.c,0) OR e.units_revoked<>COALESCE(l.v,0));

-- 8. Reservation allocation totals and grant frozen balance.
SELECT r.id,r.units,COALESCE(a.n,0) allocated FROM credit_reservations r
LEFT JOIN (SELECT reservation_id,SUM(units) n FROM credit_allocations GROUP BY reservation_id) a ON a.reservation_id=r.id
WHERE r.units<>COALESCE(a.n,0);
SELECT e.id,e.units_reserved,COALESCE(a.n,0) actual_reserved FROM entitlement_grants e
LEFT JOIN (
 SELECT a.grant_id,SUM(a.units) n FROM credit_allocations a
 JOIN credit_reservations r ON r.id=a.reservation_id WHERE r.status='RESERVED' GROUP BY a.grant_id
) a ON a.grant_id=e.id
WHERE e.kind='CREDITS' AND e.units_reserved<>COALESCE(a.n,0);

-- 9. Fulfillment exceptions (one credits benefit per order in first release).
SELECT o.id,o.status,o.fulfillment_status FROM purchase_orders o
LEFT JOIN entitlement_grants e ON e.order_id=o.id AND e.benefit_key='credits'
WHERE o.fulfillment_status='FULFILLED' AND e.id IS NULL;
SELECT e.id,e.order_id,o.status FROM entitlement_grants e JOIN purchase_orders o ON o.id=e.order_id
WHERE e.status='ACTIVE' AND o.status NOT IN ('PAID','PARTIALLY_REFUNDED');

-- 10. Operational queues: nonempty can be normal; alert by age/SLA.
SELECT id,order_no,paid_at FROM purchase_orders WHERE status='PAID'
AND fulfillment_status IN ('PENDING','PROCESSING','FAILED') ORDER BY paid_at;
SELECT id,status,lease_expires_at FROM generation_jobs WHERE status='RUNNING'
AND (lease_expires_at IS NULL OR lease_expires_at<UTC_TIMESTAMP(3));
SELECT id,event_type,attempts,last_error FROM outbox_events WHERE status='DEAD'
OR (status='PROCESSING' AND lease_expires_at<UTC_TIMESTAMP(3));
SELECT id,order_id,next_query_at FROM payment_attempts WHERE status='UNKNOWN' ORDER BY created_at;
SELECT id,out_refund_no,next_query_at FROM refunds WHERE status='UNKNOWN' ORDER BY created_at;
