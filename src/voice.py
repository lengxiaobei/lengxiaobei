"""
Voice 语音功能 — 照搬 Claude Code 设计
====================================
核心功能：
- 多模态交互
- 语音输入输出能力
- 麦克风权限管理
- 跨平台支持
- 语音转文本和文本转语音
"""

import os
import subprocess
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, Callable


# ============================================================================# 常量定义# ============================================================================

RECORDING_SAMPLE_RATE = 16000
RECORDING_CHANNELS = 1
SILENCE_DURATION_SECS = '2.0'
SILENCE_THRESHOLD = '3%'


# ============================================================================# 依赖检查# ============================================================================

def has_command(cmd: str) -> bool:
    """检查命令是否存在"""
    try:
        result = subprocess.run(
            [cmd, '--version'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False

def detect_package_manager() -> Optional[Dict[str, str]]:
    """检测包管理器"""
    if os.name == 'posix':
        if has_command('brew'):
            return {
                'cmd': 'brew',
                'args': 'install sox',
                'display_command': 'brew install sox'
            }
        elif has_command('apt-get'):
            return {
                'cmd': 'sudo',
                'args': 'apt-get install -y sox',
                'display_command': 'sudo apt-get install sox'
            }
        elif has_command('dnf'):
            return {
                'cmd': 'sudo',
                'args': 'dnf install -y sox',
                'display_command': 'sudo dnf install sox'
            }
        elif has_command('pacman'):
            return {
                'cmd': 'sudo',
                'args': 'pacman -S --noconfirm sox',
                'display_command': 'sudo pacman -S sox'
            }
    return None


# ============================================================================# 语音服务# ============================================================================

class VoiceService:
    """
    语音服务
    功能：
    1. 音频录制
    2. 语音转文本
    3. 文本转语音
    4. 麦克风权限管理
    """
    
    def __init__(self):
        """初始化语音服务"""
        self.active_recorder = None
        self.native_recording_active = False
        self.pyaudio = None
        self.stream = None
        self.speech_recognition = None
        self.pyttsx3 = None
        
        # 尝试导入依赖
        self._try_import_dependencies()
    
    def _try_import_dependencies(self):
        """尝试导入依赖"""
        try:
            import pyaudio
            self.pyaudio = pyaudio
        except ImportError:
            pass
        
        try:
            import speech_recognition
            self.speech_recognition = speech_recognition
        except ImportError:
            pass
        
        try:
            import pyttsx3
            self.pyttsx3 = pyttsx3
        except ImportError:
            pass
    
    async def check_voice_dependencies(self) -> Dict[str, Any]:
        """检查语音依赖"""
        missing = []
        
        # 检查录音依赖
        if self.pyaudio:
            # 有pyaudio，使用它
            pass
        elif has_command('arecord'):
            # Linux，使用arecord
            pass
        elif has_command('rec'):
            # 有sox，使用rec
            pass
        else:
            missing.append('录音工具 (pyaudio 或 sox)')
        
        # 检查语音转文本依赖
        if not self.speech_recognition:
            missing.append('speech_recognition 库')
        
        # 检查文本转语音依赖
        if not self.pyttsx3:
            missing.append('pyttsx3 库')
        
        pm = detect_package_manager() if missing else None
        
        return {
            'available': len(missing) == 0,
            'missing': missing,
            'install_command': pm['display_command'] if pm else None
        }
    
    async def check_recording_availability(self) -> Dict[str, Any]:
        """检查录音可用性"""
        # 检查环境
        if os.environ.get('CLAUDE_CODE_REMOTE'):
            return {
                'available': False,
                'reason': 'Voice mode requires microphone access, but no audio device is available in this environment.'
            }
        
        # 检查依赖
        dependencies = await self.check_voice_dependencies()
        if not dependencies['available']:
            missing_deps = ', '.join(dependencies['missing'])
            return {
                'available': False,
                'reason': f'Missing dependencies: {missing_deps}'
            }
        
        # 检查麦克风权限
        if self.pyaudio:
            try:
                p = self.pyaudio.PyAudio()
                stream = p.open(
                    format=self.pyaudio.paInt16,
                    channels=RECORDING_CHANNELS,
                    rate=RECORDING_SAMPLE_RATE,
                    input=True,
                    frames_per_buffer=1024
                )
                stream.close()
                p.terminate()
            except Exception as e:
                return {
                    'available': False,
                    'reason': f'Could not access microphone: {e}'
                }
        
        return {
            'available': True,
            'reason': None
        }
    
    async def start_recording(
        self,
        on_data: Callable[[bytes], None],
        on_end: Callable[[], None],
        options: Optional[Dict[str, Any]] = None
    ) -> bool:
        """开始录音"""
        options = options or {}
        use_silence_detection = options.get('silence_detection', True)
        
        # 尝试使用pyaudio
        if self.pyaudio:
            try:
                p = self.pyaudio.PyAudio()
                self.stream = p.open(
                    format=self.pyaudio.paInt16,
                    channels=RECORDING_CHANNELS,
                    rate=RECORDING_SAMPLE_RATE,
                    input=True,
                    frames_per_buffer=1024,
                    stream_callback=lambda in_data, frame_count, time_info, status:
                        (None, self.pyaudio.paComplete) if self.native_recording_active else (on_data(in_data), self.pyaudio.paContinue)
                )
                self.stream.start_stream()
                self.native_recording_active = True
                return True
            except Exception as e:
                print(f"[Voice] PyAudio recording failed: {e}")
        
        # 尝试使用arecord (Linux)
        if os.name == 'posix' and has_command('arecord'):
            try:
                args = [
                    'arecord',
                    '-f', 'S16_LE',
                    '-r', str(RECORDING_SAMPLE_RATE),
                    '-c', str(RECORDING_CHANNELS),
                    '-t', 'raw',
                    '-q',
                    '-'
                ]
                self.active_recorder = subprocess.Popen(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                async def read_from_process():
                    while self.active_recorder and self.active_recorder.poll() is None:
                        data = self.active_recorder.stdout.read(1024)
                        if data:
                            on_data(data)
                    on_end()
                
                asyncio.create_task(read_from_process())
                return True
            except Exception as e:
                print(f"[Voice] arecord recording failed: {e}")
        
        # 尝试使用sox rec
        if has_command('rec'):
            try:
                args = [
                    'rec',
                    '-q',
                    '--buffer', '1024',
                    '-t', 'raw',
                    '-r', str(RECORDING_SAMPLE_RATE),
                    '-e', 'signed',
                    '-b', '16',
                    '-c', str(RECORDING_CHANNELS),
                    '-'
                ]
                
                if use_silence_detection:
                    args.extend([
                        'silence',
                        '1', '0.1', SILENCE_THRESHOLD,
                        '1', SILENCE_DURATION_SECS, SILENCE_THRESHOLD
                    ])
                
                self.active_recorder = subprocess.Popen(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                async def read_from_process():
                    while self.active_recorder and self.active_recorder.poll() is None:
                        data = self.active_recorder.stdout.read(1024)
                        if data:
                            on_data(data)
                    on_end()
                
                asyncio.create_task(read_from_process())
                return True
            except Exception as e:
                print(f"[Voice] SoX recording failed: {e}")
        
        return False
    
    def stop_recording(self):
        """停止录音"""
        if self.native_recording_active and self.stream:
            self.native_recording_active = False
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        elif self.active_recorder:
            self.active_recorder.terminate()
            self.active_recorder = None
    
    async def speech_to_text(self, audio_data: bytes) -> Optional[str]:
        """语音转文本"""
        if not self.speech_recognition:
            return None
        
        try:
            r = self.speech_recognition.Recognizer()
            audio = self.speech_recognition.AudioData(
                audio_data,
                RECORDING_SAMPLE_RATE,
                2  # 2 bytes per sample
            )
            text = r.recognize_google(audio, language='zh-CN')
            return text
        except Exception as e:
            print(f"[Voice] Speech to text failed: {e}")
            return None
    
    async def text_to_speech(self, text: str):
        """文本转语音"""
        if not self.pyttsx3:
            return
        
        try:
            engine = self.pyttsx3.init()
            engine.setProperty('rate', 150)
            engine.setProperty('volume', 1.0)
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            print(f"[Voice] Text to speech failed: {e}")
    
    async def record_and_transcribe(self) -> Optional[str]:
        """录音并转录"""
        audio_data = bytearray()
        done = asyncio.Event()
        
        def on_data(data):
            audio_data.extend(data)
        
        def on_end():
            done.set()
        
        # 开始录音
        started = await self.start_recording(
            on_data,
            on_end,
            {'silence_detection': True}
        )
        
        if not started:
            return None
        
        # 等待录音完成
        await done.wait()
        
        # 停止录音
        self.stop_recording()
        
        # 转录
        return await self.speech_to_text(bytes(audio_data))


# ============================================================================# 便捷函数# ============================================================================

def create_voice_service() -> VoiceService:
    """创建语音服务"""
    return VoiceService()
