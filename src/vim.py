"""
Vim 模式编辑功能 — 照搬 Claude Code 设计
====================================
核心功能：
- Vim 编辑器模式支持
- 模式切换（INSERT/NORMAL）
- 标准 Vim 键位映射
- 与系统配置集成
"""

from typing import Dict, Any


# ============================================================================# Vim 模式管理器# ============================================================================

class VimModeManager:
    """
    Vim 模式管理器
    功能：
    1. 管理编辑器模式（normal/vim）
    2. 处理 Vim 键位映射
    3. 提供模式切换功能
    """
    
    def __init__(self, config):
        """初始化 Vim 模式管理器"""
        self.config = config
        self.current_mode = config.editor_mode
        self.vim_state = {
            'mode': 'INSERT',  # INSERT 或 NORMAL
            'key_mappings': {
                # 基本 Vim 命令
                'h': 'move_left',
                'j': 'move_down',
                'k': 'move_up',
                'l': 'move_right',
                'w': 'move_word_forward',
                'b': 'move_word_backward',
                '0': 'move_to_start',
                '$': 'move_to_end',
                'i': 'insert_mode',
                'a': 'append_mode',
                'o': 'open_line_below',
                'O': 'open_line_above',
                'dd': 'delete_line',
                'yy': 'yank_line',
                'p': 'paste_after',
                'P': 'paste_before',
                'u': 'undo',
                'Ctrl-r': 'redo',
                '/': 'search_forward',
                'n': 'search_next',
                'N': 'search_previous',
                ':%s/old/new/g': 'replace_all',
                'wq': 'write_quit',
                'q!': 'quit_without_saving'
            }
        }
    
    def toggle_editor_mode(self) -> str:
        """切换编辑器模式"""
        if self.current_mode == 'normal':
            self.current_mode = 'vim'
            self.config.editor_mode = 'vim'
        else:
            self.current_mode = 'normal'
            self.config.editor_mode = 'normal'
        
        return self.current_mode
    
    def toggle_vim_mode(self) -> str:
        """切换 Vim 内部模式（INSERT/NORMAL）"""
        if self.vim_state['mode'] == 'INSERT':
            self.vim_state['mode'] = 'NORMAL'
        else:
            self.vim_state['mode'] = 'INSERT'
        
        return self.vim_state['mode']
    
    def get_current_mode(self) -> str:
        """获取当前编辑器模式"""
        return self.current_mode
    
    def get_vim_state(self) -> Dict[str, Any]:
        """获取 Vim 状态"""
        return self.vim_state
    
    def handle_key(self, key: str) -> Dict[str, Any]:
        """处理按键输入"""
        if self.current_mode != 'vim':
            return {'action': 'pass_through', 'key': key}
        
        # 处理 Escape 键
        if key == 'Escape':
            new_mode = self.toggle_vim_mode()
            return {'action': 'mode_change', 'mode': new_mode}
        
        # 处理 Vim 命令
        if self.vim_state['mode'] == 'NORMAL':
            if key in self.vim_state['key_mappings']:
                action = self.vim_state['key_mappings'][key]
                return {'action': action}
            elif key == 'i':
                self.vim_state['mode'] = 'INSERT'
                return {'action': 'mode_change', 'mode': 'INSERT'}
        
        # 默认行为
        return {'action': 'pass_through', 'key': key}
    
    def get_status_message(self) -> str:
        """获取状态消息"""
        if self.current_mode == 'vim':
            return f"Editor mode: vim ({self.vim_state['mode']} mode)"
        else:
            return "Editor mode: normal"
    
    def get_help(self) -> str:
        """获取帮助信息"""
        help_text = """
Vim 模式帮助:

基本操作:
  Escape    - 切换 INSERT/NORMAL 模式
  i         - 进入 INSERT 模式
  h/j/k/l   - 移动光标（左/下/上/右）
  w         - 向前移动一个词
  b         - 向后移动一个词
  0         - 移动到行首
  $         - 移动到行尾
  dd        - 删除当前行
  yy        - 复制当前行
  p         - 在光标后粘贴
  P         - 在光标前粘贴
  u         - 撤销
  Ctrl-r    - 重做
  /         - 向前搜索
  n         - 下一个搜索结果
  N         - 上一个搜索结果
  :wq       - 保存并退出
  :q!       - 不保存退出

提示:
  - 使用 :vim 命令切换编辑器模式
  - 在 NORMAL 模式下输入命令
  - 在 INSERT 模式下输入文本
        """
        return help_text


# ============================================================================# 便捷函数# ============================================================================

def create_vim_manager(config) -> VimModeManager:
    """创建 Vim 模式管理器"""
    return VimModeManager(config)

def toggle_editor_mode(config) -> str:
    """切换编辑器模式"""
    manager = create_vim_manager(config)
    new_mode = manager.toggle_editor_mode()
    
    if new_mode == 'vim':
        return f"Editor mode set to {new_mode}. Use Escape key to toggle between INSERT and NORMAL modes."
    else:
        return f"Editor mode set to {new_mode}. Using standard keyboard bindings."


# 为了兼容性，创建别名
VimMode = VimModeManager
