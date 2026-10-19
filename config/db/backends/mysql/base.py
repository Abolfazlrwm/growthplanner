"""Django MySQL backend with split column/FK ALTERs for managed MySQL proxies.

Some MySQL-compatible servers reject a foreign key referencing a column added
within the same ALTER TABLE statement. Deferred FK creation avoids that dialect
edge case without dropping constraints or changing historical migrations.
"""
from django.db.backends.mysql.base import DatabaseWrapper as MySQLDatabaseWrapper
from django.db.backends.mysql.schema import DatabaseSchemaEditor as MySQLSchemaEditor


class DatabaseSchemaEditor(MySQLSchemaEditor):
    sql_create_column_inline_fk = None


class DatabaseWrapper(MySQLDatabaseWrapper):
    SchemaEditorClass = DatabaseSchemaEditor
