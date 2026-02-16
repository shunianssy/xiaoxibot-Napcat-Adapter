from src.logger import logger
from src.config import global_config
import time
import asyncio

from . import MetaEventType
from email_send import email_sender


class MetaEventHandler:
    """
    处理Meta事件
    """

    def __init__(self):
        self.interval = global_config.napcat_server.heartbeat_interval
        self._interval_checking = False
        # 防止重复发送下线通知邮件的标志位
        self._offline_notified = False

    async def handle_meta_event(self, message: dict) -> None:
        event_type = message.get("meta_event_type")
        if event_type == MetaEventType.lifecycle:
            sub_type = message.get("sub_type")
            if sub_type == MetaEventType.Lifecycle.connect:
                self_id = message.get("self_id")
                self.last_heart_beat = time.time()
                logger.success(f"Bot {self_id} 连接成功")
                # 连接成功时重置下线通知标志
                self._offline_notified = False
                asyncio.create_task(self.check_heartbeat(self_id))
        elif event_type == MetaEventType.heartbeat:
            self_id = message.get("self_id")
            status = message.get("status", {})
            is_online = status.get("online", False)
            is_good = status.get("good", False)
            
            if is_online and is_good:
                # 正常心跳
                if not self._interval_checking:
                    asyncio.create_task(self.check_heartbeat(self_id))
                self.last_heart_beat = time.time()
                self.interval = message.get("interval", 30000) / 1000
                # 恢复在线时重置下线通知标志
                self._offline_notified = False
            else:
                # Bot 离线或状态异常
                reason = "未知原因"
                if not is_online:
                    logger.error(f"🔴 Bot {self_id} 已下线 (online=false)")
                    logger.warning("Bot 可能被踢下线、网络断开或主动退出登录")
                    reason = "Bot已下线 (online=false)，可能被踢下线、网络断开或主动退出登录"
                elif not is_good:
                    logger.warning(f"⚠️ Bot {self_id} 状态异常 (good=false)")
                    reason = "Bot状态异常 (good=false)"
                else:
                    logger.warning(f"Bot {self_id} Napcat 端异常！")
                    reason = "Napcat端异常"
                
                # 发送邮件通知（防止重复发送）
                if not self._offline_notified:
                    self._offline_notified = True
                    # 在新线程中发送邮件，避免阻塞
                    email_sender.send_kicked_offline_notify(self_id, reason)

    async def check_heartbeat(self, id: int) -> None:
        self._interval_checking = True
        while True:
            now_time = time.time()
            if now_time - self.last_heart_beat > self.interval * 2:
                logger.error(f"Bot {id} 可能发生了连接断开，被下线，或者Napcat卡死！")
                # 发送邮件通知（防止重复发送）
                if not self._offline_notified:
                    self._offline_notified = True
                    reason = "心跳超时，可能发生了连接断开、被踢下线或Napcat卡死"
                    email_sender.send_kicked_offline_notify(id, reason)
                break
            else:
                logger.debug("心跳正常")
            await asyncio.sleep(self.interval)


meta_event_handler = MetaEventHandler()
