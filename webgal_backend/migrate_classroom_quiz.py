"""Explicit additive migration: python -m webgal_backend.migrate_classroom_quiz."""
from pathlib import Path
from webgal_backend.database import database_transaction


def main():
    source = Path(__file__).resolve().parents[1] / 'webgal_backend/migrations/001_classroom_quiz.sql'
    with database_transaction() as cursor:
        for statement in source.read_text(encoding='utf-8').split(';'):
            if statement.strip():
                cursor.execute(statement)
    print('Classroom quiz tables ready. MySQL DDL is additive and may commit implicitly.')


if __name__ == '__main__':
    main()
