"""Isolated Windows MySQL 5.7 schema/constraint smoke test; never uses .env/RDS.

Creates a NEW temp data directory, starts mysqld on a random loopback-only TCP port,
and shuts down that exact instance in finally.
Temp files are retained for inspection. No existing service/database is touched.
"""
from pathlib import Path
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parent
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

BASELINE = """
CREATE DATABASE narrativeos_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE narrativeos_test;
CREATE TABLE users (
 id VARCHAR(191) NOT NULL PRIMARY KEY, email VARCHAR(191) NULL UNIQUE,
 email_verified_at DATETIME(3) NULL, nickname VARCHAR(191) NULL, avatar_url VARCHAR(191) NULL,
 created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3), updated_at DATETIME(3) NOT NULL,
 password_hash VARCHAR(191) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE accounts (
 id VARCHAR(191) NOT NULL PRIMARY KEY,user_id VARCHAR(191) NOT NULL,
 provider ENUM('email','wechat') NOT NULL,provider_account_id VARCHAR(191) NOT NULL,
 union_id VARCHAR(191) NULL,profile_json JSON NULL,
 created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
 UNIQUE KEY accounts_provider_provider_account_id_key(provider,provider_account_id),
 KEY accounts_user_id_idx(user_id),
 FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE auth_sessions (
 id VARCHAR(191) NOT NULL PRIMARY KEY,user_id VARCHAR(191) NOT NULL,
 token_hash VARCHAR(191) NOT NULL UNIQUE,expires_at DATETIME(3) NOT NULL,
 created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),KEY auth_sessions_user_id_idx(user_id),
 FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE verification_codes (
 id VARCHAR(191) NOT NULL PRIMARY KEY,email VARCHAR(191) NOT NULL,code_hash VARCHAR(191) NOT NULL,
 expires_at DATETIME(3) NOT NULL,consumed_at DATETIME(3) NULL,attempts INT NOT NULL DEFAULT 0,
 ip VARCHAR(191) NULL,created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
 KEY verification_codes_email_created_at_idx(email,created_at),
 KEY verification_codes_ip_created_at_idx(ip,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

FIXTURE = """
INSERT INTO users(id,updated_at) VALUES ('u1',NOW(3)),('u2',NOW(3));
INSERT INTO games(id,owner_user_id,title) VALUES ('g1','u1','测试作品'),('g2','u2','Other');
INSERT INTO generation_jobs(id,game_id,owner_user_id,request_key,request_hash,job_storage_prefix)
VALUES ('j1','g1','u1','req1',REPEAT('a',64),'jobs/j1'),('j2','g2','u2','req2',REPEAT('b',64),'jobs/j2');
INSERT INTO game_versions(id,game_id,source_job_id,version_no,source_draft_revision,engine_version)
VALUES ('v1','g1','j1',1,1,'4.6.0'),('v2','g2','j2',1,1,'4.6.0');
INSERT INTO assets(id,owner_user_id,source_job_id,name,kind,source_type)
VALUES ('a1','u1','j1','图像','BACKGROUND','GENERATED');
INSERT INTO asset_files(id,asset_id,storage_provider,object_key,location_hash,mime_type,size_bytes)
VALUES ('f1','a1','LOCAL','assets/a1/f1.png',UNHEX(SHA2('location1',256)),'image/png',123);
INSERT INTO asset_usages(game_version_id,logical_path,asset_file_id,usage_role)
VALUES ('v1','background/a.png','f1','background');
INSERT INTO game_likes(game_id,user_id) VALUES('g1','u1');
INSERT INTO game_favorites(game_id,user_id) VALUES('g1','u1');
INSERT INTO products(id,sku,name,kind,price_fen,benefit_json)
VALUES('sku1','TEST_ONLY','测试额度包','CREDIT_PACK',100,JSON_OBJECT('units',10,'schema_version',1));
INSERT INTO purchase_orders(id,order_no,user_id,product_id,product_snapshot,total_fen,payable_fen,request_key,request_hash,expires_at)
VALUES('o1','ORDER1','u1','sku1',JSON_OBJECT('units',10),100,100,'buy1',REPEAT('c',64),DATE_ADD(NOW(),INTERVAL 1 HOUR)),
('o2','ORDER2','u2','sku1',JSON_OBJECT('units',10),100,100,'buy2',REPEAT('d',64),DATE_ADD(NOW(),INTERVAL 1 HOUR));
INSERT INTO payment_attempts(id,order_id,channel,merchant_id,app_id,out_trade_no,expected_fen,expires_at)
VALUES('p1','o1','WECHAT_NATIVE','m1','app1','TRADE0001',100,DATE_ADD(NOW(),INTERVAL 1 HOUR));
INSERT INTO entitlement_grants(id,user_id,order_id,units_granted,units_available,starts_at)
VALUES('e1','u1','o1',10,10,NOW(3)),('e2','u2','o2',10,10,NOW(3));
INSERT INTO credit_reservations(id,user_id,job_id,operation_key,units,pricing_snapshot)
VALUES('r1','u1','j1','generate:1',3,JSON_OBJECT('units',3));
INSERT INTO credit_allocations(reservation_id,grant_id,user_id,units) VALUES('r1','e1','u1',3);
INSERT INTO credit_ledger(event_key,grant_id,user_id,action,delta_available,delta_reserved,delta_consumed,delta_revoked,
 available_after,reserved_after,consumed_after,revoked_after)
VALUES('grant:o1','e1','u1','GRANT',10,0,0,0,10,0,0,0);
"""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mysql-bin', default=r'C:\Program Files\MySQL\MySQL Server 5.7\bin')
    args = parser.parse_args()
    bindir = Path(args.mysql_bin)
    basedir = bindir.parent
    temp = Path(tempfile.mkdtemp(prefix='narrativeos-schema-'))
    data = temp / 'data'
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    server_args = [str(bindir/'mysqld.exe'), '--no-defaults', f'--basedir={basedir}', f'--datadir={data}']
    report = {'engine': '', 'transport': f'isolated loopback TCP port {port}', 'checks': [], 'temp_dir': str(temp)}
    print(f'Initializing isolated MySQL in {temp}', flush=True)
    result = subprocess.run(server_args + ['--initialize-insecure'], capture_output=True, creationflags=FLAGS, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8',errors='replace'))
    log = (temp/'server.log').open('wb')
    server = subprocess.Popen(server_args + [f'--port={port}','--bind-address=127.0.0.1',
        '--innodb-buffer-pool-size=32M','--sql-mode=STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'],
        stdout=log,stderr=log,creationflags=FLAGS)
    client = [str(bindir/'mysql.exe'),'--no-defaults','--protocol=TCP','--host=127.0.0.1',f'--port={port}',
              '--user=root','--default-character-set=utf8mb4','--batch','--skip-column-names']

    def sql(statement, database=True, expected_error=None):
        command = client + (['narrativeos_test'] if database else [])
        res = subprocess.run(command,input=statement.encode('utf-8'),capture_output=True,creationflags=FLAGS,timeout=30)
        error = res.stderr.decode('utf-8',errors='replace')
        if expected_error is not None:
            assert res.returncode and f'ERROR {expected_error} ' in error, error or res.stdout.decode()
        elif res.returncode:
            raise RuntimeError(error)
        return res.stdout.decode('utf-8',errors='replace').strip()

    def check(name, statement, error=None, output=None):
        actual = sql(statement,expected_error=error)
        if output is not None:
            assert actual == output, (name,actual,output)
        report['checks'].append({'name':name,'result':'PASS'})
        print('PASS',name,flush=True)

    try:
        for _ in range(60):
            if server.poll() is not None:
                raise RuntimeError((temp/'server.log').read_text(errors='replace'))
            try:
                report['engine'] = sql('SELECT VERSION()',False)
                break
            except RuntimeError:
                time.sleep(0.25)
        else:
            raise RuntimeError('isolated server did not become ready')
        sql(BASELINE,False)
        check('read-only preflight', (ROOT/'00_preflight.sql').read_text(encoding='utf-8'))
        for file in ['01_content.sql','07_database_job_store.sql','06_asset_library.sql','02_commerce.sql','03_credit_usage.sql','04_auth_additions_optional.sql']:
            check('execute '+file,(ROOT/file).read_text(encoding='utf-8'))
        check('fixture insert across all domains',FIXTURE)
        project_root = ROOT.parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        from webgal_backend.config import settings
        from webgal_backend.storage import JobStore
        object.__setattr__(settings, 'database_url', f'mysql://root@127.0.0.1:{port}/narrativeos_test?charset=utf8mb4')
        db_store = JobStore(temp/'jobs', database_enabled=True)
        app_job = db_store.create('database authority test', {'classroom_topic':'DB Job'}, {'type':'sso','user_id':'u1'})
        stale_job = db_store.get(app_job['id'])
        db_store.transition(app_job, 'RUNNING', 'NARRATIVE_PLANNING')
        db_store.record_artifact(app_job, 'plan', 'state/plan.json')
        db_store.mark_draft_changed(app_job, 'outline')
        loaded_job = db_store.get(app_job['id'])
        assert loaded_job['status'] == 'RUNNING' and loaded_job['artifacts']['plan'] == 'state/plan.json'
        assert loaded_job['draft_revision'] == 1 and loaded_job['dirty_scopes'] == ['outline']
        assert any(item['id'] == app_job['id'] for item in db_store.list({'type':'sso','user_id':'u1'}))
        stale_job['phase'] = 'STALE_WRITE'
        try:
            db_store.save(stale_job)
        except RuntimeError as exc:
            assert 'concurrently' in str(exc)
        else:
            raise AssertionError('stale database job update was accepted')
        report['checks'].append({'name':'database JobStore CRUD and optimistic lock','result':'PASS'})
        print('PASS database JobStore CRUD and optimistic lock',flush=True)
        check('duplicate like rejected',"INSERT INTO game_likes VALUES('g1','u1',NOW(3));",1062)
        check('duplicate favorite rejected',"INSERT INTO game_favorites VALUES('g1','u1',NOW(3));",1062)
        check('job cannot belong to another owner',"INSERT INTO generation_jobs(id,game_id,owner_user_id,request_key,request_hash,job_storage_prefix) VALUES('badjob','g1','u2','bad',REPEAT('a',64),'jobs/bad');",1452)
        check('version cannot reference another game job',"UPDATE game_versions SET source_job_id='j2' WHERE id='v1';",1452)
        check('current version cannot belong to another game',"UPDATE games SET current_version_id='v2' WHERE id='g1';",1452)
        check('asset source must have same owner',"UPDATE assets SET source_job_id='j2' WHERE id='a1';",1452)
        check('referenced file cannot be deleted',"DELETE FROM asset_files WHERE id='f1';",1451)
        check('user with business records cannot be deleted',"DELETE FROM users WHERE id='u1';",1451)
        pay2="INSERT INTO payment_attempts(id,order_id,channel,merchant_id,app_id,out_trade_no,expected_fen,expires_at) VALUES('p2','o1','WECHAT_NATIVE','m1','app1','TRADE0002',100,NOW(3));"
        check('two unresolved payments prohibited',pay2,1062)
        check('confirmed close permits new payment',"UPDATE payment_attempts SET status='CLOSED' WHERE id='p1';"+pay2)
        check('settle one payment',"UPDATE payment_attempts SET status='SUCCESS',transaction_id='tx1',paid_total_fen=100 WHERE id='p2'; UPDATE purchase_orders SET status='PAID',paid_attempt_id='p2' WHERE id='o1';")
        check('duplicate channel transaction rejected',"UPDATE payment_attempts SET transaction_id='tx1' WHERE id='p1';",1062)
        check('order cannot use another order payment',"UPDATE purchase_orders SET paid_attempt_id='p2' WHERE id='o2';",1452)
        check('refund cannot cross order',"INSERT INTO refunds(id,order_id,payment_attempt_id,out_refund_no,request_key,request_hash,amount_fen,reason) VALUES('rf1','o2','p2','REFUND1','refund1',REPEAT('f',64),100,'test');",1452)
        check('grant cannot belong to wrong buyer',"INSERT INTO entitlement_grants(id,user_id,order_id,benefit_key,units_granted,units_available,starts_at) VALUES('badgrant','u2','o1','wrong',10,10,NOW(3));",1452)
        check('duplicate fulfillment rejected',"INSERT INTO entitlement_grants(id,user_id,order_id,units_granted,units_available,starts_at) VALUES('e3','u1','o1',10,10,NOW(3));",1062)
        check('credit allocation cannot spend another user grant',"UPDATE credit_allocations SET grant_id='e2' WHERE reservation_id='r1';",1452)
        check('cannot charge another user job',"INSERT INTO credit_reservations(id,user_id,job_id,operation_key,units,pricing_snapshot) VALUES('r2','u1','j2','generate:2',1,JSON_OBJECT());",1452)
        check('job cannot have two unsettled charged operations',"INSERT INTO credit_reservations(id,user_id,job_id,operation_key,units,pricing_snapshot) VALUES('r2','u1','j1','generate:2',1,JSON_OBJECT());",1062)
        check('reserve then capture units transactionally',"START TRANSACTION; SELECT id INTO @locked FROM entitlement_grants WHERE id='e1' FOR UPDATE; UPDATE entitlement_grants SET units_available=units_available-3,units_reserved=units_reserved+3 WHERE id='e1' AND status='ACTIVE' AND units_available>=3; UPDATE entitlement_grants SET units_reserved=units_reserved-3,units_consumed=units_consumed+3 WHERE id='e1' AND units_reserved>=3; UPDATE credit_reservations SET status='CAPTURED',settled_at=NOW(3) WHERE id='r1' AND status='RESERVED'; COMMIT; SELECT CONCAT(units_available,',',units_reserved,',',units_consumed) FROM entitlement_grants WHERE id='e1';",output='7,0,3')
        check('insufficient balance conditional update is no-op',"UPDATE entitlement_grants SET units_available=units_available-8,units_reserved=units_reserved+8 WHERE id='e1' AND units_available>=8; SELECT ROW_COUNT();",output='0')
        check('duplicate credit event rejected',"INSERT INTO credit_ledger(event_key,grant_id,user_id,action,delta_available,delta_reserved,delta_consumed,delta_revoked,available_after,reserved_after,consumed_after,revoked_after) VALUES('grant:o1','e1','u1','GRANT',10,0,0,0,10,0,0,0);",1062)
        check('notification uniqueness',"INSERT INTO payment_notifications(id,channel,merchant_id,notification_id,event_type,body_sha256) VALUES('n1','WECHAT_NATIVE','m1','notice1','TRANSACTION.SUCCESS',REPEAT('a',64));")
        check('duplicate notification rejected',"INSERT INTO payment_notifications(id,channel,merchant_id,notification_id,event_type,body_sha256) VALUES('n2','WECHAT_NATIVE','m1','notice1','TRANSACTION.SUCCESS',REPEAT('a',64));",1062)
        check('outbox event uniqueness',"INSERT INTO outbox_events(id,event_key,event_type,aggregate_id,payload_json) VALUES('ob1','paid:o1','ORDER_PAID','o1',JSON_OBJECT());")
        check('duplicate outbox event rejected',"INSERT INTO outbox_events(id,event_key,event_type,aggregate_id,payload_json) VALUES('ob2','paid:o1','ORDER_PAID','o1',JSON_OBJECT());",1062)
        check('consistency query syntax', (ROOT/'05_consistency_checks.sql').read_text(encoding='utf-8'))
        tables = []
        for filename in ['01_content.sql','02_commerce.sql','03_credit_usage.sql','06_asset_library.sql','07_database_job_store.sql']:
            tables.extend(re.findall(r'CREATE TABLE (\w+)',(ROOT/filename).read_text(encoding='utf-8')))
        dictionary = ['# 业务表字段字典', '',
            '由本次独立 MySQL 实例的 information_schema 导出；20 张新业务表。完整索引/外键以 SQL 为准。', '',
            '用户 ID 沿用 VARCHAR(191)，其余 CHAR(32) 业务 ID 由应用生成 UUID hex；AUTO_INCREMENT 流水 ID 除外。', '',
            '余额与金额关系、所有权授权、合法状态转换等应用层规则见 PLAN.md 与 TRANSACTIONS.md。', '']
        for table in tables:
            comment=sql(f"SELECT TABLE_COMMENT FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='{table}';")
            dictionary.extend([f'## {table}', '', comment, '', '| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 / 额外属性 |','|---|---|---|---|---|---|'])
            rows=sql(f"SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COALESCE(COLUMN_DEFAULT,'—'),COLUMN_KEY,CONCAT(COLUMN_COMMENT,' ',EXTRA) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='{table}' ORDER BY ORDINAL_POSITION;")
            for row in rows.splitlines():
                cells=row.split('\t')
                cells.extend([''] * (6-len(cells)))
                dictionary.append('| '+' | '.join(c.replace('|','\\|').strip() or '—' for c in cells)+' |')
            dictionary.append('')
        (ROOT/'DATA_DICTIONARY.md').write_text('\n'.join(dictionary)+'\n',encoding='utf-8')
        report['table_count'] = int(sql("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE();"))
        report['foreign_key_count'] = int(sql("SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=DATABASE() AND CONSTRAINT_TYPE='FOREIGN KEY';"))
        report['scope'] = 'DDL, constraints, SQL state examples, and database JobStore CRUD/optimistic-lock integration; NOT external payment or OSS end-to-end tests.'
        report['result'] = 'PASS'
    finally:
        try:
            subprocess.run([str(bindir/'mysqladmin.exe'),'--no-defaults','--protocol=TCP','--host=127.0.0.1',f'--port={port}',
                '--user=root','shutdown'],capture_output=True,creationflags=FLAGS,timeout=15)
            server.wait(timeout=15)
        except (subprocess.TimeoutExpired, OSError):
            server.terminate()
            server.wait(timeout=10)
        log.close()
        report['server_stopped'] = server.poll() is not None
        (ROOT/'VALIDATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='checks'},ensure_ascii=False),flush=True)

if __name__ == '__main__':
    main()
