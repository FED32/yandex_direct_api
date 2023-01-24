import pandas as pd
import numpy as np


def get_token_from_db(client_login: str, engine, logger):
    """"Получает токен из БД по логину"""

    query = f"""
            SELECT 
            al.id, asd.attribute_value client_login, asd2.attribute_value client_token 
            FROM account_service_data asd 
            JOIN account_list al ON asd.account_id = al.id 
            JOIN (SELECT al.mp_id, asd.account_id, asd.attribute_id, asd.attribute_value 
            FROM account_service_data asd JOIN account_list al ON asd.account_id = al.id 
            WHERE al.mp_id = 16) asd2 ON asd2.mp_id = al.mp_id AND asd2.account_id= asd.account_id AND asd2.attribute_id <> asd.attribute_id 
            WHERE al.mp_id = 16 AND asd.attribute_id = 24 AND al.status_1 = 'Active' and asd.attribute_value = '{client_login}' 
            GROUP BY asd.attribute_id, asd.attribute_value, asd2.attribute_id, asd2.attribute_value, al.id 
            """

    try:

        data = pd.read_sql(query, con=engine)

        if data is None:
            logger.error("accounts database error")
            return ''
        elif data.shape[0] == 0:
            logger.error("non-existent account")
            return ''
        else:
            return data['client_token'][0]

    except:
        print('Нет подключения к БД')
        return ''




