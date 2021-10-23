import asyncio
from typing import Optional
from warnings import resetwarnings
import nonebot
import json
import datetime
from playhouse.shortcuts import model_to_dict
from pydantic import BaseModel
from nonebot.adapters.cqhttp import Bot, Event, MessageEvent
from nonebot.adapters.cqhttp.event import PrivateMessageEvent, GroupMessageEvent, PrivateMessageEvent
from nonebot.adapters.cqhttp.message import Message, MessageSegment
from nonebot.plugin import on, on_command, on_message, MatcherGroup, on_regex
from nonebot.typing import T_State

from fastapi import FastAPI, Request, Path, Response, Cookie

from .utils import BossStatus, ClanBattle, ClanBattleData, CommitBattlrOnTreeResult, CommitInProgressResult, CommitRecordResult, CommitSLResult, CommitSubscribeResult, WebAuth

driver = nonebot.get_driver()

app: FastAPI = nonebot.get_app()

clanbattle = ClanBattle()


class WebLoginPost(BaseModel):
    qq_uid: str
    password: str


class WebReportRecord(BaseModel):
    clan_gid: str
    target_boss: str
    damage: Optional[str]
    is_kill_boss: bool
    froce_use_full_chance: bool
    is_proxy_report: bool
    proxy_report_member: Optional[str]
    comment: Optional[str]


class WebReportQueue(BaseModel):
    clan_gid: str
    target_boss: str
    comment: Optional[str]


class WebReportSubscribe(BaseModel):
    clan_gid: str
    target_boss: str
    target_cycle: str
    comment: Optional[str]


class WebReportSL(BaseModel):
    clan_gid: str
    boss: str
    comment: Optional[str]
    is_proxy_report: bool
    proxy_report_uid: Optional[str]


class WebReportOnTree(BaseModel):
    clan_gid: str
    boss: str
    comment: Optional[str]


class WebQueryReport(BaseModel):
    clan_gid: str
    date: Optional[str]
    member: Optional[str]
    boss: Optional[str]
    cycle: Optional[str]


class WebSetClanbattleData(BaseModel):
    clan_gid: str
    data_num: int


class WebGetRoute:
    @staticmethod
    async def get_joined_clan(uid: str):
        clan_list = clanbattle.get_joined_clan(uid)
        return {"err_code": 0, "clan_list": clan_list}

    @staticmethod
    async def boss_status(uid: str, clan_gid: str):
        clan = clanbattle.get_clan_data(clan_gid)
        boss_status = clan.get_current_boss_state()
        return {"err_code": 0, "boss_status": boss_status}

    @staticmethod
    async def member_list(uid: str, clan_gid: str):
        clan = clanbattle.get_clan_data(clan_gid)
        member_list = clan.get_clan_members_with_info()
        return{"err_code": 0, "member_list": member_list}

    @staticmethod
    async def report_unqueue(uid: str, clan_gid: str):
        clan = clanbattle.get_clan_data(clan_gid)
        result = clan.delete_battle_in_progress(uid)
        if result:
            return{"err_code": 0}
        else:
            return{"err_code": 403, "msg": "取消申请失败，请确认您已经在出刀了喵"}

    @staticmethod
    async def get_in_queue(uid: str, clan_gid: str):
        clan = clanbattle.get_clan_data(clan_gid)
        in_process_list_dict = {}
        for i in range(1, 6):
            in_process_list = []
            in_processes = clan.get_battle_in_progress(boss=i)
            for process in in_processes:
                in_process_list.append(model_to_dict(process))
            in_process_list_dict[str(i)] = in_process_list
        return {"err_code": 0, "queue": in_process_list_dict}

    @staticmethod
    async def on_tree_list(uid: str, clan_gid: str):
        clan = clanbattle.get_clan_data(clan_gid)
        on_tree_list_dict = {}
        for i in range(1, 6):
            on_tree_list = []
            on_trees = clan.get_battle_on_tree(boss=i)
            for on_tree in on_trees:
                on_tree_list.append(model_to_dict(on_tree))
            on_tree_list_dict[str(i)] = on_tree_list
        return {"err_code": 0, "on_tree": on_tree_list_dict}

    @staticmethod
    async def subscribe_list(uid: str, clan_gid: str):
        clan = clanbattle.get_clan_data(clan_gid)
        subscribe_list_dict = {}
        for i in range(1, 6):
            subscribe_list = []
            subscribes = clan.get_battle_subscribe(boss=i)
            for subscribe in subscribes:
                subscribe_list.append(model_to_dict(subscribe))
            subscribe_list_dict[str(i)] = subscribe_list
        return {"err_code": 0, "subscribe": subscribe_list_dict}

    @staticmethod
    async def battle_status(uid: str, clan_gid: str):
        clan = clanbattle.get_clan_data(clan_gid)
        status_list = []
        members = clan.get_clan_members()
        for member in members:
            status = clan.get_today_record_status(member)
            status_list.append(status)
        return {"err_code": 0, "status": status_list}

    @staticmethod
    async def current_clanbattle_data_num(uid: str, clan_gid: str):
        clan = clanbattle.get_clan_data(clan_gid)
        data_num = clan.get_current_clanbattle_data()
        return{"err_code": 0, "data_num": data_num}


@app.get("/api/clanbattle/{api_name}")
async def _(api_name: str, response: Response, clan_gid: str = None, session: str = Cookie(None)):
    if not (uid := WebAuth.check_session_valid(session)):
        return {"err_code": -1, "msg": "会话错误，请重新登录"}
    if not hasattr(WebGetRoute, api_name):
        response.status_code = 404
        return {"err_code": 404, "msg": "找不到该路由"}
    if api_name in ["get_joined_clan"]:
        ret = await getattr(WebGetRoute, api_name)(uid=uid)
    else:
        joined_clan = clanbattle.get_joined_clan(uid)
        if not clan_gid in joined_clan:
            return {"err_code": 403, "msg": "您还没有加入该公会"}
        #clan = clanbattle.get_clan_data(clan_gid)
        ret = await getattr(WebGetRoute, api_name)(uid=uid, clan_gid=clan_gid)
    return ret


@app.post("/api/clanbattle/login")
async def _(item: WebLoginPost, request: Request, response: Response):
    login_item = WebAuth.login(item.qq_uid, item.password)
    if login_item[0] == 404:
        return {"err_code": 404, "msg": "找不到该用户"}
    elif login_item[0] == 403:
        return {"err_code": 403, "msg": "密码错误"}
    session = login_item[1]
    response.set_cookie(key="session", value=session)
    return {"err_code": 0, "msg": "", "cookie": session}


@app.post("/api/clanbattle/report_record")
async def _(item: WebReportRecord, session: str = Cookie(None)):
    if not (uid := WebAuth.check_session_valid(session)):
        return {"err_code": -1, "msg": "会话错误，请重新登录"}
    joined_clan = clanbattle.get_joined_clan(uid)
    if not item.clan_gid in joined_clan:
        return {"err_code": 403, "msg": "您还没有加入该公会"}
    if item.is_proxy_report:
        joined_clan = clanbattle.get_joined_clan(item.proxy_report_member)
        if not item.clan_gid in joined_clan:
            return {"err_code": 403, "msg": "您还没有加入该公会"}
    clan = clanbattle.get_clan_data(item.clan_gid)
    challenge_boss = int(item.target_boss)
    proxy_report_uid = item.proxy_report_member if item.is_proxy_report else None
    comment = item.comment if item.comment else None
    force_use_full_chance = item.froce_use_full_chance
    if not item.is_kill_boss:
        challenge_damage = item.damage
    else:
        boss_status = clan.get_current_boss_state()[challenge_boss-1]
        challenge_damage = str(boss_status.boss_hp)
    if item.is_proxy_report:
        result = await clan.commit_record(proxy_report_uid, challenge_boss, challenge_damage, comment, uid, force_use_full_chance)
        uid = proxy_report_uid
    else:
        result = await clan.commit_record(uid, challenge_boss, challenge_damage, comment, None, force_use_full_chance)
    bot: Bot = list(nonebot.get_bots().values())[0]
    if result == CommitRecordResult.success:
        record = clan.get_recent_record(uid)[0]
        today_status = clan.get_today_record_status(uid)
        boss_status = clan.get_current_boss_state()[challenge_boss-1]
        if today_status.last_is_addition:
            record_type = "补偿刀"
        else:
            record_type = "完整刀"
        await bot.send_group_msg(group_id=item.clan_gid, message="网页上报数据：\n" + MessageSegment.at(uid) + f"对{challenge_boss}王造成了{record.damage}点伤害\n今日第{today_status.today_challenged}刀，{record_type}\n当前{challenge_boss}王第{boss_status.target_cycle}周目，生命值{boss_status.boss_hp}")
        return{"err_code": 0}
    elif result == CommitRecordResult.illegal_damage_inpiut:
        return{"err_code": 403, "msg": "上报的伤害格式不合法"}
    elif result == CommitRecordResult.damage_out_of_hp:
        return{"err_code": 403, "msg": "上报的伤害超出了boss血量，如已击杀请使用尾刀指令"}
    elif result == CommitRecordResult.check_record_legal_failed:
        return{"err_code": 403, "msg": "上报数据合法性检查错误，请检查是否正确上报"}
    elif result == CommitRecordResult.member_not_in_clan:
        return{"err_code": 403, "msg": "您还未加入公会，请发送“加入公会”加入"}


@app.post("/api/clanbattle/report_queue")
async def _(item: WebReportQueue, session: str = Cookie(None)):
    if not (uid := WebAuth.check_session_valid(session)):
        return {"err_code": -1, "msg": "会话错误，请重新登录"}
    joined_clan = clanbattle.get_joined_clan(uid)
    if not item.clan_gid in joined_clan:
        return {"err_code": 403, "msg": "您还没有加入该公会"}
    clan = clanbattle.get_clan_data(item.clan_gid)
    challenge_boss = int(item.target_boss)
    comment = item.comment if item.comment else None
    result = clan.commit_battle_in_progress(uid, challenge_boss, comment)
    bot: Bot = list(nonebot.get_bots().values())[0]
    if result == CommitInProgressResult.success:
        await bot.send_group_msg(group_id=item.clan_gid, message=MessageSegment.at(uid) + f"开始挑战{challenge_boss}王")
        return{"err_code": 0}
    elif result == CommitInProgressResult.already_in_battle:
        return{"err_code": 403, "msg": "您已经有正在挑战的boss"}
    elif result == CommitInProgressResult.illegal_target_boss:
        return{"err_code": 403, "msg": "您目前无法挑战这个boss"}
    elif result == CommitInProgressResult.member_not_in_clan:
        return{"err_code": 403, "msg": "您还未加入公会，请发送“加入公会”加入"}


@app.post("/api/clanbattle/report_subscribe")
async def _(item: WebReportSubscribe, session: str = Cookie(None)):
    if not (uid := WebAuth.check_session_valid(session)):
        return {"err_code": -1, "msg": "会话错误，请重新登录"}
    joined_clan = clanbattle.get_joined_clan(uid)
    if not item.clan_gid in joined_clan:
        return {"err_code": 403, "msg": "您还没有加入该公会"}
    clan = clanbattle.get_clan_data(item.clan_gid)
    challenge_boss = int(item.target_boss)
    cycle = int(item.target_cycle)
    comment = item.comment if item.comment else None
    result = clan.commit_batle_subscribe(uid, challenge_boss, cycle, comment)
    bot: Bot = list(nonebot.get_bots().values())[0]
    if result == CommitSubscribeResult.success:
        await bot.send_group_msg(group_id=item.clan_gid, message=MessageSegment.at(uid) + f"预约了{cycle}周目{challenge_boss}王")
        return{"err_code": 0}
    elif result == CommitSubscribeResult.already_in_progress:
        return{"err_code": 403, "msg": "您已经正在挑战这个boss了"}
    elif result == CommitSubscribeResult.already_subscribed:
        return{"err_code": 403, "msg": "您已经预约了这个boss了"}
    elif result == CommitSubscribeResult.boss_cycle_already_killed:
        return{"err_code": 403, "msg": "boss已经死亡，请刷新页面重新查看"}
    elif result == CommitSubscribeResult.member_not_in_clan:
        return{"err_code": 403, "msg": "您还未加入公会，请发送“加入公会”加入"}


@app.post("/api/clanbattle/report_unsubscribe")
async def _(item: WebReportSubscribe, session: str = Cookie(None)):
    if not (uid := WebAuth.check_session_valid(session)):
        return {"err_code": -1, "msg": "会话错误，请重新登录"}
    joined_clan = clanbattle.get_joined_clan(uid)
    if not item.clan_gid in joined_clan:
        return {"err_code": 403, "msg": "您还没有加入该公会"}
    clan = clanbattle.get_clan_data(item.clan_gid)
    challenge_boss = int(item.target_boss)
    cycle = int(item.target_cycle)
    result = clan.delete_battle_subscribe(uid, challenge_boss, cycle)
    if result:
        return{"err_code": 0}
    else:
        return{"err_code": 403, "msg": "取消预约失败，请确认您已经预约该boss喵"}


@app.post("/api/clanbattle/report_ontree")
async def _(item: WebReportOnTree, session: str = Cookie(None)):
    if not (uid := WebAuth.check_session_valid(session)):
        return {"err_code": -1, "msg": "会话错误，请重新登录"}
    joined_clan = clanbattle.get_joined_clan(uid)
    if not item.clan_gid in joined_clan:
        return {"err_code": 403, "msg": "您还没有加入该公会"}
    clan = clanbattle.get_clan_data(item.clan_gid)
    boss = int(item.boss)
    comment = item.comment if item.comment else None
    result = clan.commit_battle_on_tree(uid, boss, comment)
    if result == CommitBattlrOnTreeResult.success:
        return{"err_code": 0}
    elif result == CommitBattlrOnTreeResult.already_in_other_boss_progress:
        return{"err_code": 403, "msg": "您正在挑战其他Boss，无法在这里挂树哦"}
    elif result == CommitBattlrOnTreeResult.already_on_tree:
        return{"err_code": 403, "msg": "您已经在树上了，不用再挂了"}
    elif result == CommitBattlrOnTreeResult.member_not_in_clan:
        return{"err_code": 403, "msg": "您还未加入公会，请发送“加入公会”加入"}


@app.post("/api/clanbattle/report_sl")
async def _(item: WebReportSL, session: str = Cookie(None)):
    if not (uid := WebAuth.check_session_valid(session)):
        return {"err_code": -1, "msg": "会话错误，请重新登录"}
    joined_clan = clanbattle.get_joined_clan(uid)
    if not item.clan_gid in joined_clan:
        return {"err_code": 403, "msg": "您还没有加入该公会"}
    if item.is_proxy_report:
        joined_clan = clanbattle.get_joined_clan(item.proxy_report_uid)
        if not item.clan_gid in joined_clan:
            return {"err_code": 403, "msg": "您还没有加入该公会"}
    clan = clanbattle.get_clan_data(item.clan_gid)
    boss = int(item.boss)
    proxy_report_uid = item.proxy_report_uid if item.is_proxy_report else None
    comment = item.comment if item.comment else None
    if item.is_proxy_report:
        result = clan.commit_battle_sl(proxy_report_uid, boss, comment, uid)
    else:
        result = clan.commit_battle_sl(uid, boss, comment, proxy_report_uid)
    if result == CommitSLResult.success:
        return{"err_code": 0}
    elif result == CommitSLResult.already_sl:
        return{"err_code": 403, "msg": "您今天已经使用过SL了"}
    elif result == CommitSLResult.member_not_in_clan:
        return{"err_code": 403, "msg": "您还未加入公会，请发送“加入公会”加入"}


@app.post("/api/clanbattle/query_record")
async def _(item: WebQueryReport, session: str = Cookie(None)):
    if not (uid := WebAuth.check_session_valid(session)):
        return {"err_code": -1, "msg": "会话错误，请重新登录"}
    joined_clan = clanbattle.get_joined_clan(uid)
    if not item.clan_gid in joined_clan:
        return {"err_code": 403, "msg": "您还没有加入该公会"}
    clan = clanbattle.get_clan_data(item.clan_gid)
    uid = item.member if item.member != '' else None
    boss = int(item.boss) if item.boss != '' else None
    cycle = int(item.cycle) if item.cycle != '' else None
    if item.date and item.date != '':
        day_data = item.date.split('T')[0]
        detla = datetime.timedelta(
            hours=9) if clan.clan_info.clan_type == "jp" else datetime.timedelta(hours=8)
        now_time_today = datetime.datetime.strptime(
            day_data, "%Y-%m-%d") + datetime.timedelta(days=1)
        start_time = now_time_today + datetime.timedelta(hours=5) - detla
        end_time = now_time_today + datetime.timedelta(hours=29) - detla
    else:
        start_time = None
        end_time = None
    record_list = []
    records = clan.get_record(uid=uid, boss=boss, cycle=cycle,
                              start_time=start_time, end_time=end_time, time_desc=True)
    if not records:
        return {"err_code": 0, "record": []}
    for record in records:
        record_list.append(model_to_dict(record))
    return {"err_code": 0, "record": record_list}


@app.post("/api/clanbattle/change_current_clanbattle_data_num")
async def _(item: WebSetClanbattleData, session: str = Cookie(None)):
    if not (uid := WebAuth.check_session_valid(session)):
        return {"err_code": -1, "msg": "会话错误，请重新登录"}
    joined_clan = clanbattle.get_joined_clan(uid)
    if not item.clan_gid in joined_clan:
        return {"err_code": 403, "msg": "您还没有加入该公会"}
    clan = clanbattle.get_clan_data(item.clan_gid)
    if not clan.check_admin_permission(str(uid)):
        return {"err_code": -2, "msg": "您不是会战管理员，无权切换会战档案"}
    clan.set_current_clanbattle_data(item.data_num)
    bot: Bot = list(nonebot.get_bots().values())[0]
    gid = clan.clan_info.clan_gid
    await bot.send_group_msg(group_id=gid, message=f"会战管理员已经将会战档案切换为{item.data_num}，请注意")
    return {"err_code": 0, "msg": "设置成功"}


class clanbattle_qq:
    worker = MatcherGroup(
        type="message", block=True
    )
    create_clan = worker.on_regex(r"^创建([台日])服公会")
    commit_record = worker.on_regex(
        r"^报刀(整)?([1-5]{1})( )?(\d+[EeKkWwBb]{0,2})?([:：](.*?))?(\[CQ:at,qq=([1-9][0-9]{4,})\] ?)?$"
    )
    commit_kill_record = worker.on_regex(
        r"^尾刀(整)?([1-5]{1})([:：](.*?))?(\[CQ:at,qq=([1-9][0-9]{4,})\] ?)?$")
    progress = worker.on_regex(r"^(状态|查)([1-5]{0,5})?$")
    query_recent_record = worker.on_regex(r"^查刀$")
    queue = worker.on_regex(r"^申请(出刀)?([1-5]{1})([:：](.*?))?$")
    unqueue = worker.on_regex(r"^取消申请$")
    showqueue = worker.on_regex(r"^出刀表([1-5]{1,5})?$")
    #clearqueue = worker.on_regex(r"^[清删][空除]出刀表([1-5]{1,5})?$")
    on_tree = worker.on_regex(
        r"^挂树([1-5]{1})([:：](.*?))?(\[CQ:at,qq=([1-9][0-9]{4,})\] ?)?$"
    )
    query_on_tree = worker.on_regex(r"^查树$")
    subscribe = worker.on_regex(r"^预约([1-5]{1})( )?([0-9]{1,3})?([:：](.*?))?$")
    unsubscribe = worker.on_regex(r"^取消预约([1-5]{1})( )?([0-9]{1,3})?$")
    undo_record_commit = worker.on_regex(
        r"^撤[回销]?(\[CQ:at,qq=([1-9][0-9]{4,})\] ?)?$"
    )
    sl = worker.on_regex(
        r"^[sS][lL](\?)?([1-5]{1})([:：](.*?))?(\[CQ:at,qq=([1-9][0-9]{4,})\] ?)?$")
    sl_query = on_regex(r"^查[sS][lL](\[CQ:at,qq=([1-9][0-9]{4,})\] ?)?$")
    webview = worker.on_regex(r"^面板$")
    help = worker.on_regex(r"^帮助$")
    join_clan = worker.on_regex(r"^加入公会(\[CQ:at,qq=([1-9][0-9]{4,})\] ?)?$")
    leave_clan = worker.on_regex(r"^退出公会$")
    refresh_clan_admin = worker.on_regex(r"^刷新会战管理员列表$")
    rename_clan_uname = worker.on_regex(
        r"^修改昵称 ?(.{1,20})(\[CQ:at,qq=([1-9][0-9]{4,})\] ?)?")
    rename_clan = worker.on_regex(r"^修改公会名称 ?(.{1,20})")
    remove_clan_member = worker.on_regex(r"^移出公会 ?(.{1,20})")
    reset_password = worker.on_regex(r"^设置密码 ?(.{1,20})$")
    #killcalc = worker.on_regex(r"^合刀( )?(\d+) (\d+) (\d+)( \d+)?$")


@clanbattle_qq.create_clan.handle()
async def create_clan_qq(bot: Bot, event: GroupMessageEvent, state: T_State):
    gid = str(event.group_id)
    clan_area = state['_matched_groups'][0]
    if clan_area == "日":
        clan_type = "jp"
    elif clan_area == "台":
        clan_type = "tw"
    clan = clanbattle.get_clan_data(gid)
    if clan:
        await clanbattle_qq.create_clan.send("公会已经存在！")
    else:
        group_info = await bot.get_group_info(group_id=event.group_id)
        group_name = group_info["group_name"]
        group_member_list = await bot.get_group_member_list(group_id=event.group_id)
        admin_list = []
        for member in group_member_list:
            if member["role"] in ["owner", "admin"] and member["user_id"] != int(bot.self_id):
                admin_list.append(str(member["user_id"]))
        clanbattle.create_clan(gid, group_name, clan_type, admin_list)
        await clanbattle_qq.create_clan.send("公会创建成功，请发送“帮助”查看使用说明")
        clan = clanbattle.get_clan_data(gid)
        if len(group_member_list) > 31:
            await clanbattle_qq.create_clan.send("当前群内人数过多，仅自动加入管理员，请手动加入需要加入公会的群员")
            for member in group_member_list:
                if member["role"] in ["owner", "admin"] and member["user_id"] != int(bot.self_id):
                    clan.add_clan_member(str(
                        member["user_id"]), member["card"] if member["card"] != "" else member["nickname"])
        else:
            for member in group_member_list:
                if member["user_id"] != int(bot.self_id):
                    clan.add_clan_member(str(
                        member["user_id"]), member["card"] if member["card"] != "" else member["nickname"])
            await clanbattle_qq.create_clan.send("已经将全部群成员加入公会")


@clanbattle_qq.progress.handle()
async def get_clanbatle_status_qq(bot: Bot, event: GroupMessageEvent, state: T_State):
    gid = str(event.group_id)
    clan = clanbattle.get_clan_data(gid)
    if not clan:
        await clanbattle_qq.progress.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    boss_status = clan.get_current_boss_state()
    if state['_matched_groups'][0] == "状态" and not state['_matched_groups'][1]:
        msg = "当前状态：\n"
        for boss in boss_status:
            msg += f"{boss.target_cycle}周目{boss.target_boss}王，生命值{boss.boss_hp}\n"
        status = clan.get_today_record_status_total()
        msg += f"今日已出{status[0]}刀，剩余{status[1]}刀补偿刀"
        await clanbattle_qq.progress.finish(msg.strip())
    elif state['_matched_groups'][1]:
        boss_count = int(state['_matched_groups'][1])
        boss = boss_status[boss_count-1]
        msg = f"当前{boss_count}王位于{boss.target_cycle}周目，剩余血量{boss.boss_hp}\n"
        subs = clan.get_battle_subscribe(
            boss=boss_count, boss_cycle=boss.target_cycle)
        if subs:
            for sub in subs:
                msg += MessageSegment.at(sub.member_uid)
            msg += "已经预约该boss"
        in_processes = clan.get_battle_in_progress(boss=boss_count)
        if in_processes:
            if subs:
                msg += "\n"
            in_process_list = []
            for proc in in_processes:
                in_process_list += clan.get_user_info(proc.member_uid).uname
            msg += " ".join(in_process_list) + "正在出刀"
        on_tree = clan.get_battle_on_tree(boss=boss_count)
        if on_tree:
            if in_processes or subs:
                msg += "\n"
            msg += f"当前有{len(on_tree)}个人挂在树上"
        await clanbattle_qq.progress.finish(msg.strip() if isinstance(msg, str) else msg)


@clanbattle_qq.commit_record.handle()
async def commit_record_qq(bot: Bot, event: GroupMessageEvent, state: T_State):
    proxy_report_uid: str = None
    if not state['_matched_groups'][7]:
        uid = str(event.user_id)
    else:
        uid = state['_matched_groups'][7]
        proxy_report_uid = str(event.user_id)
    force_use_full_chance = True if state['_matched_groups'][0] else False
    challenge_boss = int(state['_matched_groups'][1]
                         ) if state['_matched_groups'][1] else None
    challenge_damage = state['_matched_groups'][3]
    comment = state['_matched_groups'][5]
    clan = clanbattle.get_clan_data(str(event.group_id))
    if not clan:
        await clanbattle_qq.commit_record.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    result = await clan.commit_record(uid, challenge_boss, challenge_damage, comment, proxy_report_uid, force_use_full_chance)
    if result == CommitRecordResult.success:
        record = clan.get_recent_record(uid)[0]
        today_status = clan.get_today_record_status(uid)
        boss_status = clan.get_current_boss_state()[challenge_boss-1]
        if today_status.last_is_addition:
            record_type = "补偿刀"
        else:
            record_type = "完整刀"
        await clanbattle_qq.commit_record.finish(MessageSegment.at(event.user_id) + f"对{challenge_boss}王造成了{record.damage}点伤害\n今日第{today_status.today_challenged}刀，{record_type}\n当前{challenge_boss}王第{boss_status.target_cycle}周目，生命值{boss_status.boss_hp}")
    elif result == CommitRecordResult.illegal_damage_inpiut:
        await clanbattle_qq.commit_record.finish("上报的伤害格式不合法")
    elif result == CommitRecordResult.damage_out_of_hp:
        await clanbattle_qq.commit_record.finish("上报的伤害超出了boss血量，如已击杀请使用尾刀指令")
    elif result == CommitRecordResult.check_record_legal_failed:
        await clanbattle_qq.commit_record.finish("上报数据合法性检查错误，请检查是否正确上报")
    elif result == CommitRecordResult.member_not_in_clan:
        await clanbattle_qq.commit_record.finish("您还未加入公会，请发送“加入公会”加入")


@clanbattle_qq.commit_kill_record.handle()
async def commit_kill_record(bot: Bot, event: GroupMessageEvent, state: T_State):
    proxy_report_uid: str = None
    if not state['_matched_groups'][5]:
        uid = str(event.user_id)
    else:
        uid = state['_matched_groups'][5]
        proxy_report_uid = str(event.user_id)
    force_use_full_chance = True if state['_matched_groups'][0] else False
    challenge_boss = int(state['_matched_groups'][1]
                         ) if state['_matched_groups'][1] else None
    comment = state['_matched_groups'][3]
    clan = clanbattle.get_clan_data(str(event.group_id))
    boss_status = clan.get_current_boss_state()[challenge_boss-1]
    challenge_damage = str(boss_status.boss_hp)
    if not clan:
        await clanbattle_qq.commit_kill_record.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    result = await clan.commit_record(uid, challenge_boss, challenge_damage, comment, proxy_report_uid, force_use_full_chance)
    if result == CommitRecordResult.success:
        record = clan.get_recent_record(uid)[0]
        today_status = clan.get_today_record_status(uid)
        boss_status = clan.get_current_boss_state()[challenge_boss-1]
        if today_status.last_is_addition:
            record_type = "补偿刀"
        else:
            record_type = "完整刀"
        await clanbattle_qq.commit_kill_record.finish(MessageSegment.at(event.user_id) + f"对{challenge_boss}王造成了{record.damage}点伤害并击破\n今日第{today_status.today_challenged}刀，{record_type}\n当前{challenge_boss}王第{boss_status.target_cycle}周目，生命值{boss_status.boss_hp}")
    elif result == CommitRecordResult.illegal_damage_inpiut:
        await clanbattle_qq.commit_kill_record.finish("上报的伤害格式不合法")
    elif result == CommitRecordResult.damage_out_of_hp:
        await clanbattle_qq.commit_kill_record.finish("上报的伤害超出了boss血量，如已击杀请使用尾刀指令")
    elif result == CommitRecordResult.check_record_legal_failed:
        await clanbattle_qq.commit_kill_record.finish("上报数据合法性检查错误，请检查是否正确上报")
    elif result == CommitRecordResult.member_not_in_clan:
        await clanbattle_qq.commit_kill_record.finish("您还未加入公会，请发送“加入公会”加入")


@clanbattle_qq.queue.handle()
async def commit_in_progress(bot: Bot, event: GroupMessageEvent, state: T_State):
    uid = str(event.user_id)
    challenge_boss = int(state['_matched_groups'][1])
    comment = state['_matched_groups'][3]
    clan = clanbattle.get_clan_data(str(event.group_id))
    if not clan:
        await clanbattle_qq.queue.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    if processes := clan.get_battle_in_progress(boss=challenge_boss):
        in_process_list = []
        for proc in processes:
            in_process_list += clan.get_user_info(proc.member_uid).uname
        msg = " ".join(in_process_list) + "正在对当前boss出刀，请注意"
        await clanbattle_qq.queue.send(msg)
        await asyncio.sleep(0.2)
    result = clan.commit_battle_in_progress(uid, challenge_boss, comment)
    if result == CommitInProgressResult.success:
        await clanbattle_qq.queue.finish(MessageSegment.at(uid) + f"开始挑战{challenge_boss}王")
    elif result == CommitInProgressResult.already_in_battle:
        await clanbattle_qq.queue.finish("您已经有正在挑战的boss")
    elif result == CommitInProgressResult.illegal_target_boss:
        await clanbattle_qq.queue.finish("您目前无法挑战这个boss")
    elif result == CommitInProgressResult.member_not_in_clan:
        await clanbattle_qq.queue.finish("您还未加入公会，请发送“加入公会”加入")


@clanbattle_qq.on_tree.handle()
async def commit_on_tree(bot: Bot, event: GroupMessageEvent, state: T_State):
    uid = str(event.user_id)
    challenge_boss = int(state['_matched_groups'][0])
    comment = state['_matched_groups'][2]
    if not state['_matched_groups'][4]:
        uid = str(event.user_id)
    else:
        uid = state['_matched_groups'][4]
    clan = clanbattle.get_clan_data(str(event.group_id))
    if not clan:
        await clanbattle_qq.on_tree.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    result = clan.commit_battle_on_tree(uid, challenge_boss, comment)
    if result == CommitBattlrOnTreeResult.success:
        await clanbattle_qq.on_tree.finish("嘿呀，"+MessageSegment.at(uid) + f"在{challenge_boss}王挂树了")
    elif result == CommitBattlrOnTreeResult.already_in_other_boss_progress:
        await clanbattle_qq.on_tree.finish("您已经申请挑战其他boss了")
    elif result == CommitBattlrOnTreeResult.already_on_tree:
        await clanbattle_qq.on_tree.finish("您已经挂在树上了")
    elif result == CommitBattlrOnTreeResult.illegal_target_boss:
        await clanbattle_qq.on_tree.finish("您现在还不能挂在这棵树上")
    elif result == CommitBattlrOnTreeResult.member_not_in_clan:
        await clanbattle_qq.on_tree.finish("您还未加入公会，请发送“加入公会”加入")


@clanbattle_qq.subscribe.handle()
async def commit_subscribe(bot: Bot, event: GroupMessageEvent, state: T_State):
    uid = str(event.user_id)
    challenge_boss = int(state['_matched_groups'][0])
    comment = state['_matched_groups'][4]
    cycle = int(state['_matched_groups'][2]
                ) if state['_matched_groups'][2] else None
    clan = clanbattle.get_clan_data(str(event.group_id))
    if not clan:
        await clanbattle_qq.subscribe.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    result = clan.commit_batle_subscribe(uid, challenge_boss, cycle,  comment)
    if result == CommitSubscribeResult.success:
        await clanbattle_qq.subscribe.finish("预约成功")
    elif result == CommitSubscribeResult.boss_cycle_already_killed:
        await clanbattle_qq.subscribe.finish("当前boss已经被击杀")
    elif result == CommitSubscribeResult.already_in_progress:
        await clanbattle_qq.subscribe.finish("您已经在挑战该boss了")
    elif result == CommitSubscribeResult.already_subscribed:
        await clanbattle_qq.subscribe.finish("您已经预约过该boss了")
    elif result == CommitSubscribeResult.member_not_in_clan:
        await clanbattle_qq.subscribe.finish("您还未加入公会，请发送“加入公会”加入")


@clanbattle_qq.join_clan.handle()
async def join_clan(bot: Bot, event: GroupMessageEvent, state: T_State):
    if not state['_matched_groups'][1]:
        uid = str(event.user_id)
    else:
        uid = state['_matched_groups'][1]
    clan = clanbattle.get_clan_data(str(event.group_id))
    if not clan:
        await clanbattle_qq.join_clan.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    group_member_list = await bot.get_group_member_list(group_id=event.group_id)
    for member in group_member_list:
        if member["user_id"] != int(bot.self_id) and member["user_id"] == int(uid):
            clan.add_clan_member(str(
                member["user_id"]), member["card"] if member["card"] != "" else member["nickname"])
    await clanbattle_qq.join_clan.finish("加入成功")


@clanbattle_qq.undo_record_commit.handle()
async def undo_record_commit(bot: Bot, event: GroupMessageEvent, state: T_State):
    if not state['_matched_groups'][1]:
        uid = str(event.user_id)
    else:
        uid = state['_matched_groups'][1]
    clan = clanbattle.get_clan_data(str(event.group_id))
    if not clan:
        await clanbattle_qq.undo_record_commit.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    ret = clan.delete_recent_record(uid)
    if ret:
        await clanbattle_qq.undo_record_commit.finish("出刀撤回成功")
    else:
        await clanbattle_qq.undo_record_commit.finish("出刀撤回失败，您只能按顺序撤回出刀记录")


@clanbattle_qq.unsubscribe.handle()
async def unsubscribe_boss(bot: Bot, event: GroupMessageEvent, state: T_State):
    uid = str(event.user_id)
    challenge_boss = int(state['_matched_groups'][0])
    cycle = int(state['_matched_groups'][2]
                ) if state['_matched_groups'][2] else None
    clan = clanbattle.get_clan_data(str(event.group_id))
    if not clan:
        await clanbattle_qq.unsubscribe.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    result = clan.delete_battle_subscribe(uid, challenge_boss, cycle)
    if result:
        await clanbattle_qq.unsubscribe.finish("取消预约成功desu")
    else:
        await clanbattle_qq.unsubscribe.finish("取消预约失败，请确认您已经预约该boss喵")


@clanbattle_qq.query_recent_record.handle()
async def query_recent_record(bot: Bot, event: GroupMessageEvent, state: T_State):
    clan = clanbattle.get_clan_data(str(event.group_id))
    if not clan:
        await clanbattle_qq.query_recent_record.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    records = clan.get_recent_record(3)
    if not records:
        await clanbattle_qq.query_recent_record.finish("现在还没有出刀记录哦，快去出刀吧")
    else:
        msg = "最近三条出刀记录：\n"
        for record in records:
            msg += f"{clan.get_user_info(record.member_uid).uname}于{record.record_time.strftime('%m月%d日%H时%M分')}对{record.target_cycle}周目{record.target_boss}王造成了{record.damage}点伤害\n\n"
        msg += "更多记录请前往网页端查看"
        await clanbattle_qq.query_recent_record.finish(msg)


@clanbattle_qq.sl.handle()
async def commit_sl(bot: Bot, event: GroupMessageEvent, state: T_State):
    proxy_report_uid: str = None
    uid = str(event.user_id)
    challenge_boss = int(state['_matched_groups'][1])
    comment = state['_matched_groups'][3]
    if not state['_matched_groups'][5]:
        uid = str(event.user_id)
    else:
        uid = state['_matched_groups'][5]
        proxy_report_uid = str(event.user_id)
    clan = clanbattle.get_clan_data(str(event.group_id))
    if not clan:
        await clanbattle_qq.sl.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    result = clan.commit_battle_sl(
        uid, challenge_boss, comment, proxy_report_uid)
    if result == CommitSLResult.success:
        await clanbattle_qq.sl.finish("sl已经记录")
    elif result == CommitSLResult.already_sl:
        await clanbattle_qq.sl.finish("您今天已经sl过了")
    elif result == CommitSLResult.illegal_target_boss:
        await clanbattle_qq.on_tree.finish("您还不能挑战这个boss，别sl了")
    elif result == CommitSLResult.member_not_in_clan:
        await clanbattle_qq.sl.finish("您还未加入公会，请发送“加入公会”加入")


@clanbattle_qq.unqueue.handle()
async def unqueue_boss(bot: Bot, event: GroupMessageEvent, state: T_State):
    uid = str(event.user_id)
    clan = clanbattle.get_clan_data(str(event.group_id))
    if not clan:
        await clanbattle_qq.unqueue.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    result = clan.delete_battle_in_progress(uid)
    if result:
        await clanbattle_qq.unsubscribe.finish("取消申请成功desu")
    else:
        await clanbattle_qq.unsubscribe.finish("取消申请失败，请确认您已经申请出刀该boss")


@clanbattle_qq.showqueue.handle()
async def show_queue(bot: Bot, event: GroupMessageEvent, state: T_State):
    clan = clanbattle.get_clan_data(str(event.group_id))
    if not clan:
        await clanbattle_qq.showqueue.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    progresses = clan.get_battle_in_progress()
    if not progresses:
        await clanbattle_qq.showqueue.finish("当前没有人申请出刀，赶快来出刀吧")
    else:
        msg = "当前正在出刀的成员："
        for i in range(1, 6):
            prog = clan.get_battle_in_progress(boss=i)
            if prog:
                msg += f"\n{i}王："
                for pro in prog:
                    msg += f" {clan.get_user_info(pro.member_uid).uname}"
        await clanbattle_qq.showqueue.finish(msg)


@clanbattle_qq.sl_query.handle()
async def query_sl(bot: Bot, event: GroupMessageEvent, state: T_State):
    uid = str(event.user_id)
    if not state['_matched_groups'][1]:
        uid = str(event.user_id)
    else:
        uid = state['_matched_groups'][1]
    clan = clanbattle.get_clan_data(str(event.group_id))
    if not clan:
        await clanbattle_qq.sl_query.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    sl = clan.get_today_battle_sl(uid=uid)
    if sl:
        await clanbattle_qq.sl_query.finish("您今天已经sl过了")
    else:
        await clanbattle_qq.sl_query.finish("您今天还没有使用过sl哦")


@clanbattle_qq.query_on_tree.handle()
async def query_on_tree(bot: Bot, event: GroupMessageEvent, state: T_State):
    clan = clanbattle.get_clan_data(str(event.group_id))
    if not clan:
        await clanbattle_qq.query_on_tree.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    on_tree_dict = {}
    for i in range(1, 6):
        on_tree_dict[i] = []
    on_tree_list = clan.get_battle_on_tree()
    for on_tree_item in on_tree_list:
        on_tree_dict[on_tree_item.target_boss].append(
            clan.get_user_name(on_tree_item.member_uid))
    msg = ""
    for i in range(1, 6):
        if on_tree_dict[i]:
            name_list = "".join(on_tree_dict[i])
            msg += f"当前{name_list}挂在{i}王上\n"
    if msg == "":
        msg = "当前没有人挂在树上哦"
    await clanbattle_qq.query_on_tree.finish(msg.strip())


@clanbattle_qq.reset_password.handle()
async def reset_password(bot: Bot, event: PrivateMessageEvent, state: T_State):
    uid = str(event.user_id)
    if user := ClanBattleData.get_user_info(uid):
        WebAuth.set_password(uid, state['_matched_groups'][0])
        await clanbattle_qq.reset_password.finish(
            f"密码已经重置为：{state['_matched_groups'][0]}，请前往网页端登录")
    else:
        await clanbattle_qq.reset_password.finish("不存在您的用户资料，请先加入一个公会")


@clanbattle_qq.leave_clan.handle()
async def leave_clan(bot: Bot, event: GroupMessageEvent, state: T_State):
    uid = str(event.user_id)
    clan = clanbattle.get_clan_data(str(event.group_id))
    if not clan:
        await clanbattle_qq.leave_clan.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    if clan.delete_clan_member(uid):
        await clanbattle_qq.leave_clan.finish("退出公会成功！")
    else:
        await clanbattle_qq.leave_clan.finish("退出公会失败，可能还没有加入公会？")


@clanbattle_qq.refresh_clan_admin.handle()
async def refresh_clan_admin(bot: Bot, event: GroupMessageEvent, state: T_State):
    gid = str(event.group_id)
    clan = clanbattle.get_clan_data(gid)
    if not clan:
        await clanbattle_qq.refresh_clan_admin.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    group_member_list = await bot.get_group_member_list(group_id=event.group_id)
    admin_list = []
    for member in group_member_list:
        if member["role"] in ["owner", "admin"] and member["user_id"] != int(bot.self_id):
            admin_list.append(str(member["user_id"]))
    clan.refresh_clan_admin(admin_list)
    await clanbattle_qq.refresh_clan_admin.finish("刷新管理员列表成功")


@clanbattle_qq.rename_clan.handle()
async def rename_clan(bot: Bot, event: GroupMessageEvent, state: T_State):
    gid = str(event.group_id)
    uid = str(event.user_id)
    clan = clanbattle.get_clan_data(gid)
    if not clan:
        await clanbattle_qq.rename_clan.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    if not clan.check_admin_permission(uid):
        await clanbattle_qq.rename_clan.finish("您不是会战管理员，无权使用本指令")
    else:
        clan.rename_clan(state['_matched_groups'][0])
        await clanbattle_qq.rename_clan.finish("修改公会名称成功")


@clanbattle_qq.remove_clan_member.handle()
async def remove_clan_member(bot: Bot, event: GroupMessageEvent, state: T_State):
    gid = str(event.group_id)
    uid = str(event.user_id)
    clan = clanbattle.get_clan_data(gid)
    if not clan:
        await clanbattle_qq.remove_clan_member.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    if not clan.check_admin_permission(uid):
        await clanbattle_qq.remove_clan_member.finish("您不是会战管理员，无权使用本指令")
    remove_uid = state['_matched_groups'][0]
    if clan.delete_clan_member(remove_uid):
        await clanbattle_qq.remove_clan_member.finish("成功将该成员移出公会")
    else:
        await clanbattle_qq.remove_clan_member.finish("移出公会失败，Ta可能还未加入公会？")


@clanbattle_qq.rename_clan_uname.handle()
async def rename_clan_uname(bot: Bot, event: GroupMessageEvent, state: T_State):
    gid = str(event.group_id)
    clan = clanbattle.get_clan_data(gid)
    if not clan:
        await clanbattle_qq.rename_clan_uname.finish("本群还未创建公会，发送“创建[台日]服公会”来创建公会")
    if not state['_matched_groups'][2]:
        uid = str(event.user_id)
    else:
        if not clan.check_admin_permission(str(event.user_id)):
            await clanbattle_qq.rename_clan_uname.finish("您不是会战管理员，无权修改他人昵称")
        uid = state['_matched_groups'][2]
    uname = state['_matched_groups'][0]
    if clan.rename_user_uname(uid, uname):
        await clanbattle_qq.remove_clan_member.finish("修改昵称成功")
    else:
        await clanbattle_qq.remove_clan_member.finish("修改昵称失败，可能用户还没加入任何公会？")


@clanbattle_qq.help.handle()
async def send_bot_help(bot: Bot, event: MessageEvent, state: T_State):
    if isinstance(event,GroupMessageEvent) or isinstance(event,PrivateMessageEvent):
        await clanbattle_qq.help.finish("Yuki Clanbattle Ver0.1.1\n会战帮助请见https://yukiclanbattle.shikeschedule.cn/help")


@clanbattle_qq.webview.handle()
async def send_webview(bot: Bot, event: MessageEvent, state: T_State):
    if isinstance(event,GroupMessageEvent) or isinstance(event,PrivateMessageEvent):
        await clanbattle_qq.webview.finish("登陆https://yukiclanbattle.shikeschedule.cn/clan查看详情")
