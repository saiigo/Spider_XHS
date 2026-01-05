#!/usr/bin/env python3
"""
CLI Entry Point for Spider XHS
用于Electron应用调用的命令行接口
"""
import sys
import json
import random
from typing import Dict, Any
from loguru import logger
from main import Data_Spider
from apis.xhs_pc_apis import XHS_Apis
from xhs_utils.common_util import init

# Cookie校验用的真实搜索关键词池(小红书常见热门搜索词)
VALIDATION_KEYWORDS = [
    "美食",
    "穿搭",
    "美妆",
    "旅行",
    "健身",
    "护肤",
    "摄影",
    "减肥",
    "家居",
    "宠物",
    "发型",
    "好物分享",
    "日常vlog",
    "读书",
    "手工",
]


def output_json(data: Dict[str, Any]):
    """统一的JSON输出函数,用于与Electron通信"""
    print(json.dumps(data, ensure_ascii=False))
    sys.stdout.flush()


def log_handler(message):
    """自定义日志处理器,将日志输出为JSON格式"""
    try:
        record = message.record
        # 确保 message 是可序列化的字符串
        msg_text = str(record["message"]) if record["message"] else ""
        output_json({
            "type": "log",
            "level": record["level"].name,
            "message": msg_text
        })
    except Exception as e:
        # 如果序列化失败，输出简化的错误信息
        try:
            output_json({
                "type": "log",
                "level": "ERROR",
                "message": f"Log serialization error: {str(e)}"
            })
        except:
            pass  # 最后的防护，避免死循环


def validate_cookie():
    """验证Cookie是否有效 - 通过搜索API验证"""
    try:
        if len(sys.argv) < 3:
            output_json({
                "type": "error",
                "code": "MISSING_COOKIE",
                "message": "Missing cookie parameter"
            })
            sys.exit(1)

        # Cookie 通过 JSON 传递
        cookie = json.loads(sys.argv[2])

        # 配置loguru
        logger.remove()
        logger.add(log_handler, format="{message}", level="DEBUG")

        # 初始化
        init()

        # 使用搜索API验证cookie有效性（搜索1个结果即可）
        # 随机选择一个真实搜索关键词,避免被检测为机器行为
        validation_keyword = random.choice(VALIDATION_KEYWORDS)
        spider = Data_Spider()
        success, msg, res_json = spider.xhs_apis.search_note(validation_keyword, cookie, page=1)

        # Check if message contains account anomaly keywords or error codes
        msg_str = str(msg) if msg else ""
        has_account_anomaly = (
            "账号异常" in msg_str or
            "检测到账号异常" in msg_str or
            "code=-1" in msg_str
        )

        if success and not has_account_anomaly:
            output_json({
                "type": "validation_result",
                "valid": True,
                "message": "Cookie有效",
                "userInfo": None
            })
        else:
            # If success but has account anomaly, or if not success
            error_msg = msg_str if msg_str and msg_str != "'msg'" else "Cookie无效或已过期"
            if has_account_anomaly:
                error_msg = "检测到账号异常，Cookie已失效"

            output_json({
                "type": "validation_result",
                "valid": False,
                "message": error_msg,
                "userInfo": None
            })

    except Exception as e:
        import traceback
        output_json({
            "type": "error",
            "code": "VALIDATION_ERROR",
            "message": f"{str(e)}\n{traceback.format_exc()}"
        })
        sys.exit(1)


def main():
    """主函数"""
    try:
        # 读取配置参数
        if len(sys.argv) < 2:
            output_json({
                "type": "error",
                "code": "MISSING_CONFIG",
                "message": "Missing configuration parameter"
            })
            sys.exit(1)

        config = json.loads(sys.argv[1])

        # 配置loguru输出到自定义handler
        logger.remove()  # 移除默认handler
        logger.add(log_handler, format="{message}", level="DEBUG")

        # 初始化
        init()

        # 提取配置参数
        cookie = config['cookie']
        task_type = config['taskType']
        params = config['params']
        save_options = config['saveOptions']
        paths = config['paths']
        proxy = config.get('proxy')
        request_interval = config.get('requestInterval')

        # 设置代理
        proxies = None
        if proxy:
            proxies = {
                'http': proxy,
                'https': proxy
            }

        # 输出开始信号
        output_json({
            "type": "log",
            "level": "INFO",
            "message": f"开始执行任务: {task_type}"
        })

        # 创建Spider实例
        spider = Data_Spider()

        # 根据taskType执行不同任务
        if task_type == 'notes':
            # 爬取指定笔记
            notes = params.get('notes', [])
            save_choice = save_options['mode']
            excel_name = save_options.get('excelName', '笔记数据')
            download = save_options.get('download', True)  # 新增：是否下载媒体文件，默认True

            output_json({
                "type": "progress",
                "current": 0,
                "total": len(notes),
                "message": f"准备爬取 {len(notes)} 条笔记"
            })

            spider.spider_some_note(
                notes=notes,
                cookies_str=cookie,
                base_path=paths,
                save_choice=save_choice,
                excel_name=excel_name,
                download=download,  # 新增：传递download参数
                proxies=proxies,
                request_interval=request_interval
            )

        elif task_type == 'user':
            # 爬取用户所有笔记
            user_url = params.get('userUrl', '')
            existing_note_ids = params.get('existingNoteIds', [])
            retry_note_urls = params.get('retryNoteUrls', [])
            save_choice = save_options['mode']
            excel_name = save_options.get('excelName', '用户笔记')
            download = save_options.get('download', True)  # 新增：是否下载媒体文件，默认True

            output_json({
                "type": "log",
                "level": "INFO",
                "message": f"开始爬取用户: {user_url}"
            })

            try:
                note_list, api_success, api_msg, user_profile, total_note_count = spider.spider_user_all_note(
                    user_url=user_url,
                    cookies_str=cookie,
                    base_path=paths,
                    save_choice=save_choice,
                    excel_name=excel_name,
                    download=download,  # 新增：传递download参数
                    proxies=proxies,
                    request_interval=request_interval,
                    existing_note_ids=existing_note_ids,
                    retry_note_urls=retry_note_urls
                )
            except Exception as e:
                api_success = False
                api_msg = str(e)
                note_list = []
                user_profile = None
                total_note_count = 0
                output_json({
                    "type": "log",
                    "level": "ERROR",
                    "message": f"爬取用户异常，已跳过当前博主: {api_msg}"
                })

            output_json({
                "type": "progress",
                "current": len(note_list),
                "total": total_note_count,
                "message": f"用户共有 {total_note_count} 条笔记"
            })

            # 输出完成信号，包含count和API返回的消息
            output_json({
                "type": "done",
                "success": True,
                "count": total_note_count,
                "api_success": api_success,
                "api_message": api_msg,
                "notes": note_list,
                "message": "任务完成",
                "user_info": user_profile
            })

        elif task_type == 'search':
            # 搜索关键词
            query = params.get('query', '')
            require_num = params.get('requireNum', 10)
            sort_type = params.get('sortType', 0)
            note_type = params.get('noteType', 0)
            note_time = params.get('noteTime', 0)
            note_range = params.get('noteRange', 0)
            pos_distance = params.get('posDistance', 0)
            geo = params.get('geo')
            save_choice = save_options['mode']
            excel_name = save_options.get('excelName', f'{query}_搜索结果')
            download = save_options.get('download', True)  # 新增：是否下载媒体文件，默认True

            output_json({
                "type": "log",
                "level": "INFO",
                "message": f"搜索关键词: {query}, 数量: {require_num}"
            })

            note_list, api_success, api_msg = spider.spider_some_search_note(
                query=query,
                require_num=require_num,
                cookies_str=cookie,
                base_path=paths,
                save_choice=save_choice,
                sort_type_choice=sort_type,
                note_type=note_type,
                note_time=note_time,
                note_range=note_range,
                pos_distance=pos_distance,
                geo=geo,
                excel_name=excel_name,
                download=download,  # 新增：传递download参数
                proxies=proxies,
                request_interval=request_interval
            )

            # 输出完成信号，包含count和API返回的消息
            output_json({
                "type": "done",
                "success": True,
                "count": len(note_list),
                "api_success": api_success,
                "api_message": api_msg,
                "message": "任务完成"
            })

        else:
            output_json({
                "type": "error",
                "code": "INVALID_TASK_TYPE",
                "message": f"Invalid task type: {task_type}"
            })
            sys.exit(1)

        # 注意: search和user任务已经在上面输出了done消息，这里不再输出
        if task_type not in ['search', 'user']:
            # 输出完成信号
            output_json({
                "type": "done",
                "success": True,
                "message": "任务完成"
            })

    except Exception as e:
        output_json({
            "type": "error",
            "code": "EXECUTION_ERROR",
            "message": str(e)
        })
        sys.exit(1)


if __name__ == '__main__':
    # 支持子命令: validate-cookie
    if len(sys.argv) >= 2 and sys.argv[1] == 'validate-cookie':
        validate_cookie()
    else:
        main()
