#!/usr/bin/env python3
"""
日志系统配置
"""

import logging
import logging.handlers
import os
import time
from typing import Optional


class LogManager:
    """日志管理器"""
    
    def __init__(self):
        self.log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
        os.makedirs(self.log_dir, exist_ok=True)
        self.loggers = {}
    
    def get_logger(self, name: str, level: int = logging.INFO) -> logging.Logger:
        """获取日志记录器"""
        if name not in self.loggers:
            logger = logging.getLogger(name)
            logger.setLevel(level)
            
            # 控制台输出
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)
            console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(console_formatter)
            
            # 文件输出
            log_file = os.path.join(self.log_dir, f'{name}_{time.strftime("%Y%m%d")}.log')
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5
            )
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(file_formatter)
            
            # 添加处理器
            logger.addHandler(console_handler)
            logger.addHandler(file_handler)
            
            self.loggers[name] = logger
        
        return self.loggers[name]


# 全局日志管理器
log_manager = LogManager()


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """获取日志记录器"""
    return log_manager.get_logger(name, level)


def log_info(logger: logging.Logger, message: str, **kwargs):
    """记录信息日志"""
    extra = kwargs if kwargs else {}
    logger.info(message, extra=extra)


def log_warning(logger: logging.Logger, message: str, **kwargs):
    """记录警告日志"""
    extra = kwargs if kwargs else {}
    logger.warning(message, extra=extra)


def log_error(logger: logging.Logger, message: str, exc_info: bool = False, **kwargs):
    """记录错误日志"""
    extra = kwargs if kwargs else {}
    logger.error(message, exc_info=exc_info, extra=extra)


def log_debug(logger: logging.Logger, message: str, **kwargs):
    """记录调试日志"""
    extra = kwargs if kwargs else {}
    logger.debug(message, extra=extra)
