import pandas as pd
import numpy as np
# import psycopg2
from datetime import datetime
import time
import json


def put_query(engine,
              logger,
              json_file,
              table_name: str,
              attempts: int = 2,
              result=None
              ):
    """Загружает запрос в БД"""

    try:
        res_id = result.json()["result"]["AddResults"][0].get("Id", None)
        # print("res_id ", res_id)
        if res_id is not None:
            json_file.setdefault("res_id", res_id)

        res_warnings = result.json()["result"]["AddResults"][0].get("Warnings", None)
        # print("res_warnings ", res_warnings)
        if res_warnings is not None:
            json_file.setdefault("res_warnings", [json.dumps(i, ensure_ascii=False).encode('utf8').decode('utf8') for i in res_warnings])

        res_errors = result.json()["result"]["AddResults"][0].get("Errors", None)
        # print("res_errors ", res_errors)
        if res_errors is not None:
            json_file.setdefault("res_errors", [json.dumps(i, ensure_ascii=False).encode('utf8').decode('utf8') for i in res_errors])
    except KeyError:
        res_errors = result.json().get("error", None)
        # print("res_errors2 ", res_errors)
        if res_errors is not None:
            json_file.setdefault("res_errors", [json.dumps(res_errors, ensure_ascii=False).encode('utf8').decode('utf8')])

    dataset = pd.DataFrame([json_file])
    dataset['date_time'] = datetime.now()

    # print(dataset['res_warnings'][0])
    # print(json_file)

    with engine.begin() as connection:
        n = 0
        while n < attempts:
            try:
                res = dataset.to_sql(name=table_name, con=connection, if_exists='append', index=False)
                logger.info(f"Upload to {table_name} - ok")
                return 'ok'
            except BaseException as ex:
                logger.error(f"data to db: {ex}")
                time.sleep(5)
                n += 1
        logger.error("data to db error")
        return None


def get_clients(account_id: int, engine, logger):
    """Получает список доступных аккаунтов для клиента"""

    query = f"""
             SELECT account_id AS api_id, attribute_value AS login 
             FROM account_service_data asd 
             WHERE attribute_id = 24 AND account_id = {account_id}
             """

    with engine.begin() as connection:
        try:
            data = pd.read_sql(query, con=connection)

            if data is None:
                logger.error("accounts database error")
                return None
            elif data.shape[0] == 0:
                logger.info("non-existent account")
                return []
            else:
                return data['login'].tolist()

        except BaseException as ex:
            logger.error(f"get clients: {ex}")
            # print('Нет подключения к БД')
            return None

def get_objects_from_db(login: str, table_name: str, engine, logger):
    """Получает кампании клиента созданные через сервис"""

    query = f"""
             SELECT * 
             FROM {table_name} 
             WHERE res_id IS NOT NULL AND login = '{login}'
             """

    with engine.begin() as connection:
        try:
            data = pd.read_sql(query, con=connection)

            if data is None:
                logger.error("accounts database error")
                return None
            elif data.shape[0] == 0:
                logger.info(f"no data for account {login}")
                return []
            else:
                return data.to_dict(orient='records')

        except BaseException as ex:
            logger.error(f"get objects: {ex}")
            # print('Нет подключения к БД')
            return None







# def update_query_status(table_name, query_id, res_id, res_warnings, res_errors):
#     """Записывает в таблицу ответ яндекс"""
#
#     query = f"""
#             UPDATE {table_name} SET res_id = {res_id}, res_warnings = {res_warnings}, res_errors = {res_errors}
#             WHERE id = {query_id}
#             """
#
#     try:
#         conn = psycopg2.connect(db_access)
#         q = conn.cursor()
#         q.execute(query)
#         conn.commit()
#         status = q.statusmessage
#         q.close()
#         conn.close()
#         return status
#     except:
#         print('Нет подключения к БД, или нет доступа на выполнение операции')
#         return None


