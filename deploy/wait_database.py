"""Wait for the configured private MySQL before starting the API worker."""
import os
import time

import pymysql


def main():
    for attempt in range(60):
        try:
            connection = pymysql.connect(
                host=os.getenv('DNB_DATABASE_HOST', '127.0.0.1'),
                port=int(os.getenv('DNB_DATABASE_PORT', '3307')),
                user=os.environ['DNB_DATABASE_USER'],
                password=os.environ['DNB_DATABASE_PASSWORD'],
                database=os.environ['DNB_DATABASE_NAME'], connect_timeout=2)
            connection.close()
            return
        except pymysql.MySQLError:
            time.sleep(1)
    raise RuntimeError('Private MySQL did not become ready; inspect mysql-service.log')


if __name__ == '__main__':
    main()
