import json
import os
import random
import time
import urllib.parse
from loguru import logger
from apis.xhs_pc_apis import XHS_Apis
from xhs_utils.common_util import init
from xhs_utils.data_util import handle_note_info, handle_user_info, download_note, save_to_xlsx, timestamp_to_str


class Data_Spider():
    def __init__(self):
        self.xhs_apis = XHS_Apis()
        self.failed_note_count = 0
        self.retry_round = 0
        self.stop_user_task = False

    def _format_simple_note_info(self, note_info: dict, note_url: str):
        if not isinstance(note_info, dict):
            return None

        note_id = note_info.get('note_id') or note_info.get('id')
        note_type = note_info.get('type') or note_info.get('note_type')
        if note_type == 'normal':
            note_type = '图集'
        elif note_type == 'video':
            note_type = '视频'
        elif note_type is None:
            note_type = ''

        user = note_info.get('user') or {}
        user_id = user.get('user_id') or note_info.get('user_id', '')
        home_url = f'https://www.xiaohongshu.com/user/profile/{user_id}' if user_id else ''
        nickname = user.get('nickname') or user.get('nick_name') or note_info.get('nickname', '')
        avatar = user.get('avatar') or note_info.get('avatar', '')

        title = note_info.get('display_title') or note_info.get('title') or ''
        desc = note_info.get('desc') or ''

        interact_info = note_info.get('interact_info') or {}
        liked_count = interact_info.get('liked_count') or note_info.get('liked_count', '')
        collected_count = interact_info.get('collected_count') or note_info.get('collected_count', '')
        comment_count = interact_info.get('comment_count') or note_info.get('comment_count', '')
        share_count = interact_info.get('share_count') or note_info.get('share_count', '')

        cover_info = note_info.get('cover') or {}
        image_url = cover_info.get('url_default') or cover_info.get('url_pre') or ''
        if not image_url:
            info_list = cover_info.get('info_list') or []
            if info_list:
                image_url = info_list[0].get('url') if isinstance(info_list[0], dict) else ''
        image_list = [image_url] if image_url else []

        tags = []
        for tag in note_info.get('tag_list') or []:
            if isinstance(tag, dict) and tag.get('name'):
                tags.append(tag['name'])
        upload_time = ''
        time_value = note_info.get('time') or note_info.get('publish_time')
        if isinstance(time_value, (int, float)):
            upload_time = timestamp_to_str(time_value)
        elif isinstance(time_value, str):
            upload_time = time_value

        crawl_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        return {
            'note_id': note_id or '',
            'note_url': note_url,
            'note_type': note_type,
            'user_id': user_id,
            'home_url': home_url,
            'nickname': nickname,
            'avatar': avatar,
            'title': title,
            'desc': desc,
            'liked_count': liked_count,
            'collected_count': collected_count,
            'comment_count': comment_count,
            'share_count': share_count,
            'video_cover': image_url if note_type == '视频' else None,
            'video_addr': None,
            'image_list': image_list,
            'tags': tags,
            'upload_time': upload_time,
            'ip_location': note_info.get('ip_location', ''),
            'crawl_time': crawl_time,
        }

    def spider_note(self, note_url: str, cookies_str: str, proxies=None, request_interval=None):
        """
        爬取一个笔记的信息
        :param note_url:
        :param cookies_str:
        :return:
        """
        note_info = None
        try:
            success, msg, note_info = self.xhs_apis.get_note_info(note_url, cookies_str, proxies, request_interval)
            if success and note_info and isinstance(note_info, dict) and 'data' in note_info and 'items' in note_info['data'] and note_info['data']['items']:
                note_info = note_info['data']['items'][0]
                note_info['url'] = note_url
                note_info = handle_note_info(note_info)
            else:
                success = False
                msg = 'items' if success else msg
        except Exception as e:
            success = False
            msg = str(e)
        logger.info(f'爬取笔记信息 {note_url}: {success}, msg: {msg}')
        return success, msg, note_info

    def spider_some_note(self, notes: list, cookies_str: str, base_path: dict, save_choice: str, excel_name: str = '', download: bool = True, proxies=None, request_interval=None, user_profile=None, fallback_notes=None):
        """
        爬取一些笔记的信息
        :param notes:
        :param cookies_str:
        :param base_path:
        :return: 爬取的笔记列表
        """
        if save_choice in ['all', 'excel'] and excel_name == '':
            raise ValueError('excel_name 不能为空')
        note_list = []
        for note_url in notes:
            if self.stop_user_task:
                break
            success, msg, note_info = self.spider_note(note_url, cookies_str, proxies, request_interval)
            if note_info is not None and success:
                self.failed_note_count = 0
                note_list.append(note_info)
                continue
            # 笔记详情获取失败，无论是否使用fallback_notes，都增加失败计数
            self.failed_note_count += 1
            
            if fallback_notes and note_url in fallback_notes and fallback_notes[note_url]:
                # 使用了fallback_notes，添加基础信息
                fallback_note = fallback_notes[note_url]
                logger.warning(f'笔记详情获取失败，使用基础信息: {note_url} (原因: {msg})')
                note_list.append(fallback_note)
            
            if self.failed_note_count >= 3:
                if self.retry_round == 0:
                    wait_seconds = random.uniform(30, 40)
                    logger.warning(f'笔记详情失败次数达到3次，等待 {wait_seconds:.2f} 秒后重试')
                    time.sleep(wait_seconds)
                    self.retry_round = 1
                    self.failed_note_count = 0
                else:
                    logger.warning('笔记详情失败次数达到6次，提前结束当前博主任务')
                    self.stop_user_task = True
                    break
        for note_info in note_list:
            if download and (save_choice == 'all' or 'media' in save_choice):
                download_note(note_info, base_path['media'], save_choice)
        if save_choice in ['all', 'excel']:
            file_path = os.path.abspath(os.path.join(base_path['excel'], f'{excel_name}.xlsx'))

            workbook = None
            if user_profile:
                try:
                    workbook = save_to_xlsx([], file_path, type='user', user_info=user_profile)
                except Exception as e:
                    logger.warning(f'记录用户信息失败: {e}')

            save_to_xlsx(note_list, file_path, sheet_name=excel_name, existing_workbook=workbook)

        return note_list


    def spider_user_all_note(self, user_url: str, cookies_str: str, base_path: dict, save_choice: str, excel_name: str = '', download: bool = True, proxies=None, request_interval=None, existing_note_ids=None):
        """
        爬取一个用户的所有笔记
        :param user_url:
        :param cookies_str:
        :param base_path:
        :return:
        """
        api_success = True
        api_msg = ''
        detailed_notes = []
        user_profile = None
        parsed_user_id = ''
        total_note_count = 0
        existing_note_ids = {str(note_id) for note_id in existing_note_ids} if existing_note_ids else set()
        self.failed_note_count = 0
        self.retry_round = 0
        self.stop_user_task = False
        try:
            parsed_user_id = user_url.split('/')[-1].split('?')[0]
            success_user, msg_user, user_detail = self.xhs_apis.get_user_info(parsed_user_id, cookies_str, proxies, request_interval)
            if success_user and user_detail and user_detail.get('data'):
                user_profile = handle_user_info(user_detail['data'], parsed_user_id)
            else:
                logger.warning(f'获取用户信息失败: {msg_user}')
        except Exception as e:
            logger.warning(f'获取用户信息异常: {e}')

        try:
            url_parse = urllib.parse.urlparse(user_url)
            path_parts = url_parse.path.split("/")
            if len(path_parts) >= 4 and path_parts[-2] == 'profile':
                user_id = path_parts[-1]
            else:
                user_id = url_parse.path.split("/")[-1]

            kvs = url_parse.query.split('&') if url_parse.query else []
            kv_dist = {kv.split('=')[0]: kv.split('=')[1] for kv in kvs if '=' in kv}
            xsec_token = kv_dist.get('xsec_token', '')
            xsec_source = kv_dist.get('xsec_source', 'pc_search')

            if save_choice in ['all', 'excel'] and not excel_name:
                excel_name = user_url.split('/')[-1].split('?')[0]

            cursor = ''
            is_first_request = True
            while True:
                success, msg, res_json = self.xhs_apis.get_user_note_info(
                    user_id,
                    cursor,
                    cookies_str,
                    xsec_token,
                    xsec_source,
                    proxies,
                    request_interval,
                    skip_delay=is_first_request
                )
                is_first_request = False
                api_success = success
                api_msg = msg
                if not success:
                    raise Exception(msg)

                notes = res_json.get('data', {}).get('notes', [])
                
                # 记录分页笔记数量，用于最后统计笔记总数
                total_note_count += len(notes)
                if not notes:
                    break

                # 比较note_id去重，得到需要获取详情的笔记列表
                note_urls = []
                fallback_notes = {}
                for simple_note_info in notes:
                    note_id = str(simple_note_info.get('note_id') or simple_note_info.get('id') or '')
                    if not note_id:
                        continue
                    if note_id in existing_note_ids:
                        continue
                    existing_note_ids.add(note_id)
                    xsec_token_item = simple_note_info.get('xsec_token', '')
                    note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token_item}"
                    note_urls.append(note_url)
                    fallback_notes[note_url] = self._format_simple_note_info(simple_note_info, note_url)

                # 获取需要获取详情的笔记列表
                if note_urls:
                    # 获取笔记详情
                    page_notes = self.spider_some_note(
                        note_urls,
                        cookies_str,
                        base_path,
                        'none',
                        excel_name,
                        download,
                        proxies,
                        request_interval,
                        user_profile=user_profile,
                        fallback_notes=fallback_notes
                    )
                    
                    # 记录增量笔记详情列表
                    if page_notes:
                        # 下载媒体文件（如果需要）
                        if download and (save_choice == 'all' or 'media' in save_choice):
                            for note_info in page_notes:
                                download_note(note_info, base_path['media'], save_choice)
                        # 添加到增量笔记详情列表
                        detailed_notes.extend(page_notes)

                if self.stop_user_task:
                    api_success = False
                    api_msg = '笔记详情失败次数达到6次，提前结束当前博主任务'
                    logger.warning('已跳过当前博主，准备处理下一个博主')
                    break

                # 继续处理下一页
                if 'cursor' in res_json.get('data', {}):
                    cursor = str(res_json['data']['cursor'])
                else:
                    break

                if not res_json['data'].get('has_more'):
                    break
        except Exception as e:
            success = False
            msg = str(e)
        if save_choice in ['all', 'excel'] and detailed_notes:
            file_path = os.path.abspath(os.path.join(base_path['excel'], f'{excel_name}.xlsx'))

            workbook = None
            if user_profile:
                try:
                    workbook = save_to_xlsx([], file_path, type='user', user_info=user_profile)
                except Exception as e:
                    logger.warning(f'记录用户信息失败: {e}')

            save_to_xlsx(detailed_notes, file_path, sheet_name=excel_name, existing_workbook=workbook)
        logger.info(f'爬取用户所有视频 {user_url}: {success}, msg: {msg}')
        return detailed_notes, api_success, api_msg, user_profile, total_note_count

    def spider_some_search_note(self, query: str, require_num: int, cookies_str: str, base_path: dict, save_choice: str, sort_type_choice=0, note_type=0, note_time=0, note_range=0, pos_distance=0, geo: dict = None,  excel_name: str = '', download: bool = True, proxies=None, request_interval=None):
        """
            指定数量搜索笔记，设置排序方式和笔记类型和笔记数量
            :param query 搜索的关键词
            :param require_num 搜索的数量
            :param cookies_str 你的cookies
            :param base_path 保存路径
            :param sort_type_choice 排序方式 0 综合排序, 1 最新, 2 最多点赞, 3 最多评论, 4 最多收藏
            :param note_type 笔记类型 0 不限, 1 视频笔记, 2 普通笔记
            :param note_time 笔记时间 0 不限, 1 一天内, 2 一周内天, 3 半年内
            :param note_range 笔记范围 0 不限, 1 已看过, 2 未看过, 3 已关注
            :param pos_distance 位置距离 0 不限, 1 同城, 2 附近 指定这个必须要指定 geo
            返回搜索的结果
        """
        note_list = []
        api_success = True
        api_msg = ''
        try:
            success, msg, notes = self.xhs_apis.search_some_note(query, require_num, cookies_str, sort_type_choice, note_type, note_time, note_range, pos_distance, geo, proxies, request_interval)
            api_success = success
            api_msg = msg
            if success:
                notes = list(filter(lambda x: x['model_type'] == "note", notes))
                logger.info(f'搜索关键词 {query} 笔记数量: {len(notes)}')
                for note in notes:
                    note_url = f"https://www.xiaohongshu.com/explore/{note['id']}?xsec_token={note['xsec_token']}"
                    note_list.append(note_url)
            if save_choice == 'all' or save_choice == 'excel':
                excel_name = query
            self.spider_some_note(note_list, cookies_str, base_path, save_choice, excel_name, download, proxies, request_interval)
        except Exception as e:
            success = False
            msg = str(e)
        logger.info(f'搜索关键词 {query} 笔记: {success}, msg: {msg}')
        return note_list, api_success, api_msg

if __name__ == '__main__':
    """
        此文件为爬虫的入口文件，可以直接运行
        apis/xhs_pc_apis.py 为爬虫的api文件，包含小红书的全部数据接口，可以继续封装
        apis/xhs_creator_apis.py 为小红书创作者中心的api文件
        感谢star和follow
    """

    cookies_str, base_path = init()
    data_spider = Data_Spider()
    """
        save_choice: all: 保存所有的信息, media: 保存视频和图片（media-video只下载视频, media-image只下载图片，media都下载）, excel: 保存到excel
        save_choice 为 excel 或者 all 时，excel_name 不能为空
    """


    # # 1 爬取列表的所有笔记信息 笔记链接 如下所示 注意此url会过期！
    # notes = [
    #     r'https://www.xiaohongshu.com/explore/683fe17f0000000023017c6a?xsec_token=ABBr_cMzallQeLyKSRdPk9fwzA0torkbT_ubuQP1ayvKA=&xsec_source=pc_user',
    # ]
    # data_spider.spider_some_note(notes, cookies_str, base_path, 'all', 'test')

    # 2 爬取用户的所有笔记信息 用户链接 如下所示 注意此url会过期！
    # user_url = 'https://www.xiaohongshu.com/user/profile/64c3f392000000002b009e45?xsec_token=AB-GhAToFu07JwNk_AMICHnp7bSTjVz2beVIDBwSyPwvM=&xsec_source=pc_feed'
    cookies_str="abRequestId=f645612f-a002-55ae-b5b0-4b027eacfbfa; xsecappid=xhs-pc-web; a1=19b2a34f49aadyxfdhh5yc1b9s7vf7fgs6bsld3tu30000269714; webId=7e4744962b59508d494aa59d3b82e6e4; gid=yjDJ0q28q0MqyjDJ0q4i4Kfqj00fvCifxx2vD97SyDjMWMq8hiWik1888JKjWy48fYjWdy4D; webBuild=5.0.7; loadts=1765993228297; websectiga=2845367ec3848418062e761c09db7caf0e8b79d132ccdd1a4f8e64a11d0cac0d; sec_poison_id=b14620cb-79b4-48d1-aeb7-47f7d042cf46; web_session=040069b4422e845faf0e5aa4773b4b479e024b"
    
    user_url = 'https://www.xiaohongshu.com/user/profile/59f8405811be103c5b76f21a?xsec_token=ABMeX4Jz7dFHuPYKJJxRpujwaWzh6WC5LTkbfes3h0PcQ=&xsec_source=pc_search'
    data_spider.spider_user_all_note(user_url, cookies_str, base_path, 'excel')

    # 3 搜索指定关键词的笔记
    query = "榴莲"
    query_num = 10
    sort_type_choice = 0  # 0 综合排序, 1 最新, 2 最多点赞, 3 最多评论, 4 最多收藏
    note_type = 0 # 0 不限, 1 视频笔记, 2 普通笔记
    note_time = 0  # 0 不限, 1 一天内, 2 一周内天, 3 半年内
    note_range = 0  # 0 不限, 1 已看过, 2 未看过, 3 已关注
    pos_distance = 0  # 0 不限, 1 同城, 2 附近 指定这个1或2必须要指定 geo
    # geo = {
    #     # 经纬度
    #     "latitude": 39.9725,
    #     "longitude": 116.4207
    # }
    data_spider.spider_some_search_note(query, query_num, cookies_str, base_path, 'all', sort_type_choice, note_type, note_time, note_range, pos_distance, geo=None)
