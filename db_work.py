import pandas as pd
import numpy as np
# import psycopg2
from datetime import datetime
import time
import json
from ecom_yandex_direct import YandexDirectEcomru


def put_query(engine,
              logger,
              json_file,
              table_name: str,
              attempts: int = 2,
              result=None
              ):
    """Загружает запрос в БД"""

    try:
        res_id = result["result"]["AddResults"][0].get("Id", None)
        # print("res_id ", res_id)
        if res_id is not None:
            json_file.setdefault("res_id", res_id)

        res_warnings = result["result"]["AddResults"][0].get("Warnings", None)
        # print("res_warnings ", res_warnings)
        if res_warnings is not None:
            json_file.setdefault("res_warnings",
                                 [json.dumps(i, ensure_ascii=False).encode('utf8').decode('utf8') for i in
                                  res_warnings])

        res_errors = result["result"]["AddResults"][0].get("Errors", None)
        # print("res_errors ", res_errors)
        if res_errors is not None:
            json_file.setdefault("res_errors",
                                 [json.dumps(i, ensure_ascii=False).encode('utf8').decode('utf8') for i in res_errors])
    except KeyError:
        res_errors = result.get("error", None)
        # print("res_errors2 ", res_errors)
        if res_errors is not None:
            json_file.setdefault("res_errors",
                                 [json.dumps(res_errors, ensure_ascii=False).encode('utf8').decode('utf8')])

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


def get_groups_from_db(login: str,
                       engine,
                       logger,
                       campaign_id: int = None,
                       group_id: int = None,
                       table_name: str = 'ya_ads_addgroups'):
    """Получает группы клиента созданные через сервис"""

    query = f"""
             SELECT * 
             FROM {table_name} 
             WHERE res_id IS NOT NULL AND login = '{login}'
             """

    if campaign_id is not None:
        query += f" AND campaign_id = {campaign_id}"

    if group_id is not None:
        query += f" AND res_id = {group_id}"

    with engine.begin() as connection:
        try:
            data = pd.read_sql(query, con=connection)

            if data is None:
                logger.error("accounts database error")
                return None
            elif data.shape[0] == 0:
                logger.info(f"no data")
                return []
            else:
                return data.to_dict(orient='records')

        except BaseException as ex:
            logger.error(f"get objects: {ex}")
            # print('Нет подключения к БД')
            return None


def get_ads_from_db(login: str,
                    engine,
                    logger,
                    group_id: int = None,
                    ad_id: int = None,
                    table_name: str = 'ya_ads_addads'):
    """Получает объявления клиента созданные через сервис"""

    query = f"""
             SELECT * 
             FROM {table_name} 
             WHERE res_id IS NOT NULL AND login = '{login}'
             """

    if group_id is not None:
        query += f" AND ads_group_id = {group_id}"

    if ad_id is not None:
        query += f" AND res_id = {ad_id}"

    with engine.begin() as connection:
        try:
            data = pd.read_sql(query, con=connection)

            if data is None:
                logger.error("accounts database error")
                return None
            elif data.shape[0] == 0:
                logger.info(f"no data")
                return []
            else:
                return data.to_dict(orient='records')

        except BaseException as ex:
            logger.error(f"get objects: {ex}")
            # print('Нет подключения к БД')
            return None


def add_regions(engine,
                logger,
                data: list[dict],
                table_name: str,
                attempts: int = 2):
    """Записывает данные в таблицу"""

    dataset = pd.DataFrame(data)
    # dataset["ParentId"] = dataset["ParentId"].astype('int', copy=False, errors='ignore')
    # dataset.style.format({'ParentId': '{:,.0f}'.format, 'GeoRegionId': '{:,.0f}'.format})
    dataset = dataset.fillna(-1)
    dataset["ParentId"] = dataset["ParentId"].astype('int', copy=False, errors='ignore')
    print(dataset.dtypes)

    with engine.begin() as connection:
        n = 0
        while n < attempts:
            try:
                res = dataset.to_sql(name=table_name, con=connection, if_exists='replace', index=False)
                logger.info(f"Upload to {table_name} - ok")
                return 'ok'
            except BaseException as ex:
                logger.error(f"data to db: {ex}")
                time.sleep(5)
                n += 1
        logger.error("data to db error")
        return None


def get_table_from_db(table_name: str, engine, logger, type='dict'):
    """Получает таблицу из базы"""

    query = f"""
             SELECT * 
             FROM {table_name}
             """

    with engine.begin() as connection:
        try:
            data = pd.read_sql(query, con=connection)

            if data is None:
                logger.error("database error")
                return None
            elif data.shape[0] == 0:
                logger.info(f"no data")
                if type == 'dict':
                    return []
                elif type == 'df':
                    return data
            else:
                if type == 'dict':
                    return data.to_dict(orient='records')
                elif type == 'df':
                    return data
                # return data.to_json(orient='records')
                # return data.to_json(orient='records').encode('utf8').decode('utf8')

        except BaseException as ex:
            logger.error(f"get table: {ex}")
            # print('Нет подключения к БД')
            return None


def response_result(response, sourсe: str, errors_table, warnings_table):
    """Возвращает словарь с результатом аналогичным YandexDirect подставляя описания ошибок и предупреждений из БД"""

    result = dict()

    res_id = None
    warnings = []
    errors = []

    if response.status_code != 200 or response.json().get("error", False):

        code = response.json()["error"]["error_code"]
        if sourсe == 'db':
            details = errors_table[errors_table.error_code == int(code)]['error_text'].values[0] + ' ' + errors_table[errors_table.error_code == int(code)]['error_comment'].values[0]
        else:
            details = YandexDirectEcomru.u(response.json()["error"]["error_detail"])

        errors.append({'Code': code, 'Details': details})

    else:
        for add in response.json()["result"]["AddResults"]:
            if add.get("Errors", False):
                for error in add["Errors"]:
                    code = error["Code"]
                    if sourсe == 'db':
                        message = errors_table[errors_table.error_code == int(code)]['error_text'].values[0]
                        details = errors_table[errors_table.error_code == int(code)]['error_comment'].values[0]
                    else:
                        message = YandexDirectEcomru.u(error["Message"])
                        details = YandexDirectEcomru.u(error["Details"])

                    errors.append({'Code': code, 'Message': message, 'Details': details})

            else:
                res_id = add["Id"]
                if add.get("Warnings", False):
                    for warning in add["Warnings"]:
                        code = warning["Code"]
                        if sourсe == 'db':
                            message = warnings_table[warnings_table.warning_code == int(code)]['warning_text'].values[0]
                            warnings.append({'Code': code, 'Message': message})
                        else:
                            message = YandexDirectEcomru.u(warning["Message"])
                            details = YandexDirectEcomru.u(warning["Details"])
                            warnings.append({'Code': code, 'Message': message, 'Details': details})

    if res_id is not None:
        result['Id'] = res_id
    if len(warnings) > 0:
        result['Warnings'] = warnings
    if len(errors) > 0:
        result['Errors'] = errors

    return {'result': {"AddResults": [result]}}



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
