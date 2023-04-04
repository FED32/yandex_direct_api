from flask import Flask, jsonify, request
from flask import Response
from werkzeug.exceptions import BadRequestKeyError
from flasgger import Swagger, swag_from
from config import Configuration, errors_warnings_sourse, DB_PARAMS
import logger_api, logger_celery
from ecom_yandex_direct import YandexDirectEcomru
from ecom_yandex_market import YandexMarketEcomru
import os
import time
import pandas as pd
from get_token_from_db import get_token_from_db
from db_work import put_query, get_clients, get_objects_from_db, get_groups_from_db, get_ads_from_db, add_regions, \
    get_table_from_db, response_result
import db_work
from sqlalchemy import create_engine
import requests
from fake_useragent import UserAgent
from celery import Celery

engine = create_engine(DB_PARAMS)

if errors_warnings_sourse == 'db':
    errors_table = get_table_from_db('ya_ads_errors', engine, logger=logger_api, type='df')
    warnings_table = get_table_from_db('ya_ads_warnings', engine, logger=logger_api, type='df')
else:
    errors_table = None
    warnings_table = None

app = Flask(__name__)
app.config.from_object(Configuration)
app.config['SWAGGER'] = {"title": "GTCOM-YandexDirectApi", "uiversion": 3}
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'
# app.config['CELERY_RESULT_BACKEND'] = f"""db+postgresql://{USER}:{PASSWORD}@{HOST}:{PORT}/{DB_NAME}"""
# app.config['CELERY_BROKER_URL'] = 'amqp://localhost'
# app.config['CELERY_RESULT_BACKEND'] = 'rpc://localhost'
# result_backend = f"""db+postgresql://{USER}:{PASSWORD}@{HOST}:{PORT}/{DB_NAME}"""

celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'], backend=app.config['CELERY_RESULT_BACKEND'])
# celery.conf.update(app.config)

logger = logger_api.init_logger()

swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec_1",
            "route": "/apispec_1.json()",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/swagger/",
}

swagger = Swagger(app, config=swagger_config)

client_id = os.environ.get("YA_CLIENT_ID", None)


class HttpError(Exception):
    def __init__(self, status_code, message):
        self.status_code = status_code
        self.message = message


def to_boolean(x):
    if x == "true":
        return True
    elif x == "false":
        return False
    else:
        return None


@app.after_request
def apply_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "content-type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST"
    return response


@app.route('/yandexdirect/authlink', methods=['GET'])
@swag_from("swagger_conf/authlink.yml")
def gen_auth_link():
    """Возвращает ссылку на страницу авторизации"""

    try:
        direct = YandexDirectEcomru()
        direct.client_id = client_id
        return jsonify({'link': direct.get_auth_link(type_='token')})

    except BadRequestKeyError:
        logger.error("authlink: BadRequest")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'authlink: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getuserinfo', methods=['POST'])
@swag_from("swagger_conf/get_user_info.yml")
def get_user_info():
    """Возвращает данные пользователя по токену"""

    try:
        json_file = request.get_json(force=False)
        token = json_file["token"]

        direct = YandexDirectEcomru()
        result = direct.get_user_info(token=token)

        if result.status_code == 200:
            logger.info(f"get user info: {result.status_code}")
            return jsonify(result.json())
        else:
            logger.error("get user info: incorrect input data or yandex direct error")
            return jsonify({'error': 'incorrect input data or yandex direct error'})

    except BadRequestKeyError:
        logger.error("get user info: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("get user info: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'get user info: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getcampaigns', methods=['POST'])
@swag_from("swagger_conf/get_campaigns.yml")
def get_campaigns():
    """Метод для вывода списка кампаний"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        # token = json_file["token"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)
        direct = YandexDirectEcomru(login, token)
        text_params = to_boolean(json_file.get("text_params", "false"))
        dynamic_text_params = to_boolean(json_file.get("dynamic_text_params", "false"))
        campaigns = direct.get_campaigns(text_params=text_params, dynamic_text_params=dynamic_text_params)

        if campaigns is not None:
            logger.info("get campaigns: OK")
            return jsonify(campaigns.json())
        else:
            logger.error("get campaigns: yandex direct api error")
            return jsonify({'error': 'yandex direct api error'})

    except BadRequestKeyError:
        logger.error("get campaigns: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("get campaigns: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'get campaigns: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getgroups', methods=['POST'])
@swag_from("swagger_conf/get_groups.yml")
def get_groups():
    """Метод для вывода списка групп"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)
        direct = YandexDirectEcomru(login, token)
        campaigns = json_file["campaigns"]
        text_feed_params = to_boolean(json_file.get("text_feed_params", "false"))
        dynamic_text_params = to_boolean(json_file.get("dynamic_text_params", "false"))
        dynamic_text_feed_params = to_boolean(json_file.get("dynamic_text_feed_params", "false"))

        groups = direct.get_groups(campaigns=campaigns, text_feed_params=text_feed_params,
                                   dynamic_text_params=dynamic_text_params,
                                   dynamic_text_feed_params=dynamic_text_feed_params)

        if groups is not None:
            logger.info("get groups: OK")
            return jsonify(groups.json())
        else:
            logger.error("get groups: yandex direct api error")
            return jsonify({'error': 'yandex direct api error'})

    except BadRequestKeyError:
        logger.error("get groups: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("get groups: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'get groups: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getads', methods=['POST'])
@swag_from("swagger_conf/get_ads.yml")
def get_ads():
    """Метод для вывода списка объявлений"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)
        direct = YandexDirectEcomru(login, token)

        ids = json_file.get("ids", None)
        groups = json_file.get("groups", None)
        campaigns = json_file.get("campaigns", None)
        text_params = to_boolean(json_file.get("text_params", "false"))
        dynamic_text_params = to_boolean(json_file.get("dynamic_text_params", "false"))

        result = direct.get_ads(ids=ids, groups=groups, campaigns=campaigns, text_params=text_params,
                                dynamic_text_params=dynamic_text_params)

        if result is None:
            logger.error("get ads: incorrect params or yandex direct error")
            return jsonify({'error': 'incorrect params or yandex direct error'})
        else:
            logger.info(f"get ads: {result.status_code}")
            return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("get ads: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("get ads: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'get ads: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/addtextcampaign', methods=['POST'])
@swag_from("swagger_conf/add_text_campaign.yml")
def add_text_campaign():
    """Метод для создания текстовой кампании"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)
        direct = YandexDirectEcomru(login, token)

        s_bid_strat = json_file["s_bid_strat"]
        n_bid_strat = json_file["n_bid_strat"]
        s_weekly_spend_limit = json_file.get("s_weekly_spend_limit", None)
        s_bid_ceiling = json_file.get("s_bid_ceiling", None)
        s_goal_id = json_file.get("s_goal_id", None)
        s_average_cpc = json_file.get("s_average_cpc", None)
        s_average_cpa = json_file.get("s_average_cpa", None)
        s_reserve_return = json_file.get("s_reserve_return")
        s_roi_coef = json_file.get("s_roi_coef", None)
        s_profitability = json_file.get("s_profitability", None)
        s_crr = json_file.get("s_crr", None)
        s_cpa = json_file.get("s_cpa", None)
        n_limit_percent = json_file.get("n_limit_percent", None)
        n_weekly_spend_limit = json_file.get("n_weekly_spend_limit", None)
        n_bid_ceiling = json_file.get("n_bid_ceiling", None)
        n_goal_id = json_file.get("n_goal_id", None)
        n_average_cpc = json_file.get("n_average_cpc", None)
        n_average_cpa = json_file.get("n_average_cpa", None)
        n_reserve_return = json_file.get("n_reserve_return", None)
        n_roi_coef = json_file.get("n_roi_coef", None)
        n_profitability = json_file.get("n_profitability", None)
        n_crr = json_file.get("n_crr", None)
        n_cpa = json_file.get("n_cpa", None)
        add_metrica_tag = json_file.get("add_metrica_tag", "YES")
        add_openstat_tag = json_file.get("add_openstat_tag", "NO")
        add_to_favorites = json_file.get("add_to_favorites", "NO")
        enable_area_of_interest_targeting = json_file.get("enable_area_of_interest_targeting", "YES")
        enable_company_info = json_file.get("enable_company_info", "YES")
        enable_site_monitoring = json_file.get("enable_site_monitoring", "NO")
        exclude_paused_competing_ads = json_file.get("exclude_paused_competing_ads", "NO")
        # maintain_network_cpc = json_file.get("maintain_network_cpc", "NO") больше не поддерживается
        require_servicing = json_file.get("require_servicing", "NO")
        campaign_exact_phrase_matching_enabled = json_file.get("campaign_exact_phrase_matching_enabled", "NO")
        counter_ids = json_file.get("counter_ids", None)
        goal_ids = json_file.get("goal_ids", None)
        goal_vals = json_file.get("goal_vals", None)
        goal_is_metrika_source_of_value = json_file.get("goal_is_metrika_source_of_value", None)
        attribution_model = json_file.get("attribution_model", "LYDC")
        tracking_params = json_file.get("tracking_params", None)

        txt_camp_params = direct.create_text_camp_params(s_bid_strat=s_bid_strat,
                                                         n_bid_strat=n_bid_strat,
                                                         s_weekly_spend_limit=s_weekly_spend_limit,
                                                         s_bid_ceiling=s_bid_ceiling,
                                                         s_goal_id=s_goal_id,
                                                         s_average_cpc=s_average_cpc,
                                                         s_average_cpa=s_average_cpa,
                                                         s_reserve_return=s_reserve_return,
                                                         s_roi_coef=s_roi_coef,
                                                         s_profitability=s_profitability,
                                                         s_crr=s_crr,
                                                         s_cpa=s_cpa,
                                                         n_limit_percent=n_limit_percent,
                                                         n_weekly_spend_limit=n_weekly_spend_limit,
                                                         n_bid_ceiling=n_bid_ceiling,
                                                         n_goal_id=n_goal_id,
                                                         n_average_cpc=n_average_cpc,
                                                         n_average_cpa=n_average_cpa,
                                                         n_reserve_return=n_reserve_return,
                                                         n_roi_coef=n_roi_coef,
                                                         n_profitability=n_profitability,
                                                         n_crr=n_crr,
                                                         n_cpa=n_cpa,
                                                         add_metrica_tag=add_metrica_tag,
                                                         add_openstat_tag=add_openstat_tag,
                                                         add_to_favorites=add_to_favorites,
                                                         enable_area_of_interest_targeting=enable_area_of_interest_targeting,
                                                         enable_company_info=enable_company_info,
                                                         enable_site_monitoring=enable_site_monitoring,
                                                         exclude_paused_competing_ads=exclude_paused_competing_ads,
                                                         # maintain_network_cpc=maintain_network_cpc,
                                                         require_servicing=require_servicing,
                                                         campaign_exact_phrase_matching_enabled=campaign_exact_phrase_matching_enabled,
                                                         counter_ids=counter_ids,
                                                         goal_ids=goal_ids,
                                                         goal_vals=goal_vals,
                                                         goal_is_metrika_source_of_value=goal_is_metrika_source_of_value,
                                                         tracking_params=tracking_params,
                                                         attribution_model=attribution_model)

        if txt_camp_params is None:
            logger.error("add text campaign: txt_camp_params incorrect")
            return jsonify({'error': 'txt_camp_params incorrect'})
        else:
            name = json_file["name"]
            start_date = json_file["start_date"]
            end_date = json_file.get("end_date", None)
            client_info = json_file.get("client_info", None)
            sms_events = json_file.get("sms_events", None)
            sms_time_from = json_file.get("sms_time_from", "9:00")
            sms_time_to = json_file.get("sms_time_to", "21:00")
            email = json_file.get("email", None)
            email_ch_pos_interval = json_file.get("email_ch_pos_interval", 60)
            email_warning_bal = json_file.get("email_warning_bal", 20)
            email_send_acc_news = json_file.get("email_send_acc_news", "NO")
            email_send_warnings = json_file.get("email_send_warnings", "NO")
            timezone = json_file.get("timezone", "Europe/Moscow")
            daily_budget_amount = json_file.get("daily_budget_amount", None)
            daily_budget_mode = json_file.get("daily_budget_mode", None)
            negative_keywords = json_file.get("negative_keywords", None)
            blocked_ips = json_file.get("blocked_ips", None)
            excluded_sites = json_file.get("excluded_sites", None)
            time_targeting_shedule = json_file.get("time_targeting_shedule", None)
            time_targeting_cons_working_weekends = json_file.get("time_targeting_cons_working_weekends", None)
            time_targeting_suspend_on_holidays = json_file.get("time_targeting_suspend_on_holidays", None)
            time_targeting_bid_percent = json_file.get("time_targeting_bid_percent", None)
            time_targeting_start_hour = json_file.get("time_targeting_start_hour", None)
            time_targeting_end_hour = json_file.get("time_targeting_end_hour", None)

            camp_params = direct.create_campaign(name=name,
                                                 start_date=start_date,
                                                 end_date=end_date,
                                                 client_info=client_info,
                                                 sms_events=sms_events,
                                                 sms_time_from=sms_time_from,
                                                 sms_time_to=sms_time_to,
                                                 email=email,
                                                 email_ch_pos_interval=email_ch_pos_interval,
                                                 email_warning_bal=email_warning_bal,
                                                 email_send_acc_news=email_send_acc_news,
                                                 email_send_warnings=email_send_warnings,
                                                 timezone=timezone,
                                                 daily_budget_amount=daily_budget_amount,
                                                 daily_budget_mode=daily_budget_mode,
                                                 negative_keywords=negative_keywords,
                                                 blocked_ips=blocked_ips,
                                                 excluded_sites=excluded_sites,
                                                 text_campaign_params=txt_camp_params['TextCampaign'],
                                                 mobile_app_campaign_params=None,
                                                 dynamic_text_campaign_params=None,
                                                 cpm_banner_campaign_params=None,
                                                 smart_campaign_params=None,
                                                 time_targeting_shedule=time_targeting_shedule,
                                                 time_targeting_cons_working_weekends=time_targeting_cons_working_weekends,
                                                 time_targeting_suspend_on_holidays=time_targeting_suspend_on_holidays,
                                                 time_targeting_bid_percent=time_targeting_bid_percent,
                                                 time_targeting_start_hour=time_targeting_start_hour,
                                                 time_targeting_end_hour=time_targeting_end_hour)

            result = direct.add_camp(campaigns=[camp_params])

            if result is None:
                logger.error("add text campaign: yandex direct error")
                return jsonify({'error': 'yandex direct error'})
            else:
                logger.info(f"add text campaign: {result.status_code}")

                # put_query(json_file=json_file, table_name='ya_ads_addcampaigns', result=result.json(), engine=engine,
                #           logger=logger)
                # return jsonify(result.json())

                parsed_result = response_result(response=result, source=errors_warnings_sourse,
                                                errors_table=errors_table, warnings_table=warnings_table)

                put_query(json_file=json_file, table_name='ya_ads_addcampaigns', result=parsed_result, engine=engine,
                          logger=logger)

                return jsonify(parsed_result)

    except BadRequestKeyError:
        logger.error("add text campaign: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("add text campaign: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'add text campaign: {ex}')
        raise HttpError(400, f'{ex}')


@celery.task(bind=True)
def task_add_campaign_async(self, login, token, camp_params, json_file):
    """Запустить задачу на создание кампании"""

    engine_ = create_engine(DB_PARAMS)
    logger_ = logger_celery.init_logger()

    try:

        logger_.info(f"add campaign async: {self.request.id}")

        direct = YandexDirectEcomru(login, token)
        result = direct.add_camp(campaigns=[camp_params])

        if result is None:
            logger_.error("add campaign async: yandex direct error")
            return {'error': 'yandex direct error'}
        else:
            logger_.info(f"add campaign async: {result.status_code}")
            parsed_result = db_work.response_result2(response=result.json(), source=errors_warnings_sourse,
                                                     errors_table=errors_table, warnings_table=warnings_table)

            json_file["task_id"] = str(self.request.id)

            put_query(json_file=json_file, table_name='ya_ads_addcampaigns', result=parsed_result, engine=engine_,
                      logger=logger_)

            return parsed_result

    except BaseException as ex:
        logger_.error(f'add campaign async: {ex}')
        return None


@app.route('/yandexdirect/addtextcampaignasync', methods=['POST'])
@swag_from("swagger_conf/add_text_campaign.yml")
def add_text_campaign_async():
    """Метод для создания текстовой кампании"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)
        s_bid_strat = json_file["s_bid_strat"]
        n_bid_strat = json_file["n_bid_strat"]
        s_weekly_spend_limit = json_file.get("s_weekly_spend_limit", None)
        s_bid_ceiling = json_file.get("s_bid_ceiling", None)
        s_goal_id = json_file.get("s_goal_id", None)
        s_average_cpc = json_file.get("s_average_cpc", None)
        s_average_cpa = json_file.get("s_average_cpa", None)
        s_reserve_return = json_file.get("s_reserve_return")
        s_roi_coef = json_file.get("s_roi_coef", None)
        s_profitability = json_file.get("s_profitability", None)
        s_crr = json_file.get("s_crr", None)
        s_cpa = json_file.get("s_cpa", None)
        n_limit_percent = json_file.get("n_limit_percent", None)
        n_weekly_spend_limit = json_file.get("n_weekly_spend_limit", None)
        n_bid_ceiling = json_file.get("n_bid_ceiling", None)
        n_goal_id = json_file.get("n_goal_id", None)
        n_average_cpc = json_file.get("n_average_cpc", None)
        n_average_cpa = json_file.get("n_average_cpa", None)
        n_reserve_return = json_file.get("n_reserve_return", None)
        n_roi_coef = json_file.get("n_roi_coef", None)
        n_profitability = json_file.get("n_profitability", None)
        n_crr = json_file.get("n_crr", None)
        n_cpa = json_file.get("n_cpa", None)
        add_metrica_tag = json_file.get("add_metrica_tag", "YES")
        add_openstat_tag = json_file.get("add_openstat_tag", "NO")
        add_to_favorites = json_file.get("add_to_favorites", "NO")
        enable_area_of_interest_targeting = json_file.get("enable_area_of_interest_targeting", "YES")
        enable_company_info = json_file.get("enable_company_info", "YES")
        enable_site_monitoring = json_file.get("enable_site_monitoring", "NO")
        exclude_paused_competing_ads = json_file.get("exclude_paused_competing_ads", "NO")
        # maintain_network_cpc = json_file.get("maintain_network_cpc", "NO") больше не поддерживается
        require_servicing = json_file.get("require_servicing", "NO")
        campaign_exact_phrase_matching_enabled = json_file.get("campaign_exact_phrase_matching_enabled", "NO")
        counter_ids = json_file.get("counter_ids", None)
        goal_ids = json_file.get("goal_ids", None)
        goal_vals = json_file.get("goal_vals", None)
        goal_is_metrika_source_of_value = json_file.get("goal_is_metrika_source_of_value", None)
        attribution_model = json_file.get("attribution_model", "LYDC")
        tracking_params = json_file.get("tracking_params", None)

        txt_camp_params = YandexDirectEcomru.create_text_camp_params(s_bid_strat=s_bid_strat,
                                                                     n_bid_strat=n_bid_strat,
                                                                     s_weekly_spend_limit=s_weekly_spend_limit,
                                                                     s_bid_ceiling=s_bid_ceiling,
                                                                     s_goal_id=s_goal_id,
                                                                     s_average_cpc=s_average_cpc,
                                                                     s_average_cpa=s_average_cpa,
                                                                     s_reserve_return=s_reserve_return,
                                                                     s_roi_coef=s_roi_coef,
                                                                     s_profitability=s_profitability,
                                                                     s_crr=s_crr,
                                                                     s_cpa=s_cpa,
                                                                     n_limit_percent=n_limit_percent,
                                                                     n_weekly_spend_limit=n_weekly_spend_limit,
                                                                     n_bid_ceiling=n_bid_ceiling,
                                                                     n_goal_id=n_goal_id,
                                                                     n_average_cpc=n_average_cpc,
                                                                     n_average_cpa=n_average_cpa,
                                                                     n_reserve_return=n_reserve_return,
                                                                     n_roi_coef=n_roi_coef,
                                                                     n_profitability=n_profitability,
                                                                     n_crr=n_crr,
                                                                     n_cpa=n_cpa,
                                                                     add_metrica_tag=add_metrica_tag,
                                                                     add_openstat_tag=add_openstat_tag,
                                                                     add_to_favorites=add_to_favorites,
                                                                     enable_area_of_interest_targeting=enable_area_of_interest_targeting,
                                                                     enable_company_info=enable_company_info,
                                                                     enable_site_monitoring=enable_site_monitoring,
                                                                     exclude_paused_competing_ads=exclude_paused_competing_ads,
                                                                     # maintain_network_cpc=maintain_network_cpc,
                                                                     require_servicing=require_servicing,
                                                                     campaign_exact_phrase_matching_enabled=campaign_exact_phrase_matching_enabled,
                                                                     counter_ids=counter_ids,
                                                                     goal_ids=goal_ids,
                                                                     goal_vals=goal_vals,
                                                                     goal_is_metrika_source_of_value=goal_is_metrika_source_of_value,
                                                                     tracking_params=tracking_params,
                                                                     attribution_model=attribution_model)

        if txt_camp_params is None:
            logger.error("add text campaign: txt_camp_params incorrect")
            return jsonify({'error': 'txt_camp_params incorrect'})
        else:
            name = json_file["name"]
            start_date = json_file["start_date"]
            end_date = json_file.get("end_date", None)
            client_info = json_file.get("client_info", None)
            sms_events = json_file.get("sms_events", None)
            sms_time_from = json_file.get("sms_time_from", "9:00")
            sms_time_to = json_file.get("sms_time_to", "21:00")
            email = json_file.get("email", None)
            email_ch_pos_interval = json_file.get("email_ch_pos_interval", 60)
            email_warning_bal = json_file.get("email_warning_bal", 20)
            email_send_acc_news = json_file.get("email_send_acc_news", "NO")
            email_send_warnings = json_file.get("email_send_warnings", "NO")
            timezone = json_file.get("timezone", "Europe/Moscow")
            daily_budget_amount = json_file.get("daily_budget_amount", None)
            daily_budget_mode = json_file.get("daily_budget_mode", None)
            negative_keywords = json_file.get("negative_keywords", None)
            blocked_ips = json_file.get("blocked_ips", None)
            excluded_sites = json_file.get("excluded_sites", None)
            time_targeting_shedule = json_file.get("time_targeting_shedule", None)
            time_targeting_cons_working_weekends = json_file.get("time_targeting_cons_working_weekends", None)
            time_targeting_suspend_on_holidays = json_file.get("time_targeting_suspend_on_holidays", None)
            time_targeting_bid_percent = json_file.get("time_targeting_bid_percent", None)
            time_targeting_start_hour = json_file.get("time_targeting_start_hour", None)
            time_targeting_end_hour = json_file.get("time_targeting_end_hour", None)

            camp_params = YandexDirectEcomru.create_campaign(name=name,
                                                             start_date=start_date,
                                                             end_date=end_date,
                                                             client_info=client_info,
                                                             sms_events=sms_events,
                                                             sms_time_from=sms_time_from,
                                                             sms_time_to=sms_time_to,
                                                             email=email,
                                                             email_ch_pos_interval=email_ch_pos_interval,
                                                             email_warning_bal=email_warning_bal,
                                                             email_send_acc_news=email_send_acc_news,
                                                             email_send_warnings=email_send_warnings,
                                                             timezone=timezone,
                                                             daily_budget_amount=daily_budget_amount,
                                                             daily_budget_mode=daily_budget_mode,
                                                             negative_keywords=negative_keywords,
                                                             blocked_ips=blocked_ips,
                                                             excluded_sites=excluded_sites,
                                                             text_campaign_params=txt_camp_params['TextCampaign'],
                                                             mobile_app_campaign_params=None,
                                                             dynamic_text_campaign_params=None,
                                                             cpm_banner_campaign_params=None,
                                                             smart_campaign_params=None,
                                                             time_targeting_shedule=time_targeting_shedule,
                                                             time_targeting_cons_working_weekends=time_targeting_cons_working_weekends,
                                                             time_targeting_suspend_on_holidays=time_targeting_suspend_on_holidays,
                                                             time_targeting_bid_percent=time_targeting_bid_percent,
                                                             time_targeting_start_hour=time_targeting_start_hour,
                                                             time_targeting_end_hour=time_targeting_end_hour)

            task = task_add_campaign_async.delay(login, token, camp_params, json_file)

            return jsonify({'result': task.id})

    except BadRequestKeyError:
        logger.error("add text campaign async: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("add text campaign async: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'add text campaign async: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/addcampaignasync/<task_id>', methods=['GET'])
@swag_from("swagger_conf/add_campaign_async_result.yml")
def add_campaign_async_result(task_id):
    """Возвращает результат по id асинхронной задачи"""

    try:
        task = task_add_campaign_async.AsyncResult(str(task_id))

        if task is not None:

            if task.state == 'SUCCESS':

                result = task.get(timeout=5)

                result["state"] = task.state
                return jsonify(result)

            else:
                result = {'state': task.state}
                return jsonify(result)
        else:
            return Response(None, 400)

    except BadRequestKeyError:
        logger.error("add campaign async result: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("add campaign async result: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'add campaign async result: {ex}')
        raise HttpError(400, f'{ex}')


# @app.route('/yandexdirect/updatetextcampaign', methods=['POST'])
# @swag_from("swagger_conf/update_text_campaign.yml")
# def update_text_campaign():
#     """Метод для обновления параметров текстовой кампании"""
#
#     try:
#         json_file = request.get_json(force=False)
#         login = json_file["login"]
#         token = json_file["token"]
#
#         direct = YandexDirectEcomru(login, token)
#
#         s_bid_strat = json_file.get("s_bid_strat", None)
#         n_bid_strat = json_file.get("n_bid_strat", None)
#
#         s_weekly_spend_limit = json_file.get("s_weekly_spend_limit", None)
#         s_bid_ceiling = json_file.get("s_bid_ceiling", None)
#         s_goal_id = json_file.get("s_goal_id", None)
#         s_average_cpc = json_file.get("s_average_cpc", None)
#         s_average_cpa = json_file.get("s_average_cpa", None)
#         s_reserve_return = json_file.get("s_reserve_return")
#         s_roi_coef = json_file.get("s_roi_coef", None)
#         s_profitability = json_file.get("s_profitability", None)
#         s_crr = json_file.get("s_crr", None)
#         s_cpa = json_file.get("s_cpa", None)
#
#         n_limit_percent = json_file.get("n_limit_percent", None)
#         n_weekly_spend_limit = json_file.get("n_weekly_spend_limit", None)
#         n_bid_ceiling = json_file.get("n_bid_ceiling", None)
#         n_goal_id = json_file.get("n_goal_id", None)
#         n_average_cpc = json_file.get("n_average_cpc", None)
#         n_average_cpa = json_file.get("n_average_cpa", None)
#         n_reserve_return = json_file.get("n_reserve_return", None)
#         n_roi_coef = json_file.get("n_roi_coef", None)
#         n_profitability = json_file.get("n_profitability", None)
#         n_crr = json_file.get("n_crr", None)
#         n_cpa = json_file.get("n_cpa", None)
#
#         add_metrica_tag = json_file.get("add_metrica_tag", "YES")
#         add_openstat_tag = json_file.get("add_openstat_tag", "NO")
#         add_to_favorites = json_file.get("add_to_favorites", "NO")
#         enable_area_of_interest_targeting = json_file.get("enable_area_of_interest_targeting", "YES")
#         enable_company_info = json_file.get("enable_company_info", "YES")
#         enable_site_monitoring = json_file.get("enable_site_monitoring", "NO")
#         exclude_paused_competing_ads = json_file.get("exclude_paused_competing_ads", "NO")
#         maintain_network_cpc = json_file.get("maintain_network_cpc", "NO")
#         require_servicing = json_file.get("require_servicing", "NO")
#
#         counter_ids = json_file.get("counter_ids", None)
#
#         goal_ids = json_file.get("goal_ids", None)
#         goal_vals = json_file.get("goal_vals", None)
#
#         attr_model = json_file.get("attr_model", "LYDC")
#
#         txt_camp_params = direct.create_text_camp_params(s_bid_strat=s_bid_strat,
#                                                          n_bid_strat=n_bid_strat,
#                                                          s_weekly_spend_limit=s_weekly_spend_limit,
#                                                          s_bid_ceiling=s_bid_ceiling,
#                                                          s_goal_id=s_goal_id,
#                                                          s_average_cpc=s_average_cpc,
#                                                          s_average_cpa=s_average_cpa,
#                                                          s_reserve_return=s_reserve_return,
#                                                          s_roi_coef=s_roi_coef,
#                                                          s_profitability=s_profitability,
#                                                          s_crr=s_crr,
#                                                          s_cpa=s_cpa,
#                                                          n_limit_percent=n_limit_percent,
#                                                          n_weekly_spend_limit=n_weekly_spend_limit,
#                                                          n_bid_ceiling=n_bid_ceiling,
#                                                          n_goal_id=n_goal_id,
#                                                          n_average_cpc=n_average_cpc,
#                                                          n_average_cpa=n_average_cpa,
#                                                          n_reserve_return=n_reserve_return,
#                                                          n_roi_coef=n_roi_coef,
#                                                          n_profitability=n_profitability,
#                                                          n_crr=n_crr,
#                                                          n_cpa=n_cpa,
#                                                          add_metrica_tag=add_metrica_tag,
#                                                          add_openstat_tag=add_openstat_tag,
#                                                          add_to_favorites=add_to_favorites,
#                                                          enable_area_of_interest_targeting=enable_area_of_interest_targeting,
#                                                          enable_company_info=enable_company_info,
#                                                          enable_site_monitoring=enable_site_monitoring,
#                                                          exclude_paused_competing_ads=exclude_paused_competing_ads,
#                                                          maintain_network_cpc=maintain_network_cpc,
#                                                          require_servicing=require_servicing,
#                                                          counter_ids=counter_ids,
#                                                          goal_ids=goal_ids,
#                                                          goal_vals=goal_vals,
#                                                          attr_model=attr_model,
#                                                          update=True)
#
#         if txt_camp_params is None:
#             logger.error("update text campaign: txt_camp_params incorrect")
#             return jsonify({'error': 'txt_camp_params incorrect'})
#         else:
#             camp_id = json_file["camp_id"]
#             name = json_file.get("name", None)
#             start_date = json_file.get("start_date", None)
#             end_date = json_file.get("end_date", None)
#             client_info = json_file.get("client_info", None)
#             sms_events = json_file.get("sms_events", None)
#             sms_time_from = json_file.get("sms_time_from", "9:00")
#             sms_time_to = json_file.get("sms_time_to", "21:00")
#             email = json_file.get("email", None)
#             email_ch_pos_interval = json_file.get("email_ch_pos_interval", 60)
#             email_warning_bal = json_file.get("email_warning_bal", 20)
#             email_send_acc_news = json_file.get("email_send_acc_news", "NO")
#             email_send_warnings = json_file.get("email_send_warnings", "NO")
#             timezone = json_file.get("timezone", "Europe/Moscow")
#             daily_budget_amount = json_file.get("daily_budget_amount", None)
#             daily_budget_mode = json_file.get("daily_budget_mode", None)
#             negative_keywords = json_file.get("negative_keywords", None)
#             blocked_ips = json_file.get("blocked_ips", None)
#             excluded_sites = json_file.get("excluded_sites", None)
#             time_targeting_shedule = json_file.get("time_targeting_shedule", None)
#             time_targeting_cons_working_weekends = json_file.get("time_targeting_cons_working_weekends", None)
#             time_targeting_suspend_on_holidays = json_file.get("time_targeting_suspend_on_holidays", None)
#             time_targeting_bid_percent = json_file.get("time_targeting_bid_percent", None)
#             time_targeting_start_hour = json_file.get("time_targeting_start_hour", None)
#             time_targeting_end_hour = json_file.get("time_targeting_end_hour", None)


@app.route('/yandexdirect/addgroup', methods=['POST'])
@swag_from("swagger_conf/add_group.yml")
def add_group():
    """Метод для создания группы"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        # token = json_file["token"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        name = json_file["name"]
        campaign_id = json_file["campaign_id"]
        region_ids = json_file["region_ids"]
        negative_keywords = json_file.get("negative_keywords", None)
        negative_keyword_set_ids = json_file.get(" negative_keyword_set_ids", None)
        tracking_params = json_file.get("tracking_params", None)
        text_feed_id = json_file.get("text_feed_id", None)
        text_feed_category_ids = json_file.get("text_feed_category_ids", None)
        dynamic_text_domain_urls = json_file.get("dynamic_text_domain_urls", None)
        dynamic_text_autotargeting_exact = json_file.get("dynamic_text_autotargeting_exact", None)
        dynamic_text_autotargeting_alternative = json_file.get("dynamic_text_autotargeting_alternative", None)
        dynamic_text_autotargeting_competitor = json_file.get("dynamic_text_autotargeting_competitor", None)
        dynamic_text_autotargeting_broader = json_file.get("dynamic_text_autotargeting_broader", None)
        dynamic_text_autotargeting_accessory = json_file.get("dynamic_text_autotargeting_accessory", None)
        dynamic_text_feed_ids = json_file.get("dynamic_text_feed_ids", None)
        dynamic_text_feed_autotargeting_exact = json_file.get("dynamic_text_feed_autotargeting_exact", None)
        dynamic_text_feed_autotargeting_alternative = json_file.get("dynamic_text_feed_autotargeting_alternative", None)
        dynamic_text_feed_autotargeting_competitor = json_file.get("dynamic_text_feed_autotargeting_competitor", None)
        dynamic_text_feed_autotargeting_broader = json_file.get("dynamic_text_feed_autotargeting_broader", None)
        dynamic_text_feed_autotargeting_accessory = json_file.get("dynamic_text_feed_autotargeting_accessory", None)

        group_params = direct.create_group(name=name,
                                           campaign_id=campaign_id,
                                           region_ids=region_ids,
                                           negative_keywords=negative_keywords,
                                           negative_keyword_set_ids=negative_keyword_set_ids,
                                           tracking_params=tracking_params,
                                           text_feed_id=text_feed_id,
                                           text_feed_category_ids=text_feed_category_ids,
                                           dynamic_text_domain_urls=dynamic_text_domain_urls,
                                           dynamic_text_autotargeting_exact=dynamic_text_autotargeting_exact,
                                           dynamic_text_autotargeting_alternative=dynamic_text_autotargeting_alternative,
                                           dynamic_text_autotargeting_competitor=dynamic_text_autotargeting_competitor,
                                           dynamic_text_autotargeting_broader=dynamic_text_autotargeting_broader,
                                           dynamic_text_autotargeting_accessory=dynamic_text_autotargeting_accessory,
                                           dynamic_text_feed_ids=dynamic_text_feed_ids,
                                           dynamic_text_feed_autotargeting_exact=dynamic_text_feed_autotargeting_exact,
                                           dynamic_text_feed_autotargeting_alternative=dynamic_text_feed_autotargeting_alternative,
                                           dynamic_text_feed_autotargeting_competitor=dynamic_text_feed_autotargeting_competitor,
                                           dynamic_text_feed_autotargeting_broader=dynamic_text_feed_autotargeting_broader,
                                           dynamic_text_feed_autotargeting_accessory=dynamic_text_feed_autotargeting_accessory
                                           )

        if group_params is None:
            logger.error("add group: group params incorrect")
            return jsonify({'error': 'group params incorrect'})
        else:
            result = direct.add_groups(groups=[group_params])

            if result is None:
                logger.error("add group: yandex direct error")
                return jsonify({'error': 'yandex direct error'})
            else:
                logger.info(f"add group: {result.status_code}")

                # put_query(json_file=json_file, table_name='ya_ads_addgroups', result=result.json(), engine=engine,
                #           logger=logger)
                # return jsonify(result.json())

                parsed_result = response_result(response=result, source=errors_warnings_sourse,
                                                errors_table=errors_table, warnings_table=warnings_table)

                put_query(json_file=json_file, table_name='ya_ads_addgroups', result=parsed_result, engine=engine,
                          logger=logger)

                return jsonify(parsed_result)

    except BadRequestKeyError:
        logger.error("add group: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("add group: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'add group: {ex}')
        raise HttpError(400, f'{ex}')


@celery.task(bind=True)
def task_add_group_async(self, login, token, group_params, json_file):
    """Запустить задачу на создание группы"""

    engine_ = create_engine(DB_PARAMS)
    logger_ = logger_celery.init_logger()

    try:
        logger_.info(f"add group async: {self.request.id}")

        direct = YandexDirectEcomru(login, token)
        result = direct.add_groups(groups=[group_params])

        if result is None:
            logger_.error("add group async: yandex direct error")
            return {'error': 'yandex direct error'}
        else:
            parsed_result = db_work.response_result2(response=result.json(), source=errors_warnings_sourse,
                                                     errors_table=errors_table, warnings_table=warnings_table)

            json_file["task_id"] = str(self.request.id)

            put_query(json_file=json_file, table_name='ya_ads_addgroups', result=parsed_result, engine=engine_,
                      logger=logger_)

            return parsed_result

    except BaseException as ex:
        logger_.error(f'add group async: {ex}')
        return None


@app.route('/yandexdirect/addgroupasync', methods=['POST'])
@swag_from("swagger_conf/add_group.yml")
def add_group_async():
    """Метод для создания группы"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)
        name = json_file["name"]
        campaign_id = json_file["campaign_id"]
        region_ids = json_file["region_ids"]
        negative_keywords = json_file.get("negative_keywords", None)
        negative_keyword_set_ids = json_file.get(" negative_keyword_set_ids", None)
        tracking_params = json_file.get("tracking_params", None)
        text_feed_id = json_file.get("text_feed_id", None)
        text_feed_category_ids = json_file.get("text_feed_category_ids", None)
        dynamic_text_domain_urls = json_file.get("dynamic_text_domain_urls", None)
        dynamic_text_autotargeting_exact = json_file.get("dynamic_text_autotargeting_exact", None)
        dynamic_text_autotargeting_alternative = json_file.get("dynamic_text_autotargeting_alternative", None)
        dynamic_text_autotargeting_competitor = json_file.get("dynamic_text_autotargeting_competitor", None)
        dynamic_text_autotargeting_broader = json_file.get("dynamic_text_autotargeting_broader", None)
        dynamic_text_autotargeting_accessory = json_file.get("dynamic_text_autotargeting_accessory", None)
        dynamic_text_feed_ids = json_file.get("dynamic_text_feed_ids", None)
        dynamic_text_feed_autotargeting_exact = json_file.get("dynamic_text_feed_autotargeting_exact", None)
        dynamic_text_feed_autotargeting_alternative = json_file.get("dynamic_text_feed_autotargeting_alternative", None)
        dynamic_text_feed_autotargeting_competitor = json_file.get("dynamic_text_feed_autotargeting_competitor", None)
        dynamic_text_feed_autotargeting_broader = json_file.get("dynamic_text_feed_autotargeting_broader", None)
        dynamic_text_feed_autotargeting_accessory = json_file.get("dynamic_text_feed_autotargeting_accessory", None)

        group_params = YandexDirectEcomru.create_group(name=name,
                                                       campaign_id=campaign_id,
                                                       region_ids=region_ids,
                                                       negative_keywords=negative_keywords,
                                                       negative_keyword_set_ids=negative_keyword_set_ids,
                                                       tracking_params=tracking_params,
                                                       text_feed_id=text_feed_id,
                                                       text_feed_category_ids=text_feed_category_ids,
                                                       dynamic_text_domain_urls=dynamic_text_domain_urls,
                                                       dynamic_text_autotargeting_exact=dynamic_text_autotargeting_exact,
                                                       dynamic_text_autotargeting_alternative=dynamic_text_autotargeting_alternative,
                                                       dynamic_text_autotargeting_competitor=dynamic_text_autotargeting_competitor,
                                                       dynamic_text_autotargeting_broader=dynamic_text_autotargeting_broader,
                                                       dynamic_text_autotargeting_accessory=dynamic_text_autotargeting_accessory,
                                                       dynamic_text_feed_ids=dynamic_text_feed_ids,
                                                       dynamic_text_feed_autotargeting_exact=dynamic_text_feed_autotargeting_exact,
                                                       dynamic_text_feed_autotargeting_alternative=dynamic_text_feed_autotargeting_alternative,
                                                       dynamic_text_feed_autotargeting_competitor=dynamic_text_feed_autotargeting_competitor,
                                                       dynamic_text_feed_autotargeting_broader=dynamic_text_feed_autotargeting_broader,
                                                       dynamic_text_feed_autotargeting_accessory=dynamic_text_feed_autotargeting_accessory
                                                       )

        if group_params is None:
            logger.error("add group async: group params incorrect")
            return jsonify({'error': 'group params incorrect'})
        else:
            task = task_add_group_async.delay(login, token, group_params, json_file)
            return jsonify({'result': task.id})

    except BadRequestKeyError:
        logger.error("add group async: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("add group async: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'add group async: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/addgroupasync/<task_id>', methods=['GET'])
@swag_from("swagger_conf/add_group_async_result.yml")
def add_group_async_result(task_id):
    """Возвращает результат по id асинхронной задачи"""

    try:
        task = task_add_group_async.AsyncResult(str(task_id))

        if task is not None:

            if task.state == 'SUCCESS':
                result = task.get(timeout=5)
                result["state"] = task.state
                return jsonify(result)
            else:
                result = {'state': task.state}
                return jsonify(result)
        else:
            return Response(None, 400)

    except BadRequestKeyError:
        logger.error("add group async result: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("add group async result: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'add group async result: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/addtextad', methods=['POST'])
@swag_from("swagger_conf/add_text_ad.yml")
def add_text_ad():
    """Метод для создания текстового объявления"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        # token = json_file["token"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        ads_group_id = json_file["ads_group_id"]
        title = json_file["title"]
        title2 = json_file.get("title2", None)
        text = json_file["text"]
        mobile = json_file["mobile"]
        href = json_file.get("href", None)
        turbo_page_id = json_file.get("turbo_page_id", None)
        vcard_id = json_file.get("vcard_id", None)
        business_id = json_file.get("business_id", None)
        prefer_vcard_over_business = json_file.get("prefer_vcard_over_business", None)
        ad_image_hash = json_file.get("ad_image_hash", None)
        sitelink_set_id = json_file.get("sitelink_set_id")
        display_url_path = json_file.get("display_url_path", None)
        ad_extension_ids = json_file.get("ad_extension_ids", None)
        creative_id = json_file.get("creative_id", None)
        txt_price = json_file.get("txt_price", None)
        txt_old_price = json_file.get("txt_old_price", None)
        txt_price_qualifier = json_file.get("txt_price_qualifier", None)
        txt_price_currency = json_file.get("txt_price_currency", None)
        ext_link_params = to_boolean(json_file.get("ext_link_params", "false"))

        params = direct.create_ad_params(ads_group_id=ads_group_id,
                                         title=title,
                                         title2=title2,
                                         text=text,
                                         mobile=mobile,
                                         href=href,
                                         turbo_page_id=turbo_page_id,
                                         vcard_id=vcard_id,
                                         business_id=business_id,
                                         prefer_vcard_over_business=prefer_vcard_over_business,
                                         ad_image_hash=ad_image_hash,
                                         sitelink_set_id=sitelink_set_id,
                                         display_url_path=display_url_path,
                                         ad_extension_ids=ad_extension_ids,
                                         creative_id=creative_id,
                                         txt_price=txt_price,
                                         txt_old_price=txt_old_price,
                                         txt_price_qualifier=txt_price_qualifier,
                                         txt_price_currency=txt_price_currency,
                                         ext_link_params=ext_link_params)

        if params is None:
            logger.error("add text ad: text ad params incorrect")
            return jsonify({'error': 'text ad params incorrect'})
        else:
            result = direct.add_ads(ads=[params])

            if result is None:
                logger.error("add text ad: yandex direct error")
                return jsonify({'error': 'yandex direct error'})
            else:
                logger.info(f"add text ad: {result.status_code}")

                # put_query(json_file=json_file, table_name='ya_ads_addads', result=result.json(), engine=engine,
                #           logger=logger)
                #
                # return jsonify(result.json())

                parsed_result = response_result(response=result, source=errors_warnings_sourse,
                                                errors_table=errors_table, warnings_table=warnings_table)

                put_query(json_file=json_file, table_name='ya_ads_addads', result=parsed_result, engine=engine,
                          logger=logger)

                return jsonify(parsed_result)

    except BadRequestKeyError:
        logger.error("add text ad: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("add text ad: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'add text ad: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/adddynamictextad', methods=['POST'])
@swag_from("swagger_conf/add_dynamic_text_ad.yml")
def add_dynamic_text_ad():
    """Метод для создания динамического текстового объявления"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        # token = json_file["token"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        ads_group_id = json_file["ads_group_id"]

        text = json_file["text"]
        vcard_id = json_file.get("vcard_id", None)
        ad_image_hash = json_file.get("ad_image_hash", None)
        sitelink_set_id = json_file.get("sitelink_set_id", None)
        ad_extension_ids = json_file.get("ad_extension_ids", None)

        params = direct.create_dynamic_text_ad_params(ads_group_id, text, vcard_id, ad_image_hash, sitelink_set_id,
                                                      ad_extension_ids)

        if params is None:
            logger.error("add dynamic text ad: text ad params incorrect")
            return jsonify({'error': 'dynamic text ad params incorrect'})
        else:
            result = direct.add_ads(ads=[params])

            if result is None:
                logger.error("add dynamic text ad: yandex direct error")
                return jsonify({'error': 'yandex direct error'})
            else:
                logger.info(f"add dynamic text ad: {result.status_code}")

                # put_query(json_file=json_file, table_name='ya_ads_addads', result=result.json(), engine=engine,
                #           logger=logger)
                #
                # return jsonify(result.json())

                parsed_result = response_result(response=result, source=errors_warnings_sourse,
                                                errors_table=errors_table, warnings_table=warnings_table)

                put_query(json_file=json_file, table_name='ya_ads_addads', result=parsed_result, engine=engine,
                          logger=logger)

                return jsonify(parsed_result)

    except BadRequestKeyError:
        logger.error("add dynamic text ad: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("add dynamic text ad: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'add dynamic text ad: {ex}')
        raise HttpError(400, f'{ex}')


@celery.task(bind=True)
def task_add_ad_async(self, login, token, ad_params, json_file):
    """Запустить задачу на создание объявления"""

    engine_ = create_engine(DB_PARAMS)
    logger_ = logger_celery.init_logger()

    try:
        logger_.info(f"add ad async: {self.request.id}")

        direct = YandexDirectEcomru(login, token)
        result = direct.add_ads(ads=[ad_params])

        if result is None:
            logger_.error("add ad async: yandex direct error")
            return {'error': 'yandex direct error'}
        else:
            parsed_result = db_work.response_result2(response=result.json(), source=errors_warnings_sourse,
                                                     errors_table=errors_table, warnings_table=warnings_table)

            json_file["task_id"] = str(self.request.id)

            put_query(json_file=json_file, table_name='ya_ads_addads', result=parsed_result, engine=engine_,
                      logger=logger_)

            return parsed_result

    except BaseException as ex:
        logger_.error(f'add ad async: {ex}')
        return None


@app.route('/yandexdirect/addtextadasync', methods=['POST'])
@swag_from("swagger_conf/add_text_ad.yml")
def add_text_ad_async():
    """Метод для создания текстового объявления"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)
        ads_group_id = json_file["ads_group_id"]
        title = json_file["title"]
        title2 = json_file.get("title2", None)
        text = json_file["text"]
        mobile = json_file["mobile"]
        href = json_file.get("href", None)
        turbo_page_id = json_file.get("turbo_page_id", None)
        vcard_id = json_file.get("vcard_id", None)
        business_id = json_file.get("business_id", None)
        prefer_vcard_over_business = json_file.get("prefer_vcard_over_business", None)
        ad_image_hash = json_file.get("ad_image_hash", None)
        sitelink_set_id = json_file.get("sitelink_set_id")
        display_url_path = json_file.get("display_url_path", None)
        ad_extension_ids = json_file.get("ad_extension_ids", None)
        creative_id = json_file.get("creative_id", None)
        txt_price = json_file.get("txt_price", None)
        txt_old_price = json_file.get("txt_old_price", None)
        txt_price_qualifier = json_file.get("txt_price_qualifier", None)
        txt_price_currency = json_file.get("txt_price_currency", None)
        ext_link_params = to_boolean(json_file.get("ext_link_params", "false"))

        params = YandexDirectEcomru.create_ad_params(ads_group_id=ads_group_id,
                                                     title=title,
                                                     title2=title2,
                                                     text=text,
                                                     mobile=mobile,
                                                     href=href,
                                                     turbo_page_id=turbo_page_id,
                                                     vcard_id=vcard_id,
                                                     business_id=business_id,
                                                     prefer_vcard_over_business=prefer_vcard_over_business,
                                                     ad_image_hash=ad_image_hash,
                                                     sitelink_set_id=sitelink_set_id,
                                                     display_url_path=display_url_path,
                                                     ad_extension_ids=ad_extension_ids,
                                                     creative_id=creative_id,
                                                     txt_price=txt_price,
                                                     txt_old_price=txt_old_price,
                                                     txt_price_qualifier=txt_price_qualifier,
                                                     txt_price_currency=txt_price_currency,
                                                     ext_link_params=ext_link_params)

        if params is None:
            logger.error("add text ad async: text ad params incorrect")
            return jsonify({'error': 'text ad params incorrect'})
        else:
            task = task_add_ad_async.delay(login=login, token=token, ad_params=params, json_file=json_file)
            return jsonify({'result': task.id})

    except BadRequestKeyError:
        logger.error("add text ad async: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("add text ad async: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'add text ad async: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/adddynamictextadasync', methods=['POST'])
@swag_from("swagger_conf/add_dynamic_text_ad.yml")
def add_dynamic_text_ad_async():
    """Метод для создания динамического текстового объявления"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)
        ads_group_id = json_file["ads_group_id"]
        text = json_file["text"]
        vcard_id = json_file.get("vcard_id", None)
        ad_image_hash = json_file.get("ad_image_hash", None)
        sitelink_set_id = json_file.get("sitelink_set_id", None)
        ad_extension_ids = json_file.get("ad_extension_ids", None)

        params = YandexDirectEcomru.create_dynamic_text_ad_params(ads_group_id, text, vcard_id, ad_image_hash,
                                                                  sitelink_set_id, ad_extension_ids)

        if params is None:
            logger.error("add dynamic text ad async: text ad params incorrect")
            return jsonify({'error': 'dynamic text ad params incorrect'})
        else:
            task = task_add_ad_async.delay(login=login, token=token, ad_params=params, json_file=json_file)
            return jsonify({'result': task.id})

    except BadRequestKeyError:
        logger.error("add text ad async: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("add text ad async: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'add text ad async: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/addadasync/<task_id>', methods=['GET'])
@swag_from("swagger_conf/add_ad_async_result.yml")
def add_ad_async_result(task_id):
    """Возвращает результат по id асинхронной задачи"""

    try:
        task = task_add_ad_async.AsyncResult(str(task_id))

        if task is not None:

            if task.state == 'SUCCESS':
                result = task.get(timeout=5)
                result["state"] = task.state
                return jsonify(result)
            else:
                result = {'state': task.state}
                return jsonify(result)
        else:
            return Response(None, 400)

    except BadRequestKeyError:
        logger.error("add ad async result: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("add ad async result: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'add ad async result: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/managecamps', methods=['POST'])
@swag_from("swagger_conf/manage_camps.yml")
def manage_camps():
    """
    Метод для управления кампаниями
    Удаляет, архивирует/разархивирует, останавливает/возобновляет показы кампании
    (delete, archive, unarchive, suspend, resume)
    """

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        # token = json_file["token"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        campaigns = json_file["campaigns"]

        action = json_file["action"]

        if action == "delete":
            action_ = "delete"
        elif action == "archive":
            action_ = "archive"
        elif action == "unarchive":
            action_ = "unarchive"
        elif action == "suspend":
            action_ = "suspend"
        elif action == "resume":
            action_ = "resume"
        else:
            logger.error("manage camps: incorrect action")
            return jsonify({'error': 'incorrect action'})

        result = direct.manage_camps(campaigns=campaigns, action=action_)

        if result is None:
            logger.error("manage camps: yandex direct error")
            return jsonify({'error': 'yandex direct error'})
        else:
            logger.info(f"manage camps: {result.status_code}")
            return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("manage camps: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("manage camps: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'manage camps: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/deletegroups', methods=['POST'])
@swag_from("swagger_conf/delete_groups.yml")
def delete_groups():
    """Метод для удаления групп"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        # token = json_file["token"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        groups = json_file["groups"]

        result = direct.delete_groups(groups=groups)

        if result is None:
            logger.error("delete groups: yandex direct error")
            return jsonify({'error': 'yandex direct error'})
        else:
            logger.info(f"delete groups: {result.status_code}")
            return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("delete groups: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("delete groups: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'delete groups: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/manageads', methods=['POST'])
@swag_from("swagger_conf/manage_ads.yml")
def manage_ads():
    """
    Метод для управления объявлениями
    Удаляет, архивирует/разархивирует, останавливает/возобновляет показы объявлений, отправляет на модерацию
    (delete, archive, unarchive, suspend, resume, moderate)
    """

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        # token = json_file["token"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        ids = json_file["ids"]

        action = json_file["action"]

        if action == "delete":
            action_ = "delete"
        elif action == "archive":
            action_ = "archive"
        elif action == "unarchive":
            action_ = "unarchive"
        elif action == "suspend":
            action_ = "suspend"
        elif action == "resume":
            action_ = "resume"
        elif action == "moderate":
            action_ = "moderate"
        else:
            logger.error("manage ads: incorrect action")
            return jsonify({'error': 'incorrect action'})

        result = direct.manage_ads(ids=ids, action=action_)

        if result is None:
            logger.error("manage ads: yandex direct error")
            return jsonify({'error': 'yandex direct error'})
        else:
            logger.info(f"manage ads: {result.status_code}")
            return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("manage ads: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("manage ads: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'manage ads: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getkeywords', methods=['POST'])
@swag_from("swagger_conf/get_keywords.yml")
def get_keywords():
    """Метод для получения параметров ключевых фраз или автотаргетингов"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        # token = json_file["token"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        ids = json_file.get("ids", None)
        adgroup_ids = json_file.get("adgroup_ids", None)
        campaign_ids = json_file.get("campaign_ids", None)

        result = direct.get_keywords(ids=ids, adgroup_ids=adgroup_ids, campaign_ids=campaign_ids)

        if result is None:
            logger.error("get keywords: yandex direct error")
            return jsonify({'error': 'yandex direct error'})
        else:
            logger.info(f"get keywords: {result.status_code}")
            return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("get keywords: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get keywords: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get keywords: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/addkeyword', methods=['POST'])
@swag_from("swagger_conf/add_keyword.yml")
def add_keyword():
    """Метод для добавления ключевой фразы или автотаргетинга"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        # token = json_file["token"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        adgroup_id = json_file["adgroup_id"]
        keyword = json_file["keyword"]
        bid = json_file.get("bid", None)
        context_bid = json_file.get("context_bid", None)
        strategy_priority = json_file.get("strategy_priority", None)
        user_param1 = json_file.get("user_param1", None)
        user_param2 = json_file.get("user_param2", None)
        autotargeting_exact = json_file.get("autotargeting_exact", "NO")
        autotargeting_alternative = json_file.get("autotargeting_alternative", "NO")
        autotargeting_competitor = json_file.get("autotargeting_competitor", "NO")
        autotargeting_broader = json_file.get("autotargeting_broader", "NO")
        autotargeting_accessory = json_file.get("autotargeting_accessory", "NO")

        keyword_params = direct.create_keyword_params(adgroup_id=adgroup_id,
                                                      keyword=keyword,
                                                      bid=bid,
                                                      context_bid=context_bid,
                                                      strategy_priority=strategy_priority,
                                                      user_param1=user_param1,
                                                      user_param2=user_param2,
                                                      autotargeting_exact=autotargeting_exact,
                                                      autotargeting_alternative=autotargeting_alternative,
                                                      autotargeting_competitor=autotargeting_competitor,
                                                      autotargeting_broader=autotargeting_broader,
                                                      autotargeting_accessory=autotargeting_accessory)

        if keyword_params is None:
            logger.error("add keyword: keyword params incorrect")
            return jsonify({'error': 'keyword params incorrect'})
        else:
            result = direct.add_keywords(keywords=[keyword_params])
            if result is None:
                logger.error("add keyword: yandex direct error")
                return jsonify({'error': 'yandex direct error'})
            else:
                logger.info(f"add keyword: {result.status_code}")

                # put_query(json_file=json_file, table_name='ya_ads_addkeywords', result=result.json(), engine=engine,
                #           logger=logger)
                #
                # return jsonify(result.json())

                parsed_result = response_result(response=result, source=errors_warnings_sourse,
                                                errors_table=errors_table, warnings_table=warnings_table)

                put_query(json_file=json_file, table_name='ya_ads_addkeywords', result=parsed_result, engine=engine,
                          logger=logger)

                return jsonify(parsed_result)

    except BadRequestKeyError:
        logger.error("add keyword: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("add keyword: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'add keyword: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/updatekeyword', methods=['POST'])
@swag_from("swagger_conf/update_keyword.yml")
def update_keyword():
    """Метод для изменения параметров ключевой фразы и автотаргетинга"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        # token = json_file["token"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        keyword_id = json_file["keyword_id"]
        keyword = json_file.get("keyword", None)
        user_param1 = json_file.get("user_param1", None)
        user_param2 = json_file.get("user_param2", None)
        autotargeting_exact = json_file.get("autotargeting_exact", None)
        autotargeting_alternative = json_file.get("autotargeting_alternative", None)
        autotargeting_competitor = json_file.get("autotargeting_competitor", None)
        autotargeting_broader = json_file.get("autotargeting_broader", None)
        autotargeting_accessory = json_file.get("autotargeting_accessory", None)

        keyword_params = direct.update_keyword_params(keyword_id=keyword_id,
                                                      keyword=keyword,
                                                      user_param1=user_param1,
                                                      user_param2=user_param2,
                                                      autotargeting_exact=autotargeting_exact,
                                                      autotargeting_alternative=autotargeting_alternative,
                                                      autotargeting_competitor=autotargeting_competitor,
                                                      autotargeting_broader=autotargeting_broader,
                                                      autotargeting_accessory=autotargeting_accessory)

        if keyword_params is None:
            logger.error("update keyword: keyword params incorrect")
            return jsonify({'error': 'keyword params incorrect'})
        else:
            result = direct.update_keywords(keywords=[keyword_params])
            if result is None:
                logger.error("update keyword: yandex direct error")
                return jsonify({'error': 'yandex direct error'})
            else:
                logger.info(f"update keyword: {result.status_code}")
                return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("update keyword: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("update keyword: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'update keyword: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/managekeywords', methods=['POST'])
@swag_from("swagger_conf/manage_keywords.yml")
def manage_keywords():
    """Метод для изменения параметров ключевой фразы и автотаргетинга"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        # token = json_file["token"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        ids = json_file["ids"]

        action = json_file["action"]

        if action == "delete":
            action_ = "delete"
        elif action == "suspend":
            action_ = "suspend"
        elif action == "resume":
            action_ = "resume"
        else:
            logger.error("manage keywords: incorrect action")
            return jsonify({'error': 'incorrect action'})

        result = direct.manage_keywords(ids=ids, action=action_)

        if result is None:
            logger.error("manage keywords: yandex direct error")
            return jsonify({'error': 'yandex direct error'})
        else:
            logger.info(f"manage keywords: {result.status_code}")
            return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("manage keywords: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("manage keywords: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'manage keywords: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/wordstatreport', methods=['POST'])
@swag_from("swagger_conf/wordstat_report.yml")
def wordstat_report():
    """
    Запускает на сервере формирование отчета о статистике поисковых запросов,
    проверяет статус и скачивает отчет по готовности
    """

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        # token = json_file["token"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        phrases = json_file["phrases"]
        regions = json_file.get("regions", None)

        nwr = direct.create_new_wordstat_report(phrases=phrases, regions=regions)

        if nwr is None:
            logger.error("create wordstat report: yandex direct error")
            return jsonify({'error': 'create wordstat report - yandex direct error'})
        else:
            try:
                report_id = nwr.json()["data"]
            except KeyError:
                return jsonify({'error': nwr.json()})

            status = None
            while status != 'Done':
                time.sleep(15)
                rep_list = direct.get_wordstat_report_list()
                if rep_list is None:
                    logger.error("get wordstat report list: yandex direct error")
                    return jsonify({'error': 'get wordstat report list - yandex direct error'})
                else:
                    reports = pd.DataFrame(rep_list.json()["data"])
                    r_stat = reports[reports["ReportID"] == report_id]
                    status = r_stat["StatusReport"].values[0]

            result = direct.get_wordstat_report(report_id=report_id)

            if result is None:
                logger.error("get wordstat report: yandex direct error")
                return jsonify({'error': 'get wordstat report - yandex direct error'})

            else:
                logger.info(f"get wordstat report: {result.status_code}")
                return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("wordstat report: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("wordstat report: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'wordstat report: {ex}')
        raise HttpError(400, f'{ex}')


@celery.task()
def task_wordstat_report_async(login, token, phrases, regions):
    """
    Запускает на сервере формирование отчета о статистике поисковых запросов,
    проверяет статус и скачивает отчет по готовности
    """

    direct = YandexDirectEcomru(login, token)
    nwr = direct.create_new_wordstat_report(phrases=phrases, regions=regions)

    if nwr is None:
        return {'error': 'create wordstat report - yandex direct error'}
    else:
        try:
            report_id = nwr.json()["data"]
        except KeyError:
            return {'error': nwr.json()}

        status = None
        while status != 'Done':
            time.sleep(15)
            rep_list = direct.get_wordstat_report_list()
            if rep_list is None:
                return {'error': 'get wordstat report list - yandex direct error'}
            else:
                reports = pd.DataFrame(rep_list.json()["data"])
                r_stat = reports[reports["ReportID"] == report_id]
                status = r_stat["StatusReport"].values[0]

        result = direct.get_wordstat_report(report_id=report_id)

        if result is None:
            return {'error': 'get wordstat report - yandex direct error'}
        else:
            return result.json()


@app.route('/yandexdirect/wordstatreportasync', methods=['POST'])
@swag_from("swagger_conf/wordstat_report.yml")
def wordstat_report_async():
    """
    Формирует команду на формирование отчета о статистике поисковых запросов,
    возвращает идентификатор задачи
    """
    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)
        phrases = json_file["phrases"]
        regions = json_file.get("regions", None)
        task = task_wordstat_report_async.delay(login, token, phrases, regions)
        return jsonify({'task_id': task.id})

    except BadRequestKeyError:
        logger.error("wordstat report async: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("wordstat report async: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'wordstat report async: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/wordstatreportasync/<task_id>', methods=['GET'])
@swag_from("swagger_conf/wordstat_report_async_result.yml")
def wordstat_report_async_result(task_id):
    """Возвращает отчет о статистике поисковых запросов по id асинхронной задачи"""

    try:
        task = task_wordstat_report_async.AsyncResult(str(task_id))
        if task.state == 'SUCCESS':
            result = {'state': task.state, 'result': task.get(timeout=5)}
        else:
            result = {'state': task.state}
        return result

    except BadRequestKeyError:
        logger.error("wordstat report async result: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("wordstat report async result: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'wordstat report async result: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/forecast', methods=['POST'])
@swag_from("swagger_conf/forecast.yml")
def forecast():
    """
    Запускает на сервере формирование прогноза показов, кликов и затрат.
    Отслеживает статус и загружает прогноз по готовности
    """

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        # token = json_file["token"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        phrases = json_file["phrases"]
        regions = json_file.get("regions", None)
        currency = json_file["currency"]
        auc_bids = json_file.get("auc_bids", None)

        nf = direct.create_new_forecast(phrases=phrases, regions=regions, currency=currency, auc_bids=auc_bids)

        if nf is None:
            logger.error("forecast: yandex direct error")
            return jsonify({'error': 'create new forecast - yandex direct error'})
        else:
            try:
                forecast_id = nf.json()["data"]
            except KeyError:
                return jsonify({'error': nf.json()})

            status = None
            while status != 'Done':
                time.sleep(15)
                forecast_list = direct.get_forecast_list()
                if forecast_list is None:
                    logger.error("forecast_list list: yandex direct error")
                    return jsonify({'error': 'forecast_list list - yandex direct error'})
                else:
                    forecasts = pd.DataFrame(forecast_list.json()["data"])
                    f_stat = forecasts[forecasts["ForecastID"] == forecast_id]
                    status = f_stat["StatusForecast"].values[0]

            result = direct.get_forecast(forecast_id=forecast_id)

            if result is None:
                logger.error("get forecast: yandex direct error")
                return jsonify({'error': 'get forecast - yandex direct error'})
            else:
                logger.info(f"get forecast: {result.status_code}")
                return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("forecast: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("forecast: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'forecast: {ex}')
        raise HttpError(400, f'{ex}')


@celery.task()
def task_forecast_async(login, token, phrases, regions, currency, auc_bids):
    """
    Запускает на сервере формирование прогноза показов, кликов и затрат.
    Отслеживает статус и загружает прогноз по готовности
    """

    direct = YandexDirectEcomru(login, token)
    nf = direct.create_new_forecast(phrases=phrases, regions=regions, currency=currency, auc_bids=auc_bids)

    if nf is None:
        logger.error("forecast async: yandex direct error")
        return {'error': 'create new forecast - yandex direct error'}
    else:
        try:
            forecast_id = nf.json()["data"]
        except KeyError:
            return {'error': nf.json()}

        status = None
        while status != 'Done':
            time.sleep(15)
            forecast_list = direct.get_forecast_list()
            if forecast_list is None:
                logger.error("forecast_list list: yandex direct error")
                return {'error': 'forecast_list list - yandex direct error'}
            else:
                forecasts = pd.DataFrame(forecast_list.json()["data"])
                f_stat = forecasts[forecasts["ForecastID"] == forecast_id]
                status = f_stat["StatusForecast"].values[0]

        result = direct.get_forecast(forecast_id=forecast_id)

        if result is None:
            logger.error("get forecast async: yandex direct error")
            return {'error': 'get forecast - yandex direct error'}
        else:
            logger.info(f"get forecast: {result.status_code}")
            return result.json()


@app.route('/yandexdirect/forecastasync', methods=['POST'])
@swag_from("swagger_conf/forecast.yml")
def forecast_async():
    """
    Формирует команду на формирование прогноза показов, кликов и затрат,
    возвращает идентификатор задачи
    """
    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)
        phrases = json_file["phrases"]
        regions = json_file.get("regions", None)
        currency = json_file["currency"]
        auc_bids = json_file.get("auc_bids", None)
        task = task_forecast_async.delay(login, token, phrases, regions, currency, auc_bids)

        return jsonify({'task_id': task.id})

    except BadRequestKeyError:
        logger.error("forecast async: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("forecast async: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'forecast async: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/forecastasync/<task_id>', methods=['GET'])
@swag_from("swagger_conf/forecast_async_result.yml")
def forecast_async_result(task_id):
    """Возвращает прогноз по id асинхронной задачи"""

    try:
        task = task_forecast_async.AsyncResult(str(task_id))
        if task.state == 'SUCCESS':
            result = {'state': task.state, 'result': task.get(timeout=5)}
        else:
            result = {'state': task.state}
        return result

    except BadRequestKeyError:
        logger.error("forecast async result: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("forecast async result: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'forecast async result: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getclients', methods=['POST'])
@swag_from("swagger_conf/get_clients.yml")
def get_clients_():
    """Получить список доступных аккаунтов для клиента"""

    try:
        json_file = request.get_json(force=False)
        account_id = json_file["account_id"]

        res = get_clients(account_id, engine, logger)

        if res is None:
            raise HttpError(400, f'accounts database error')
        else:
            logger.info(f"get_clients: OK")
            return jsonify({'result': res})

    except BadRequestKeyError:
        logger.error("get_clients: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("get_clients: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'get_clients: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getcampaignsdb', methods=['POST'])
@swag_from("swagger_conf/get_campaigns_db.yml")
def get_campaigns_db():
    """Получить кампании из БД"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]

        res = get_objects_from_db(login=login, table_name='ya_ads_addcampaigns', engine=engine, logger=logger)

        if res is None:
            raise HttpError(400, f'accounts database error')
        else:
            logger.info(f"get_campaigns_db: OK")
            return jsonify({'result': res})

    except BadRequestKeyError:
        logger.error("get_campaigns_db: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("get_campaigns_db: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'get_campaigns_db: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getgroupsdb', methods=['POST'])
@swag_from("swagger_conf/get_groups_db.yml")
def get_groups_db():
    """Получить группы из БД"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        campaign_id = json_file.get("campaign_id", None)
        group_id = json_file.get("group_id", None)

        res = get_groups_from_db(login=login, campaign_id=campaign_id, group_id=group_id, table_name='ya_ads_addgroups',
                                 engine=engine, logger=logger)

        if res is None:
            raise HttpError(400, f'accounts database error')

        else:
            logger.info(f"get_campaigns_db: OK")
            return jsonify({'result': res})

    except BadRequestKeyError:
        logger.error("get_groups_db: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("get_groups_db: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'get_groups_db: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getadsdb', methods=['POST'])
@swag_from("swagger_conf/get_ads_db.yml")
def get_ads_db():
    """Получить объявления из БД"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        group_id = json_file.get("group_id", None)
        ad_id = json_file.get("ad_id", None)

        res = get_ads_from_db(login=login, group_id=group_id, ad_id=ad_id, table_name='ya_ads_addads', engine=engine,
                              logger=logger)

        if res is None:
            raise HttpError(400, f'accounts database error')

        else:
            logger.info(f"get_ads_db: OK")
            return jsonify({'result': res})

    except BadRequestKeyError:
        logger.error("get_ads_db: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("get_ads_db: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'get_ads_db: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/adddynamictextcampaign', methods=['POST'])
@swag_from("swagger_conf/add_dynamic_text_campaign.yml")
def add_dynamic_text_campaign():
    """Метод для создания динамической текстовой кампании"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        # token = json_file["token"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        s_bid_strat = json_file["s_bid_strat"]
        s_weekly_spend_limit = json_file.get("s_weekly_spend_limit", None)
        s_bid_ceiling = json_file.get("s_bid_ceiling", None)
        s_goal_id = json_file.get("s_goal_id", None)
        s_average_cpc = json_file.get("s_average_cpc", None)
        s_average_cpa = json_file.get("s_average_cpa", None)
        s_reserve_return = json_file.get("s_reserve_return", None)
        s_roi_coef = json_file.get("s_roi_coef", None)
        s_profitability = json_file.get("s_profitability", None)
        s_crr = json_file.get("s_crr", None)
        s_cpa = json_file.get("s_cpa", None)
        add_metrica_tag = json_file.get("add_metrica_tag", None)
        add_openstat_tag = json_file.get("add_openstat_tag", None)
        add_to_favorites = json_file.get("add_to_favorites", None)
        enable_area_of_interest_targeting = json_file.get("enable_area_of_interest_targeting", None)
        enable_company_info = json_file.get("enable_company_info", None)
        enable_site_monitoring = json_file.get("enable_site_monitoring", None)
        require_servicing = json_file.get("require_servicing", None)
        campaign_exact_phrase_matching_enabled = json_file.get("campaign_exact_phrase_matching_enabled", None)
        placement_search_results = json_file.get("placement_search_results", None)
        placement_product_gallery = json_file.get("placement_product_gallery", None)
        counter_ids = json_file.get("counter_ids", None)
        goal_ids = json_file.get("goal_ids", None)
        goal_vals = json_file.get("goal_vals", None)
        goal_is_metrika_source_of_value = json_file.get("goal_is_metrika_source_of_value", None)
        tracking_params = json_file.get("tracking_params", None)
        attribution_model = json_file.get("attribution_model", None)

        dynamic_txt_camp_params = direct.create_dynamic_text_camp_params(
            s_bid_strat, s_weekly_spend_limit, s_bid_ceiling, s_goal_id, s_average_cpc, s_average_cpa,
            s_reserve_return, s_roi_coef, s_profitability, s_crr, s_cpa, add_metrica_tag, add_openstat_tag,
            add_to_favorites, enable_area_of_interest_targeting, enable_company_info, enable_site_monitoring,
            require_servicing, campaign_exact_phrase_matching_enabled, placement_search_results,
            placement_product_gallery, counter_ids, goal_ids, goal_vals, goal_is_metrika_source_of_value,
            tracking_params, attribution_model)

        if dynamic_txt_camp_params is None:
            logger.error("add dynamic text campaign: txt_camp_params incorrect")
            return jsonify({'error': 'dynamic_txt_camp_params incorrect'})
        else:
            name = json_file["name"]
            start_date = json_file["start_date"]
            end_date = json_file.get("end_date", None)
            client_info = json_file.get("client_info", None)
            sms_events = json_file.get("sms_events", None)
            sms_time_from = json_file.get("sms_time_from", "9:00")
            sms_time_to = json_file.get("sms_time_to", "21:00")
            email = json_file.get("email", None)
            email_ch_pos_interval = json_file.get("email_ch_pos_interval", 60)
            email_warning_bal = json_file.get("email_warning_bal", 20)
            email_send_acc_news = json_file.get("email_send_acc_news", "NO")
            email_send_warnings = json_file.get("email_send_warnings", "NO")
            timezone = json_file.get("timezone", "Europe/Moscow")
            daily_budget_amount = json_file.get("daily_budget_amount", None)
            daily_budget_mode = json_file.get("daily_budget_mode", None)
            negative_keywords = json_file.get("negative_keywords", None)
            blocked_ips = json_file.get("blocked_ips", None)
            excluded_sites = json_file.get("excluded_sites", None)
            time_targeting_shedule = json_file.get("time_targeting_shedule", None)
            time_targeting_cons_working_weekends = json_file.get("time_targeting_cons_working_weekends", None)
            time_targeting_suspend_on_holidays = json_file.get("time_targeting_suspend_on_holidays", None)
            time_targeting_bid_percent = json_file.get("time_targeting_bid_percent", None)
            time_targeting_start_hour = json_file.get("time_targeting_start_hour", None)
            time_targeting_end_hour = json_file.get("time_targeting_end_hour", None)

            camp_params = direct.create_campaign(name=name,
                                                 start_date=start_date,
                                                 end_date=end_date,
                                                 client_info=client_info,
                                                 sms_events=sms_events,
                                                 sms_time_from=sms_time_from,
                                                 sms_time_to=sms_time_to,
                                                 email=email,
                                                 email_ch_pos_interval=email_ch_pos_interval,
                                                 email_warning_bal=email_warning_bal,
                                                 email_send_acc_news=email_send_acc_news,
                                                 email_send_warnings=email_send_warnings,
                                                 timezone=timezone,
                                                 daily_budget_amount=daily_budget_amount,
                                                 daily_budget_mode=daily_budget_mode,
                                                 negative_keywords=negative_keywords,
                                                 blocked_ips=blocked_ips,
                                                 excluded_sites=excluded_sites,
                                                 text_campaign_params=None,
                                                 mobile_app_campaign_params=None,
                                                 dynamic_text_campaign_params=dynamic_txt_camp_params[
                                                     "DynamicTextCampaign"],
                                                 cpm_banner_campaign_params=None,
                                                 smart_campaign_params=None,
                                                 time_targeting_shedule=time_targeting_shedule,
                                                 time_targeting_cons_working_weekends=time_targeting_cons_working_weekends,
                                                 time_targeting_suspend_on_holidays=time_targeting_suspend_on_holidays,
                                                 time_targeting_bid_percent=time_targeting_bid_percent,
                                                 time_targeting_start_hour=time_targeting_start_hour,
                                                 time_targeting_end_hour=time_targeting_end_hour)

            result = direct.add_camp(campaigns=[camp_params])

            if result is None:
                logger.error("add dynamic text campaign: yandex direct error")
                return jsonify({'error': 'yandex direct error'})
            else:
                logger.info(f"add dynamic text campaign: {result.status_code}")

                # put_query(json_file=json_file, table_name='ya_ads_addcampaigns', result=result.json(), engine=engine,
                #           logger=logger)
                #
                # return jsonify(result.json())

                parsed_result = response_result(response=result, source=errors_warnings_sourse,
                                                errors_table=errors_table, warnings_table=warnings_table)

                put_query(json_file=json_file, table_name='ya_ads_addcampaigns', result=parsed_result, engine=engine,
                          logger=logger)

                return jsonify(parsed_result)

    except BadRequestKeyError:
        logger.error("add dynamic text campaign: BadRequest")
        return Response(None, 400)
    except KeyError as ex:
        logger.error(f"add dynamic text campaign: KeyError {ex}")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'add dynamic text campaign: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/adddynamictextcampaignasync', methods=['POST'])
@swag_from("swagger_conf/add_dynamic_text_campaign.yml")
def add_dynamic_text_campaign_async():
    """Метод для создания динамической текстовой кампании"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)
        s_bid_strat = json_file["s_bid_strat"]
        s_weekly_spend_limit = json_file.get("s_weekly_spend_limit", None)
        s_bid_ceiling = json_file.get("s_bid_ceiling", None)
        s_goal_id = json_file.get("s_goal_id", None)
        s_average_cpc = json_file.get("s_average_cpc", None)
        s_average_cpa = json_file.get("s_average_cpa", None)
        s_reserve_return = json_file.get("s_reserve_return", None)
        s_roi_coef = json_file.get("s_roi_coef", None)
        s_profitability = json_file.get("s_profitability", None)
        s_crr = json_file.get("s_crr", None)
        s_cpa = json_file.get("s_cpa", None)
        add_metrica_tag = json_file.get("add_metrica_tag", None)
        add_openstat_tag = json_file.get("add_openstat_tag", None)
        add_to_favorites = json_file.get("add_to_favorites", None)
        enable_area_of_interest_targeting = json_file.get("enable_area_of_interest_targeting", None)
        enable_company_info = json_file.get("enable_company_info", None)
        enable_site_monitoring = json_file.get("enable_site_monitoring", None)
        require_servicing = json_file.get("require_servicing", None)
        campaign_exact_phrase_matching_enabled = json_file.get("campaign_exact_phrase_matching_enabled", None)
        placement_search_results = json_file.get("placement_search_results", None)
        placement_product_gallery = json_file.get("placement_product_gallery", None)
        counter_ids = json_file.get("counter_ids", None)
        goal_ids = json_file.get("goal_ids", None)
        goal_vals = json_file.get("goal_vals", None)
        goal_is_metrika_source_of_value = json_file.get("goal_is_metrika_source_of_value", None)
        tracking_params = json_file.get("tracking_params", None)
        attribution_model = json_file.get("attribution_model", None)

        dynamic_txt_camp_params = YandexDirectEcomru.create_dynamic_text_camp_params(
            s_bid_strat, s_weekly_spend_limit, s_bid_ceiling, s_goal_id, s_average_cpc, s_average_cpa,
            s_reserve_return, s_roi_coef, s_profitability, s_crr, s_cpa, add_metrica_tag, add_openstat_tag,
            add_to_favorites, enable_area_of_interest_targeting, enable_company_info, enable_site_monitoring,
            require_servicing, campaign_exact_phrase_matching_enabled, placement_search_results,
            placement_product_gallery, counter_ids, goal_ids, goal_vals, goal_is_metrika_source_of_value,
            tracking_params, attribution_model)

        if dynamic_txt_camp_params is None:
            logger.error("add dynamic text campaign: txt_camp_params incorrect")
            return jsonify({'error': 'dynamic_txt_camp_params incorrect'})
        else:
            name = json_file["name"]
            start_date = json_file["start_date"]
            end_date = json_file.get("end_date", None)
            client_info = json_file.get("client_info", None)
            sms_events = json_file.get("sms_events", None)
            sms_time_from = json_file.get("sms_time_from", "9:00")
            sms_time_to = json_file.get("sms_time_to", "21:00")
            email = json_file.get("email", None)
            email_ch_pos_interval = json_file.get("email_ch_pos_interval", 60)
            email_warning_bal = json_file.get("email_warning_bal", 20)
            email_send_acc_news = json_file.get("email_send_acc_news", "NO")
            email_send_warnings = json_file.get("email_send_warnings", "NO")
            timezone = json_file.get("timezone", "Europe/Moscow")
            daily_budget_amount = json_file.get("daily_budget_amount", None)
            daily_budget_mode = json_file.get("daily_budget_mode", None)
            negative_keywords = json_file.get("negative_keywords", None)
            blocked_ips = json_file.get("blocked_ips", None)
            excluded_sites = json_file.get("excluded_sites", None)
            time_targeting_shedule = json_file.get("time_targeting_shedule", None)
            time_targeting_cons_working_weekends = json_file.get("time_targeting_cons_working_weekends", None)
            time_targeting_suspend_on_holidays = json_file.get("time_targeting_suspend_on_holidays", None)
            time_targeting_bid_percent = json_file.get("time_targeting_bid_percent", None)
            time_targeting_start_hour = json_file.get("time_targeting_start_hour", None)
            time_targeting_end_hour = json_file.get("time_targeting_end_hour", None)

            camp_params = YandexDirectEcomru.create_campaign(name=name,
                                                             start_date=start_date,
                                                             end_date=end_date,
                                                             client_info=client_info,
                                                             sms_events=sms_events,
                                                             sms_time_from=sms_time_from,
                                                             sms_time_to=sms_time_to,
                                                             email=email,
                                                             email_ch_pos_interval=email_ch_pos_interval,
                                                             email_warning_bal=email_warning_bal,
                                                             email_send_acc_news=email_send_acc_news,
                                                             email_send_warnings=email_send_warnings,
                                                             timezone=timezone,
                                                             daily_budget_amount=daily_budget_amount,
                                                             daily_budget_mode=daily_budget_mode,
                                                             negative_keywords=negative_keywords,
                                                             blocked_ips=blocked_ips,
                                                             excluded_sites=excluded_sites,
                                                             text_campaign_params=None,
                                                             mobile_app_campaign_params=None,
                                                             dynamic_text_campaign_params=dynamic_txt_camp_params[
                                                                 "DynamicTextCampaign"],
                                                             cpm_banner_campaign_params=None,
                                                             smart_campaign_params=None,
                                                             time_targeting_shedule=time_targeting_shedule,
                                                             time_targeting_cons_working_weekends=time_targeting_cons_working_weekends,
                                                             time_targeting_suspend_on_holidays=time_targeting_suspend_on_holidays,
                                                             time_targeting_bid_percent=time_targeting_bid_percent,
                                                             time_targeting_start_hour=time_targeting_start_hour,
                                                             time_targeting_end_hour=time_targeting_end_hour)

            task = task_add_campaign_async.delay(login, token, camp_params, json_file)

            return jsonify({'result': task.id})

    except BadRequestKeyError:
        logger.error("add dynamic text campaign async: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("add dynamic text campaign async: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'add dynamic text campaign async: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getfeeds', methods=['POST'])
@swag_from("swagger_conf/get_feeds.yml")
def get_feeds():
    """Метод для получения информации о фидах пользователя"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        # token = json_file["token"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        ids = json_file.get("ids", None)

        result = direct.get_feeds(ids=ids)

        if result is None:
            logger.error("get feeds: yandex direct error")
            return jsonify({'error': 'yandex direct error'})
        else:
            logger.info(f"get feeds: {result.status_code}")
            return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("get feeds: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get feeds: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get feeds: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/addfeeds', methods=['POST'])
@swag_from("swagger_conf/add_feed.yml")
def add_feeds():
    """Метод для добавления фида"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        # token = json_file["token"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        name = json_file["name"]
        business_type = json_file["business_type"]
        source_type = json_file["source_type"]
        url_feed_url = json_file.get("url_feed_url", None)
        url_feed_remove_utm = json_file.get("url_feed_remove_utm", None)
        url_feed_login = json_file.get("url_feed_login", None)
        url_feed_password = json_file.get("url_feed_password", None)
        file_feed_data = json_file.get("file_feed_data", None)
        file_feed_filename = json_file.get("file_feed_filename", None)

        feed_params = direct.create_feed_params(name, business_type, source_type, url_feed_url, url_feed_remove_utm,
                                                url_feed_login, url_feed_password, file_feed_data, file_feed_filename)

        if feed_params is None:
            logger.error("add feed: feed_params incorrect")
            return jsonify({'error': 'feed params incorrect'})
        else:
            result = direct.add_feeds(feeds=[feed_params])
            if result is None:
                logger.error("add feed: yandex direct error")
                return jsonify({'error': 'yandex direct error'})
            else:
                logger.info(f"add feed: {result.status_code}")

                # put_query(json_file=json_file, table_name='ya_ads_addfeeds', result=result.json(), engine=engine,
                #           logger=logger)

                return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("add feeds: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("add feeds: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'add feeds: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/deletefeeds', methods=['POST'])
@swag_from("swagger_conf/delete_feeds.yml")
def delete_feeds():
    """Метод для удаления фидов"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        # token = json_file["token"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        ids = json_file["ids"]

        result = direct.delete_feeds(ids=ids)

        if result is None:
            logger.error("delete feeds: yandex direct error")
            return jsonify({'error': 'yandex direct error'})
        else:
            logger.info(f"delete feeds: {result.status_code}")
            return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("delete feeds: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("delete feeds: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'delete feeds: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/updatefeed', methods=['POST'])
@swag_from("swagger_conf/update_feed.yml")
def update_feed():
    """Метод для изменения параметров фида"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        # token = json_file["token"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        feed_id = json_file["feed_id"]
        name = json_file.get("name", None)
        url_feed_url = json_file.get("url_feed_url", None)
        url_feed_remove_utm = json_file.get("url_feed_remove_utm", None)
        url_feed_login = json_file.get("url_feed_login", None)
        url_feed_password = json_file.get("url_feed_password", None)
        file_feed_data = json_file.get("file_feed_data", None)
        file_feed_filename = json_file.get("file_feed_filename", None)

        feed_params = direct.update_feed_params(feed_id, name, url_feed_url, url_feed_remove_utm, url_feed_login,
                                                url_feed_password, file_feed_data, file_feed_filename)

        if feed_params is None:
            logger.error("update feed: feed_params incorrect")
            return jsonify({'error': 'feed params incorrect'})
        else:
            result = direct.update_feeds(feeds=[feed_params])
            if result is None:
                logger.error("update feed: yandex direct error")
                return jsonify({'error': 'yandex direct error'})
            else:
                logger.info(f"update feed: {result.status_code}")

                return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("update feed: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("update feed: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'update feed: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getregions', methods=['POST'])
@swag_from("swagger_conf/get_regions.yml")
def get_regions():
    """Метод для получения регионов с сервера яндекса и занесения их в базу данных"""

    try:
        json_file = request.get_json(force=False)

        login = json_file["login"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)
        update_db = to_boolean(json_file.get("update_db", "false"))

        direct = YandexDirectEcomru(login, token, lang="ru")

        result = direct.dictionaries(dict_names=["GeoRegions"])

        if result is None:
            logger.error("get regions: yandex direct error")
            return jsonify({'error': 'yandex direct error'})
        else:
            logger.info(f"get regions: {result.status_code}")

            if update_db is True:
                data = result.json()["result"]["GeoRegions"]
                add_regions(engine, logger, data, table_name="ya_ads_regions")

            return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("get regions: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get regions: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get regions: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getregionsdb', methods=['GET'])
@swag_from("swagger_conf/get_regions_db.yml")
def get_regions_db():
    """Метод для получения регионов из базы данных"""

    try:
        res = get_table_from_db(table_name='ya_ads_regions', engine=engine, logger=logger)

        print(type(res))

        if res is None:
            raise HttpError(400, f'database error')

        else:
            logger.info(f"get_regions_db: OK")
            return jsonify({'result': res})

    except BadRequestKeyError:
        logger.error("get_regions_db: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get_regions_db: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get_regions_db: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/gethtmlbyurl/url=<path:url>', methods=['GET'])
@swag_from("swagger_conf/get_html.yml")
def get_html_by_url(url):
    """Принимает url, возвращает страницу"""

    try:
        # print(url)
        ua = UserAgent()
        header = {"User-Agent": str(ua.firefox)}

        # print(header)

        resp = requests.get(url, headers=header)

        # print(resp.status_code)

        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for (name, value) in resp.raw.headers.items() if name.lower() not in excluded_headers]
        response = Response(resp.content, resp.status_code, headers=headers)
        # response = Response(resp.content, resp.status_code)

        return response

    except BadRequestKeyError:
        logger.error("get html: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get html: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get html: {ex}')
        raise HttpError(400, f'{ex}')

    except ConnectionError:
        logger.error(f'get html: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getstatgoals', methods=['POST'])
@swag_from("swagger_conf/get_stat_goals.yml")
def get_stat_goals():
    """Метод возвращает сведения о целях Яндекс Метрики, которые доступны для кампании"""

    try:
        json_file = request.get_json(force=False)

        login = json_file["login"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        campaign_ids = json_file["campaign_ids"]
        # update_db = to_boolean(json_file.get("update_db", "false"))

        result = direct.get_stat_goals(campaign_ids)

        if result is None:
            logger.error("get stat goals: yandex direct error")
            return jsonify({'error': 'yandex direct error'})
        else:
            logger.info(f"get stat goals: {result.status_code}")

            # if update_db is True:
            #     data = result.json()["result"]["GeoRegions"]
            #     add_stat_goals(login, engine, logger, data, table_name="ya_ads_stat_goals")

            return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("get stat goals: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get stat goals: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get stat goals: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getbusinessprofiles', methods=['POST'])
@swag_from("swagger_conf/get_business_profiles.yml")
def get_business_profiles():
    """Метод возвращает данные профилей организаций рекламодателя на Яндексе"""

    try:
        json_file = request.get_json(force=False)

        login = json_file["login"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        result = direct.get_business_profiles()

        if result is None:
            logger.error("get business profiles: yandex direct error")
            return jsonify({'error': 'yandex direct error'})
        else:
            logger.info(f"get business profiles: {result.status_code}")

            return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("get business profiles: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get business profiles: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get business profiles: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getvcards', methods=['POST'])
@swag_from("swagger_conf/get_v_cards.yml")
def get_v_cards():
    """Метод возвращает виртуальные визитки"""

    try:
        json_file = request.get_json(force=False)

        login = json_file["login"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        result = direct.get_v_cards()

        if result is None:
            logger.error("get v_cards: yandex direct error")
            return jsonify({'error': 'yandex direct error'})
        else:
            logger.info(f"get v_cards: {result.status_code}")

            return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("get v_cards: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get v_cards: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get v_cards: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/addvcard', methods=['POST'])
@swag_from("swagger_conf/add_v_card.yml")
def add_v_card():
    """Метод cоздает виртуальную визитку"""

    try:
        json_file = request.get_json(force=False)

        login = json_file["login"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        campaign_id = json_file["campaign_id"]
        country = json_file["country"]
        city = json_file["city"]
        company_name = json_file["company_name"]
        work_time = json_file["work_time"]
        phone_country_code = json_file["phone_country_code"]
        phone_city_code = json_file["phone_city_code"]
        phone_number = json_file["phone_number"]
        phone_extension = json_file.get("phone_extension", None)
        street = json_file.get("street", None)
        house = json_file.get("house", None)
        building = json_file.get("building", None)
        apartment = json_file.get("apartment", None)
        instant_messenger_client = json_file.get("instant_messenger_client", None)
        instant_messenger_login = json_file.get("instant_messenger_login", None)
        extra_message = json_file.get("extra_message", None)
        contact_email = json_file.get("contact_email", None)
        ogrn = json_file.get("ogrn", None)
        metro_station_id = json_file.get("metro_station_id", None)
        map_point_x = json_file.get("map_point_x", None)
        map_point_y = json_file.get("map_point_y", None)
        map_point_x1 = json_file.get("map_point_x1", None)
        map_point_y1 = json_file.get("map_point_y1", None)
        map_point_x2 = json_file.get("map_point_x2", None)
        map_point_y2 = json_file.get("map_point_y2", None)
        contact_person = json_file.get("contact_person", None)

        v_card_params = direct.create_v_card_params(campaign_id, country, city, company_name, work_time,
                                                    phone_country_code, phone_city_code, phone_number, phone_extension,
                                                    street, house, building, apartment, instant_messenger_client,
                                                    instant_messenger_login, extra_message, contact_email, ogrn,
                                                    metro_station_id, map_point_x, map_point_y, map_point_x1,
                                                    map_point_y1, map_point_x2, map_point_y2, contact_person)

        if v_card_params is None:
            logger.error("add v_card: v_card_params incorrect")
            return jsonify({'error': 'v_card_params incorrect'})
        else:
            result = direct.add_v_cards(v_cards=[v_card_params])
            if result is None:
                logger.error("add v_card: yandex direct error")
                return jsonify({'error': 'yandex direct error'})
            else:
                logger.info(f"add v_card: {result.status_code}")

                return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("add v_card: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("add v_card: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'add v_card: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/deletevcards', methods=['POST'])
@swag_from("swagger_conf/delete_v_cards.yml")
def delete_v_cards():
    """Метод удаляет виртуальные визитки"""

    try:
        json_file = request.get_json(force=False)

        login = json_file["login"]
        token = get_token_from_db(client_login=login, engine=engine, logger=logger)

        direct = YandexDirectEcomru(login, token)

        v_card_ids = json_file["v_card_ids"]

        result = direct.delete_v_cards(v_card_ids)

        if result is None:
            logger.error("delete v_cards: yandex direct error")
            return jsonify({'error': 'yandex direct error'})
        else:
            logger.info(f"delete v_cards: {result.status_code}")

            return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("delete v_cards: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("delete v_cards: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'delete v_cards: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getaddcampaigntypes', methods=['GET'])
@swag_from("swagger_conf/get_add_campaign_types.yml")
def get_campaign_types():
    """Получить из БД типы кампаний доступные к созданию"""

    try:
        result = db_work.get_add_campaign_types(engine, logger)

        if result is None:
            return jsonify({'error': 'database error'})
        else:
            logger.info(f"get_campaign_types: OK")

            return jsonify({'result': result})

    except BadRequestKeyError:
        logger.error("get_campaign_types: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get_campaign_types: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get_campaign_types: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getaddcampaigncommonparams', methods=['GET'])
@swag_from("swagger_conf/get_add_campaign_common_params.yml")
def get_campaign_common_params():
    """Получить из БД поля общих параметров для всех типов кампаний"""

    try:
        result = db_work.get_add_campaign_common_params(engine, logger)

        if result is None:
            return jsonify({'error': 'database error'})
        else:
            logger.info(f"get_campaign_common_params: OK")

            return jsonify({'result': result})

    except BadRequestKeyError:
        logger.error("get_campaign_common_params: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get_campaign_common_params: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get_campaign_common_params: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getaddcampaigntextparams', methods=['GET'])
@swag_from("swagger_conf/get_add_campaign_text_params.yml")
def get_campaign_text_params():
    """Получить из БД поля параметров для создания текстовой кампании"""

    try:
        result = db_work.get_add_campaign_text_params(engine, logger)

        if result is None:
            return jsonify({'error': 'database error'})
        else:
            logger.info(f"get_campaign_text_params: OK")

            return jsonify({'result': result})

    except BadRequestKeyError:
        logger.error("get_campaign_text_params: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get_campaign_text_params: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get_campaign_text_params: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getaddcampaigndynamictextparams', methods=['GET'])
@swag_from("swagger_conf/get_add_campaign_dynamic_text_params.yml")
def get_campaign_dynamic_text_params():
    """Получить из БД поля параметров для создания динамической текстовой кампании"""

    try:
        result = db_work.get_add_campaign_dynamic_text_params(engine, logger)

        if result is None:
            return jsonify({'error': 'database error'})
        else:
            logger.info(f"get_campaign_dynamic_text_params: OK")

            return jsonify({'result': result})

    except BadRequestKeyError:
        logger.error("get_campaign_dynamic_text_params: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get_campaign_dynamic_text_params: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get_campaign_dynamic_text_params: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getaddcampaignstrategyparams', methods=['POST'])
@swag_from("swagger_conf/get_add_campaign_strategy_params.yml")
def get_campaign_strategy_params():
    """Получить из БД поля параметров стратегии для типа кампании и типа места показа (в сетях или на поиске)"""

    try:
        json_file = request.get_json(force=False)

        campaign_type = json_file["campaign_type"]
        placement = json_file["placement"]
        strategy = json_file["strategy"]

        result = db_work.get_add_campaign_strategy_params(campaign_type, placement, strategy, engine, logger)

        if result is None:
            return jsonify({'error': 'database error'})
        else:
            logger.info(f"get_campaign_strategy_params: OK")

            return jsonify({'result': result})

    except BadRequestKeyError:
        logger.error("get_campaign_strategy_params: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get_campaign_strategy_params: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get_campaign_strategy_params: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getaddcampaignsearchstrategytypes', methods=['POST'])
@swag_from("swagger_conf/get_add_campaign_search_strategy_types.yml")
def get_campaign_search_strategy_types():
    """Получить из БД стратегии показа на поиске доступные для типа кампании"""

    try:
        json_file = request.get_json(force=False)

        campaign_type = json_file["campaign_type"]

        result = db_work.get_add_campaign_search_strategy_types(campaign_type, engine, logger)

        if result is None:
            return jsonify({'error': 'database error'})
        else:
            logger.info(f"get_campaign_search_strategy_types: OK")

            return jsonify({'result': result})

    except BadRequestKeyError:
        logger.error("get_campaign_search_strategy_types: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get_campaign_search_strategy_types: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get_campaign_search_strategy_types: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getaddcampaignnetworkstrategytypes', methods=['POST'])
@swag_from("swagger_conf/get_add_campaign_network_strategy_types.yml")
def get_campaign_network_strategy_types():
    """Получить из БД стратегии показа в сетях доступные для типа кампании с выбранной стратегией на поиске"""

    try:
        json_file = request.get_json(force=False)

        campaign_type = json_file["campaign_type"]
        search_strategy = json_file["search_strategy"]

        result = db_work.get_add_campaign_network_strategy_types(campaign_type, search_strategy, engine, logger)

        if result is None:
            return jsonify({'error': 'database error'})
        else:
            logger.info(f"get_campaign_network_strategy_types: OK")

            return jsonify({'result': result})

    except BadRequestKeyError:
        logger.error("get_campaign_network_strategy_types: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get_campaign_network_strategy_types: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get_campaign_network_strategy_types: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getaddgrouptypes', methods=['POST'])
@swag_from("swagger_conf/get_add_group_types.yml")
def get_adgroup_types():
    """Получить типы групп доступные к созданию"""

    try:
        json_file = request.get_json(force=False)

        campaign_type = json_file["campaign_type"]

        result = db_work.get_add_group_types(campaign_type, engine, logger)

        if result is None:
            return jsonify({'error': 'database error'})
        else:
            logger.info(f"get_adgroup_types: OK")

            return jsonify({'result': result})

    except BadRequestKeyError:
        logger.error("get_adgroup_types: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get_adgroup_types: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get_adgroup_types: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getaddgroupcommonparams', methods=['GET'])
@swag_from("swagger_conf/get_add_group_common_params.yml")
def get_adgroup_common_params():
    """Получить из БД поля общих параметров для всех типов групп"""

    try:
        result = db_work.get_add_group_common_params(engine, logger)

        if result is None:
            return jsonify({'error': 'database error'})
        else:
            logger.info(f"get_adgroup_common_params: OK")

            return jsonify({'result': result})

    except BadRequestKeyError:
        logger.error("get_adgroup_common_params: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get_adgroup_common_params: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get_adgroup_common_params: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getaddgrouptextfeedparams', methods=['GET'])
@swag_from("swagger_conf/get_add_group_text_feed_params.yml")
def get_adgroup_text_feed_params():
    """Получить из БД поля для группы текстово-графических объявлений (параметры фида)"""

    try:
        result = db_work.get_add_group_text_feed_params(engine, logger)

        if result is None:
            return jsonify({'error': 'database error'})
        else:
            logger.info(f"get_adgroup_text_feed_params: OK")

            return jsonify({'result': result})

    except BadRequestKeyError:
        logger.error("get_adgroup_text_feed_params: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get_adgroup_text_feed_params: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get_adgroup_text_feed_params: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getaddgroupdynamictextparams', methods=['GET'])
@swag_from("swagger_conf/get_add_group_dynamic_text_params.yml")
def get_adgroup_dynamic_text_params():
    """Получить из БД поля параметров группы динамический объявлений"""

    try:
        result = db_work.get_add_group_dynamic_text_params(engine, logger)

        if result is None:
            return jsonify({'error': 'database error'})
        else:
            logger.info(f"get_adgroup_dynamic_text_params: OK")

            return jsonify({'result': result})

    except BadRequestKeyError:
        logger.error("get_adgroup_dynamic_text_params: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get_adgroup_dynamic_text_params: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get_adgroup_dynamic_text_params: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getaddgroupdynamictextfeedparams', methods=['GET'])
@swag_from("swagger_conf/get_add_group_dynamic_text_feed_params.yml")
def get_adgroup_dynamic_text_feed_params():
    """Получить из БД поля параметров группы динамический объявлений с подтипом FEED"""

    try:
        result = db_work.get_add_group_dynamic_text_feed_params(engine, logger)

        if result is None:
            return jsonify({'error': 'database error'})
        else:
            logger.info(f"get_adgroup_dynamic_text_feed_params: OK")

            return jsonify({'result': result})

    except BadRequestKeyError:
        logger.error("get_adgroup_dynamic_text_feed_params: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get_adgroup_dynamic_text_feed_params: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get_adgroup_dynamic_text_feed_params: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getaddadtypes', methods=['POST'])
@swag_from("swagger_conf/get_add_ad_types.yml")
def get_ad_types():
    """Получить из БД типы объявлений доступные к созданию"""

    try:
        json_file = request.get_json(force=False)

        adgroup_type = json_file["adgroup_type"]

        result = db_work.get_add_ad_types(adgroup_type, engine, logger)

        if result is None:
            return jsonify({'error': 'database error'})
        else:
            logger.info(f"get_ad_types: OK")

            return jsonify({'result': result})

    except BadRequestKeyError:
        logger.error("get_ad_types: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get_ad_types: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get_ad_types: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getaddadtextadparams', methods=['GET'])
@swag_from("swagger_conf/get_add_ad_text_ad_params.yml")
def get_ad_text_ad_params():
    """Получить из БД параметры полей для создания текстово-графического объявления"""

    try:
        result = db_work.get_add_ad_text_ad_params(engine, logger)

        if result is None:
            return jsonify({'error': 'database error'})
        else:
            logger.info(f"get_ad_text_ad_params: OK")

            return jsonify({'result': result})

    except BadRequestKeyError:
        logger.error("get_ad_text_ad_params: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("get_ad_text_ad_params: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'get_ad_text_ad_params: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/getaddaddynamictextadparams', methods=['GET'])
@swag_from("swagger_conf/get_add_ad_dynamic_text_ad_params.yml")
def get_ad_dynamic_text_ad_params():
    """Получить из БД параметры полей для создания динамического объявления"""

    try:
        result = db_work.get_add_ad_dynamic_text_ad_params(engine, logger)

        if result is None:
            return jsonify({'error': 'database error'})
        else:
            logger.info(f"get_ad_dynamic_text_ad_params: OK")

            return jsonify({'result': result})

    except BadRequestKeyError:
        logger.error("get_ad_dynamic_text_ad_params: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("get_ad_dynamic_text_ad_params: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'get_ad_dynamic_text_ad_params: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexmarket/salesboost', methods=['POST'])
@swag_from("swagger_conf/market_salesboost.yml")
def market_salesboost():
    """Включение буста продаж и установка ставок"""

    try:
        json_file = request.get_json(force=False)
        token = json_file["token"]
        business_id = json_file["business_id"]
        sku_list = json_file["sku_list"]
        bids_list = json_file["bids_list"]

        y_market = YandexMarketEcomru(token=token)

        res = y_market.sales_boost(business_id, sku_list, bids_list)
        logger.info(f"""market_salesboost: {res["code"]} {res["message"]}""")

        return jsonify(res)

    except BadRequestKeyError:
        logger.error("market_salesboost: BadRequest")
        return Response(None, 400)
    except KeyError:
        logger.error("market_salesboost: KeyError")
        return Response(None, 400)
    except BaseException as ex:
        logger.error(f'market_salesboost: {ex}')
        raise HttpError(400, f'{ex}')





# @celery.task()
# def get_campaigns_async(login, text_params, dynamic_text_params):
#
#     token = get_token_from_db(client_login=login, engine=engine, logger=logger)
#     print(token)
#
#     direct = YandexDirectEcomru(login, token)
#     res = direct.get_campaigns(text_params=text_params, dynamic_text_params=dynamic_text_params)
#
#     return res

#
# @celery.task()
# def some_func_async(arg1, arg2, arg3):
#
#     return {'arg1': arg1, 'arg2': arg2, 'arg3': arg3}
#
#
# @app.route('/yandexdirect/getcampaignsasync', methods=['POST'])
# @swag_from("swagger_conf/get_campaigns_async.yml")
# def get_campaigns_():
#     """
#     Полезные ссылки с примерами:
#     Метод для вывода списка кампаний
#     https://dev.to/itz_salemm/how-to-use-celery-with-flask-2k1m
#     https://www.defpython.ru/ispolzovanie_Celery_vo_Flask
#     https://www.defpython.ru/ispolzovanie_Celery_vo_Flask_czast_2
#     https://ploshadka.net/flask-celery-rabbitmq/
#     https://habr.com/ru/post/461531/
#     https://morioh.com/p/35d9fd86c702
#     https://docs.celeryq.dev/en/stable/userguide/workers.html?ref=morioh.com#starting-the-worker
#     https://russianblogs.com/article/23431128896/
#     https://habr.com/ru/post/686820/
#     """
#
#     try:
#         json_file = request.get_json(force=False)
#         login = json_file["login"]
#         text_params = to_boolean(json_file.get("text_params", "false"))
#         dynamic_text_params = to_boolean(json_file.get("dynamic_text_params", "false"))
#         #
#         # task = get_campaigns_async.delay(login, text_params, dynamic_text_params)
#         # task = get_campaigns_async.apply_async(args=[login, text_params, dynamic_text_params])
#
#         task = some_func_async.delay(arg1=login, arg2=text_params, arg3=dynamic_text_params)
#
#         print(task.id)
#
#         if task is not None:
#             logger.info("get campaigns: OK")
#             return jsonify({'result': str(task.id)})
#         else:
#             logger.error("get campaigns: yandex direct api error")
#             return jsonify({'error': 'yandex direct api error'})
#
#     except BadRequestKeyError:
#         logger.error("get campaigns: BadRequest")
#         return Response(None, 400)
#
#     except KeyError:
#         logger.error("get campaigns: KeyError")
#         return Response(None, 400)
#
#     except BaseException as ex:
#         logger.error(f'get campaigns: {ex}')
#         raise HttpError(400, f'{ex}')
#
#
# @app.route('/yandexdirect/getcampaignsasync/<task_id>', methods=['GET'])
# @swag_from('swagger_conf/get_campaigns_async_result.yml')
# def get_campaigns_async_result(task_id):
#     """Получить кампании"""
#
#     try:
#         # task = get_campaigns_async.AsyncResult(str(task_id))
#
#         task = some_func_async.AsyncResult(str(task_id))
#
#         print(task.state)
#         print(task.info)
#
#         result = task.get(timeout=5)
#
#         response = {
#             'state': task.state,
#             'result': result,
#         }
#
#         return jsonify(response)
#
#     except BaseException as ex:
#         logger.error(f'get campaigns async result: {ex}')
#         raise HttpError(400, f'{ex}')
#
#
