"""Enable PyMySQL for managed MySQL; PostgreSQL and SQLite remain supported."""
import pymysql
pymysql.version_info = (2, 2, 7, "final", 0)
pymysql.install_as_MySQLdb()
