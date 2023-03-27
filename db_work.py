import pandas as pd
import numpy as np
import psycopg2
from datetime import datetime
import time
import json
from sqlalchemy import exc
from ecom_yandex_direct import YandexDirectEcomru


def sql_query(query, engine, logger, type_='dict'):
    """Выполнить SQL запрос на чтение"""

    with engine.connect() as connection:
        with connection.begin() as transaction:
            try:
                data = pd.read_sql(query, con=connection)

                if data is None:
                    logger.error("database error")
                    return None
                elif data.shape[0] == 0:
                    logger.info(f"no data")
                    if type_ == 'dict':
                        return []
                    elif type_ == 'df':
                        return data
                else:
                    if type_ == 'dict':
                        return data.to_dict(orient='records')
                    elif type_ == 'df':
                        return data

            except (exc.DBAPIError, exc.SQLAlchemyError):
                logger.error("db error")
                transaction.rollback()
                raise
            except BaseException as ex:
                logger.error(f"{ex}")
                transaction.rollback()
                raise
            finally:
                connection.close()


def add_into_table(dataset, table_name: str, engine,
                   logger,
                   attempts=1):
    """Выполнить запись датасета в таблицу БД"""

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

    # with engine.begin() as connection:
    #     with connection.begin() as transaction:
    #         try:
    #             res = dataset.to_sql(name=table_name, con=connection, if_exists='append', index=False)
    #             # transaction.commit()
    #             logger.info(f"Upload to {table_name} - ok")
    #             # return 'ok'
    #         except (exc.DBAPIError, exc.SQLAlchemyError):
    #             logger.info(f"Upload to {table_name} -error")
    #             transaction.rollback()
    #             raise
    #         finally:
    #             connection.close()


def upd_into_table(query: str, engine, logger):
    """Выполнить запрос на запись в БД"""

    with engine.connect() as connection:
        with connection.begin() as transaction:
            try:
                connection.execute(query)
                transaction.commit()
                logger.info("successful")
            except (exc.DBAPIError, exc.SQLAlchemyError):
                logger.info("error")
                transaction.rollback()
                raise
            # else:
            #     transaction.commit()
            finally:
                connection.close()


def put_query(engine,
              logger,
              json_file,
              table_name: str,
              attempts: int = 1,
              result=None
              ):
    """Загружает параметры запроса с ответом в БД"""

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

    return add_into_table(dataset, table_name, engine, logger, attempts)


def put_query_in(engine,
                 logger,
                 json_file,
                 table_name: str,
                 task_id: str = None,
                 attempts: int = 2):
    """Загружает параметры запроса в БД"""

    if task_id is not None:
        json_file.setdefault("task_id", task_id)

    dataset = pd.DataFrame([json_file])
    dataset['date_time'] = datetime.now()

    return add_into_table(dataset, table_name, engine, logger, attempts)


def put_query_out(task_id: str,
                  table_name: str,
                  result: dict,
                  engine,
                  logger
                  ):
    """Обновляет результат запроса"""

    res_id = None
    res_warnings = None
    res_errors = None

    try:
        res_id = result["result"]["AddResults"][0].get("Id", None)
        res_warnings = result["result"]["AddResults"][0].get("Warnings", None)
        res_errors = result["result"]["AddResults"][0].get("Errors", None)
    except KeyError:
        res_errors = [result.get("error", None)]

    queries = []

    if res_id is not None:
        queries.append(f"""UPDATE {table_name} SET res_id = {int(res_id)} WHERE task_id = '{task_id}'""")

    if res_warnings is not None:
        res_warnings_ = [json.dumps(i, ensure_ascii=False).encode('utf8').decode('utf8') for i in res_warnings]
        queries.append(f"""UPDATE {table_name} SET res_warnings = ARRAY{res_warnings_} WHERE task_id = '{task_id}'""")

    if res_errors is not None:
        res_errors_ = [json.dumps(i, ensure_ascii=False).encode('utf8').decode('utf8') for i in res_errors]
        queries.append(f"""UPDATE {table_name} SET res_errors = ARRAY{res_errors_} WHERE task_id = '{task_id}'""")

    query = " ".join(queries)
    # print(query)
    return upd_into_table(query, engine, logger)


def get_clients(account_id: int, engine, logger):
    """Получает список доступных аккаунтов для клиента"""

    # query = f"""
    #          SELECT account_id AS api_id, attribute_value AS login
    #          FROM account_service_data asd
    #          WHERE attribute_id = 24 AND account_id = {account_id}
    #          """

    query = f"""
             SELECT 
             al.name as name, 
             asd.account_id AS acc_id, 
             asd.attribute_value AS ya_direct_client_id 
             FROM account_list al 
             JOIN account_service_data asd ON al.id = asd.account_id 
             WHERE status_1 = 'Active' AND al.mp_id = 16 AND asd.attribute_id = 24 AND client_id = {account_id}
             """

    return sql_query(query, engine, logger, type_='dict')


def get_objects_from_db(login: str, table_name: str, engine, logger):
    """Получает кампании клиента созданные через сервис"""

    query = f"""
             SELECT * 
             FROM {table_name} 
             WHERE res_id IS NOT NULL AND login = '{login}'
             """

    return sql_query(query, engine, logger, type_='dict')


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

    return sql_query(query, engine, logger, type_='dict')


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

    return sql_query(query, engine, logger, type_='dict')


def add_regions(engine,
                logger,
                data: list[dict],
                table_name: str,
                attempts: int = 2):
    """Записывает данные о регионах в таблицу"""

    dataset = pd.DataFrame(data)
    # dataset["ParentId"] = dataset["ParentId"].astype('int', copy=False, errors='ignore')
    # dataset.style.format({'ParentId': '{:,.0f}'.format, 'GeoRegionId': '{:,.0f}'.format})
    dataset = dataset.fillna(-1)
    dataset["ParentId"] = dataset["ParentId"].astype('int', copy=False, errors='ignore')
    # print(dataset.dtypes)

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

    return sql_query(query, engine, logger, type_=type)


def response_result(response, source: str, errors_table, warnings_table):
    """Возвращает словарь с результатом аналогичным YandexDirect подставляя описания ошибок и предупреждений из БД"""

    result = dict()

    res_id = None
    warnings = []
    errors = []

    if response.status_code != 200 or response.json().get("error", False):

        code = response.json()["error"]["error_code"]
        if source == 'db':
            details = errors_table[errors_table.error_code == int(code)]['error_text'].values[0] + ' ' + errors_table[errors_table.error_code == int(code)]['error_comment'].values[0]
        else:
            details = YandexDirectEcomru.u(response.json()["error"]["error_detail"])

        errors.append({'Code': code, 'Details': details})

    else:
        for add in response.json()["result"]["AddResults"]:
            if add.get("Errors", False):
                for error in add["Errors"]:
                    code = error["Code"]
                    if source == 'db':
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
                        if source == 'db':
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


def response_result2(response, source: str, errors_table, warnings_table):
    """Возвращает словарь с результатом аналогичным YandexDirect подставляя описания ошибок и предупреждений из БД"""

    result = dict()

    res_id = None
    warnings = []
    errors = []

    if response.get("error", False):
        code = response["error"]["error_code"]
        if source == 'db':
            details = errors_table[errors_table.error_code == int(code)]['error_text'].values[0] + ' ' + \
                      errors_table[errors_table.error_code == int(code)]['error_comment'].values[0]
        else:
            details = YandexDirectEcomru.u(response["error"]["error_detail"])

        errors.append({'Code': code, 'Details': details})

    else:
        for add in response["result"]["AddResults"]:
            if add.get("Errors", False):
                for error in add["Errors"]:
                    code = error["Code"]
                    if source == 'db':
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
                        if source == 'db':
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


def get_add_campaign_common_params(engine, logger):
    """Получить из БД поля общих параметров для всех типов кампаний"""

    query = """
            SELECT 
            param_api_name, 
            dtype, 
            enum, 
            required, 
            by_default, 
            min, 
            max, 
            description, 
            note 
            FROM ya_ads_campaign_common_params_attr 
            ORDER BY id
            """
    return sql_query(query, engine, logger, type_='dict')


def get_add_campaign_text_params(engine, logger):
    """Получить из БД поля параметров для создания текстовой кампании"""

    query = """
            SELECT 
            param_api_name, 
            dtype, 
            enum, 
            required, 
            by_default, 
            min, 
            max, 
            description, 
            note 
            FROM ya_ads_text_campaign_params_attr 
            ORDER BY id
            """

    return sql_query(query, engine, logger, type_='dict')


def get_add_campaign_dynamic_text_params(engine, logger):
    """Получить из БД поля параметров для создания динамической текстовой кампании"""

    query = """
            SELECT 
            param_api_name, 
            dtype, 
            enum, 
            required, 
            by_default, 
            min, 
            max, 
            description, 
            note 
            FROM ya_ads_dyn_text_campaign_params_attr 
            ORDER BY id
            """

    return sql_query(query, engine, logger, type_='dict')


def get_add_campaign_strategy_params(campaign_type: str, placement: str, strategy: str, engine, logger):
    """Получить из БД поля параметров стратегии для типа кампании и типа места показа (в сетях или на поиске)"""

    query = f"""
             SELECT 
             st_p.param_api_name, 
             st_p_attr.dtype, 
             st_p_attr.enum, 
             st_p.required, 
             st_p_attr.by_default, 
             st_p_attr.min, 
             st_p_attr.max, 
             st_p_attr.description, 
             st_p.note 
             FROM ya_ads_campaign_strategy_params AS st_p 
             JOIN ya_ads_campaign_strategy_params_attr AS st_p_attr ON st_p.param_api_name = st_p_attr.param_api_name 
             WHERE st_p.campaign_type = '{campaign_type}' AND st_p.placement = '{placement}' AND st_p.strategy_type = '{strategy}' 
             ORDER BY st_p.id
             """

    return sql_query(query, engine, logger, type_='dict')


def get_add_campaign_search_strategy_types(campaign_type: str, engine, logger):
    """Получить из БД стратегии показа на поиске доступные для типа кампании"""

    query = f"""
             SELECT 
             DISTINCT search_strategy, 
             description 
             FROM ya_ads_campaign_search_network csn 
             JOIN ya_ads_campaign_strategy_types st_types ON csn.search_strategy = st_types.name 
             WHERE campaign_type = '{campaign_type}'
             """

    return sql_query(query, engine, logger, type_='dict')


def get_add_campaign_network_strategy_types(campaign_type: str, search_strategy: str, engine, logger):
    """Получить из БД стратегии показа в сетях доступные для типа кампании с выбранной стратегией на поиске"""

    query = f"""
             SELECT 
             network_strategy, 
             description 
             FROM ya_ads_campaign_search_network csn 
             JOIN ya_ads_campaign_strategy_types st_types ON csn.network_strategy = st_types.name 
             WHERE campaign_type = '{campaign_type}' AND search_strategy = '{search_strategy}' 
             ORDER BY st_types.id
             """

    return sql_query(query, engine, logger, type_='dict')


def get_add_campaign_types(engine, logger):
    """Получить из БД типы кампаний доступные к созданию"""

    query = """
            SELECT 
            name, 
            description 
            FROM ya_ads_campaign_types 
            ORDER BY id
            """

    return sql_query(query, engine, logger, type_='dict')


def get_add_group_types(campaign_type: str, engine, logger):
    """Получить из БД типы групп доступные к созданию"""

    query = f"""
            SELECT 
            name, 
            description, 
            note, 
            campaign_type 
            FROM ya_ads_addgroup_types 
            WHERE campaign_type = '{campaign_type}'
            ORDER BY id
            """

    return sql_query(query, engine, logger, type_='dict')


def get_add_group_common_params(engine, logger):
    """Получить из БД поля общих параметров для всех типов групп"""

    query = f"""
             SELECT 
             param_api_name, 
             dtype, 
             enum, 
             required, 
             by_default, 
             min, 
             max, 
             description, 
             note 
             FROM ya_ads_addgroup_common_params_attr 
             ORDER BY id
             """

    return sql_query(query, engine, logger, type_='dict')


def get_add_group_text_feed_params(engine, logger):
    """Получить из БД поля для группы текстово-графических объявлений (параметры фида)"""

    query = """
            SELECT 
            param_api_name, 
            dtype, 
            enum, 
            required, 
            by_default, 
            min, 
            max, 
            description, 
            note 
            FROM ya_ads_addgroup_text_feed_params_attr 
            ORDER BY id
            """
    return sql_query(query, engine, logger, type_='dict')


def get_add_group_dynamic_text_params(engine, logger):
    """Получить из БД поля параметров группы динамический объявлений"""

    query = """
            SELECT 
            param_api_name, 
            dtype, 
            enum, 
            required, 
            by_default, 
            min, 
            max, 
            description, 
            note 
            FROM ya_ads_addgroup_dynamic_text_params_attr 
            ORDER BY id
            """

    return sql_query(query, engine, logger, type_='dict')


def get_add_group_dynamic_text_feed_params(engine, logger):
    """Получить из БД поля параметров группы динамический объявлений с подтипом FEED"""

    query = """
            SELECT 
            param_api_name, 
            dtype, 
            enum, 
            required, 
            by_default, 
            min, 
            max, 
            description, 
            note 
            FROM ya_ads_addgroup_dynamic_text_feed_params_attr 
            ORDER BY id
            """

    return sql_query(query, engine, logger, type_='dict')


def get_add_ad_types(adgroup_type: str, engine, logger):
    """Получить из БД типы объявлений доступные к созданию"""

    query = f"""
             SELECT 
             adtypes.name, 
             adtypes.description, 
             adtypes.note 
             FROM ya_ads_addad_groups_ads_types gr_ads 
             JOIN ya_ads_addad_ad_types AS adtypes ON gr_ads.ad_type = adtypes.name 
             WHERE adgroup_type = '{adgroup_type}' 
             ORDER BY adtypes.id
             """

    return sql_query(query, engine, logger, type_='dict')


def get_add_ad_text_ad_params(engine, logger):
    """Получить из БД параметры полей для создания текстово-графического объявления"""

    query = """
            SELECT 
            param_api_name, 
            dtype, 
            enum, 
            required, 
            by_default, 
            min, 
            max, 
            description, 
            note 
            FROM ya_ads_addad_text_ad_params_attr 
            ORDER BY id
            """

    return sql_query(query, engine, logger, type_='dict')


def get_add_ad_dynamic_text_ad_params(engine, logger):
    """Получить из БД параметры полей для создания динамического объявления"""

    query = """
            SELECT 
            param_api_name, 
            dtype, 
            enum, 
            required, 
            by_default, 
            min, 
            max, 
            description, 
            note 
            FROM ya_ads_addad_dynamic_text_ad_params_attr 
            ORDER BY id
            """

    return sql_query(query, engine, logger, type_='dict')



























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
