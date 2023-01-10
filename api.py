from flask import Flask, jsonify, request
from flask import Response
from werkzeug.exceptions import BadRequestKeyError
from flasgger import Swagger, swag_from
from config import Configuration
import logger_api
from ecom_yandex_direct import YandexDirectEcomru
import os


app = Flask(__name__)
app.config.from_object(Configuration)
app.config['SWAGGER'] = {"title": "Swagger-UI", "uiversion": 3}

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
        token = json_file["token"]

        direct = YandexDirectEcomru(login, token)

        return jsonify(direct.get_campaigns().json())

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
        token = json_file["token"]
        campaigns = json_file["campaigns"]

        direct = YandexDirectEcomru(login, token)

        groups = direct.get_groups(campaigns=campaigns)

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
        token = json_file["token"]

        direct = YandexDirectEcomru(login, token)

        ids = json_file.get("ids", None)
        groups = json_file.get("groups", None)
        campaigns = json_file.get("campaigns", None)
        text_params = json_file.get("text_params", True)

        if text_params is True or text_params == "true":
            text_params_ = True
        elif text_params == "false":
            text_params_ = False
        else:
            text_params_ = False

        result = direct.get_ads(ids=ids, groups=groups, campaigns=campaigns, text_params=text_params_)

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
        token = json_file["token"]

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
        maintain_network_cpc = json_file.get("maintain_network_cpc", "NO")
        require_servicing = json_file.get("require_servicing", "NO")
        campain_exact_phrase_matching_enabled = json_file.get("campain_exact_phrase_matching_enabled", "NO")

        counter_ids = json_file.get("counter_ids", None)

        goal_ids = json_file.get("goal_ids", None)
        goal_vals = json_file.get("goal_vals", None)

        attr_model = json_file.get("attr_model", "LYDC")

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
                                                         enable_company_info= enable_company_info,
                                                         enable_site_monitoring=enable_site_monitoring,
                                                         exclude_paused_competing_ads=exclude_paused_competing_ads,
                                                         maintain_network_cpc=maintain_network_cpc,
                                                         require_servicing=require_servicing,
                                                         campain_exact_phrase_matching_enabled=campain_exact_phrase_matching_enabled,
                                                         counter_ids=counter_ids,
                                                         goal_ids=goal_ids,
                                                         goal_vals=goal_vals,
                                                         attr_model=attr_model)

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
                return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("add text campaign: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("add text campaign: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'add text campaign: {ex}')
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
        token = json_file["token"]

        direct = YandexDirectEcomru(login, token)

        name = json_file["name"]
        campaign_id = json_file["campaign_id"]
        region_ids = json_file["region_ids"]

        negative_keywords = json_file.get("negative_keywords", None)
        negative_keyword_set_ids = json_file.get(" negative_keyword_set_ids", None)
        tracking_params = json_file.get("tracking_params", None)
        text_feed_id = json_file.get("text_feed_id", None)
        text_feed_category_ids = json_file.get("text_feed_category_ids", None)

        group_params = direct.create_group(name=name,
                                           campaign_id=campaign_id,
                                           region_ids=region_ids,
                                           negative_keywords=negative_keywords,
                                           negative_keyword_set_ids=negative_keyword_set_ids,
                                           tracking_params=tracking_params,
                                           text_feed_id=text_feed_id,
                                           text_feed_category_ids=text_feed_category_ids)

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
                return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("add group: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("add group: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'add group: {ex}')
        raise HttpError(400, f'{ex}')


@app.route('/yandexdirect/addtextad', methods=['POST'])
@swag_from("swagger_conf/add_text_ad.yml")
def add_text_ad():
    """Метод для создания текстового объявления"""

    try:
        json_file = request.get_json(force=False)
        login = json_file["login"]
        token = json_file["token"]

        direct = YandexDirectEcomru(login, token)

        ads_group_id = json_file["ads_group_id"]

        txt_ad_title = json_file["txt_ad_title"]
        txt_ad_title2 = json_file.get("txt_ad_title2", None)
        txt_ad_text = json_file["txt_ad_text"]
        txt_mobile = json_file["txt_mobile"]
        href = json_file.get("href", None)
        turbo_page_id = json_file.get("turbo_page_id", None)
        vcard_id = json_file.get("vcard_id", None)
        business_id = json_file.get("business_id", None)
        prefer_vcard_over_business = json_file.get("prefer_vcard_over_business", None)
        txt_ad_image_hash = json_file.get("txt_ad_image_hash", None)
        sitelink_set_id = json_file.get("sitelink_set_id")
        txt_display_url_path = json_file.get("txt_display_url_path", None)
        ad_extension_ids = json_file.get("ad_extension_ids", None)
        creative_id = json_file.get("creative_id", None)
        txt_price = json_file.get("txt_price", None)
        txt_old_price = json_file.get("txt_old_price", None)
        txt_price_qualifier = json_file.get("txt_price_qualifier", None)
        txt_price_currency = json_file.get("txt_price_currency", None)
        ext_link_params = json_file.get("ext_link_params", False)

        if ext_link_params == "true":
            ext_link_params_ = True
        elif ext_link_params == "false":
            ext_link_params_ = False
        else:
            ext_link_params_ = False

        params = direct.create_ad_params(ads_group_id=ads_group_id,
                                         txt_ad_title=txt_ad_title,
                                         txt_ad_title2=txt_ad_title2,
                                         txt_ad_text=txt_ad_text,
                                         txt_mobile=txt_mobile,
                                         href=href,
                                         turbo_page_id=turbo_page_id,
                                         vcard_id=vcard_id,
                                         business_id=business_id,
                                         prefer_vcard_over_business=prefer_vcard_over_business,
                                         txt_ad_image_hash=txt_ad_image_hash,
                                         sitelink_set_id=sitelink_set_id,
                                         txt_display_url_path=txt_display_url_path,
                                         ad_extension_ids=ad_extension_ids,
                                         creative_id=creative_id,
                                         txt_price=txt_price,
                                         txt_old_price=txt_old_price,
                                         txt_price_qualifier=txt_price_qualifier,
                                         txt_price_currency=txt_price_currency,
                                         ext_link_params=ext_link_params_)

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
                return jsonify(result.json())

    except BadRequestKeyError:
        logger.error("add text ad: BadRequest")
        return Response(None, 400)

    except KeyError:
        logger.error("add text ad: KeyError")
        return Response(None, 400)

    except BaseException as ex:
        logger.error(f'add text ad: {ex}')
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
        token = json_file["token"]

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
        token = json_file["token"]

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
        token = json_file["token"]

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

