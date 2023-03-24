import os


class Configuration(object):
    DEBUG = False


# errors_warnings_sourse = 'db'
errors_warnings_sourse = 'yandex_direct'


HOST = os.environ.get('ECOMRU_PG_HOST', None)
PORT = os.environ.get('ECOMRU_PG_PORT', None)
SSL_MODE = os.environ.get('ECOMRU_PG_SSL_MODE', None)
DB_NAME = os.environ.get('ECOMRU_PG_DB_NAME', None)
USER = os.environ.get('ECOMRU_PG_USER', None)
PASSWORD = os.environ.get('ECOMRU_PG_PASSWORD', None)
target_session_attrs = 'read-write'

# HOST = 'localhost'
# PORT = '5432'
# DB_NAME = 'postgres'
# USER = 'postgres'
# PASSWORD = ' '

DB_PARAMS = f"postgresql://{USER}:{PASSWORD}@{HOST}:{PORT}/{DB_NAME}"

