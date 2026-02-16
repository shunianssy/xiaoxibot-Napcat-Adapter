"""
邮件发送模块
用于在Bot被踢下线时发送邮件通知
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List
from datetime import datetime
import threading

from src.logger import logger
from src.config import global_config


class EmailSender:
    """
    邮件发送器类
    支持异步发送邮件，避免阻塞主线程
    """
    
    _instance: Optional['EmailSender'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """
        单例模式，确保只有一个邮件发送器实例
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """
        初始化邮件发送器
        """
        self._initialized = False
        self._config = None
    
    def _init_config(self) -> bool:
        """
        初始化配置，延迟加载以避免循环导入
        :return: 配置是否有效
        """
        if self._initialized:
            return self._config is not None
        
        try:
            self._config = global_config.email_notify
            self._initialized = True
            
            # 检查配置是否完整
            if not self._config.enable:
                logger.debug("邮件通知功能未启用")
                return False
            
            if not self._config.smtp_user or not self._config.smtp_password:
                logger.warning("邮件通知配置不完整：缺少SMTP用户名或密码")
                return False
            
            if not self._config.receiver_emails:
                logger.warning("邮件通知配置不完整：未设置接收方邮箱")
                return False
            
            return True
        except Exception as e:
            logger.error(f"初始化邮件配置失败: {str(e)}")
            self._initialized = True
            return False
    
    def _get_smtp_connection(self) -> Optional[smtplib.SMTP]:
        """
        获取SMTP连接
        :return: SMTP连接对象，失败返回None
        """
        try:
            smtp_obj = smtplib.SMTP()
            smtp_obj.connect(self._config.smtp_server, self._config.smtp_port)
            smtp_obj.login(self._config.smtp_user, self._config.smtp_password)
            return smtp_obj
        except smtplib.SMTPConnectError as e:
            logger.error(f"SMTP连接失败: {str(e)}")
            return None
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP认证失败，请检查用户名和密码: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"SMTP连接异常: {str(e)}")
            return None
    
    def send_email(
        self,
        subject: str,
        content: str,
        html_content: Optional[str] = None,
        receivers: Optional[List[str]] = None
    ) -> bool:
        """
        发送邮件（同步方法）
        :param subject: 邮件主题
        :param content: 邮件纯文本内容
        :param html_content: 邮件HTML内容（可选）
        :param receivers: 接收方邮箱列表（可选，默认使用配置中的列表）
        :return: 是否发送成功
        """
        if not self._init_config():
            return False
        
        # 使用传入的接收方或配置中的接收方
        receiver_list = receivers or self._config.receiver_emails
        if not receiver_list:
            logger.warning("未指定邮件接收方")
            return False
        
        sender = self._config.sender_email or f"{self._config.smtp_user}@163.com"
        
        # 构建邮件
        try:
            if html_content:
                # 使用HTML格式
                message = MIMEMultipart('alternative')
                message.attach(MIMEText(content, 'plain', 'utf-8'))
                message.attach(MIMEText(html_content, 'html', 'utf-8'))
            else:
                # 纯文本格式
                message = MIMEText(content, 'plain', 'utf-8')
            
            message['Subject'] = subject
            message['From'] = sender
            message['To'] = ', '.join(receiver_list)
            
        except Exception as e:
            logger.error(f"构建邮件失败: {str(e)}")
            return False
        
        # 发送邮件
        smtp_obj = None
        try:
            smtp_obj = self._get_smtp_connection()
            if smtp_obj is None:
                return False
            
            smtp_obj.sendmail(sender, receiver_list, message.as_string())
            logger.success(f"邮件发送成功，主题: {subject}，接收方: {receiver_list}")
            return True
            
        except smtplib.SMTPException as e:
            logger.error(f"邮件发送失败: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"邮件发送异常: {str(e)}")
            return False
        finally:
            if smtp_obj:
                try:
                    smtp_obj.quit()
                except Exception:
                    pass
    
    def send_email_async(
        self,
        subject: str,
        content: str,
        html_content: Optional[str] = None,
        receivers: Optional[List[str]] = None
    ) -> None:
        """
        异步发送邮件（在新线程中发送，不阻塞主线程）
        :param subject: 邮件主题
        :param content: 邮件纯文本内容
        :param html_content: 邮件HTML内容（可选）
        :param receivers: 接收方邮箱列表（可选）
        """
        thread = threading.Thread(
            target=self.send_email,
            args=(subject, content, html_content, receivers),
            daemon=True
        )
        thread.start()
    
    def send_kicked_offline_notify(
        self,
        bot_id: int,
        reason: str = "未知原因"
    ) -> bool:
        """
        发送Bot被踢下线通知邮件
        :param bot_id: Bot的QQ号
        :param reason: 下线原因
        :return: 是否发送成功
        """
        logger.info(f"准备发送被踢下线邮件通知: Bot={bot_id}, 原因={reason}")
        
        if not self._init_config():
            logger.warning("邮件配置初始化失败，跳过发送")
            return False
        
        logger.info(f"邮件通知已启用，准备发送到: {self._config.receiver_emails}")
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        subject = f"【紧急】QQ Bot {bot_id} 被踢下线通知"
        
        text_content = f"""
QQ Bot 被踢下线通知

Bot QQ号: {bot_id}
下线时间: {current_time}
下线原因: {reason}

请及时检查Bot状态！
"""
        
        html_content = f"""
<html>
    <body>
        <h2 style="color: red;">🔴 QQ Bot 被踢下线通知</h2>
        <hr>
        <table style="border-collapse: collapse;">
            <tr>
                <td style="padding: 8px; font-weight: bold;">Bot QQ号:</td>
                <td style="padding: 8px;">{bot_id}</td>
            </tr>
            <tr>
                <td style="padding: 8px; font-weight: bold;">下线时间:</td>
                <td style="padding: 8px;">{current_time}</td>
            </tr>
            <tr>
                <td style="padding: 8px; font-weight: bold;">下线原因:</td>
                <td style="padding: 8px;">{reason}</td>
            </tr>
        </table>
        <hr>
        <p style="color: red; font-weight: bold;">⚠️ 请及时检查Bot状态！</p>
    </body>
</html>
"""
        
        result = self.send_email(subject, text_content, html_content)
        if result:
            logger.success("被踢下线邮件通知发送成功")
        else:
            logger.error("被踢下线邮件通知发送失败")
        return result


# 全局邮件发送器实例
email_sender = EmailSender()


# 向后兼容的函数接口
def email(user: str, content: str, subject: str) -> bool:
    """
    发送邮件（向后兼容接口）
    :param user: 接收方邮箱
    :param content: 邮件内容
    :param subject: 邮件主题
    :return: 是否发送成功
    """
    return email_sender.send_email(subject, content, receivers=[user])
