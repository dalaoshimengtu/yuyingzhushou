"""
语音识别模块
使用 FunASR 离线语音识别引擎（阿里达摩院、免费、本地运行、支持中文）
完全离线运行，中文识别精度高，自动处理数字和标点
"""

import os
import struct
import time
import sys
from contextlib import contextmanager
from typing import Optional
import pyaudio


@contextmanager
def _suppress_output():
    """临时抑制标准输出和标准错误（用于隐藏 tqdm 进度条和模型日志）"""
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    devnull = open(os.devnull, "w")
    sys.stdout = devnull
    sys.stderr = devnull
    try:
        yield
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        devnull.close()


class VoiceRecognizer:
    """FunASR 离线语音识别器"""

    TARGET_RATE = 16000  # FunASR 模型需要 16kHz 采样率

    def __init__(self, status_callback=None, model_path: Optional[str] = None):
        self._status_callback = status_callback
        # 禁用 tqdm 进度条输出
        # 禁用 tqdm 进度条输出
        os.environ["TQDM_DISABLE"] = "1"

        # 首次使用时自动下载模型到本地缓存
        print("正在加载 FunASR 语音识别模型...")
        print("首次使用会自动下载中文模型到本地缓存，请耐心等待...")

        # 抑制 modelscope 和 funasr 的日志输出
        os.environ["MODELSCOPE_DEBUG"] = "0"
        os.environ["MODELSCOPE_LOG_LEVEL"] = "ERROR"
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache")
        os.environ["MODELSCOPE_CACHE"] = cache_dir

        import logging
        # 抑制 tqdm 和 modelscope 的日志
        logging.getLogger("modelscope").setLevel(logging.ERROR)
        logging.getLogger("funasr").setLevel(logging.ERROR)
        logging.getLogger("urllib3").setLevel(logging.ERROR)

        from modelscope.pipelines import pipeline
        from modelscope.utils.constant import Tasks

        # 使用 Paraformer 中文离线模型
        self.pipeline = pipeline(
            task=Tasks.auto_speech_recognition,
            model="damo/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
            model_revision="v2.0.4",
        )
        self.microphone = None
        self._detect_device()
        print("模型加载完成。")

    def _detect_device(self) -> None:
        """检测并选择合适的麦克风设备"""
        self.pa = pyaudio.PyAudio()
        self.device_index = None
        self.device_rate = self.TARGET_RATE

        try:
            # 尝试获取默认输入设备
            default = self.pa.get_default_input_device_info()
            self.device_index = default["index"]
            self.device_name = default["name"]
            self.device_rate = int(default.get("defaultSampleRate", self.TARGET_RATE))
            print(f"使用默认麦克风: {self.device_name} (采样率: {self.device_rate}Hz)")
        except Exception as e:
            # 遍历所有设备查找输入设备
            print("未找到默认输入设备，尝试自动查找...")
            info = self.pa.get_host_api_info_by_index(0)
            num_devices = info.get("deviceCount")

            for i in range(num_devices):
                device_info = self.pa.get_device_info_by_host_api_device_index(0, i)
                if device_info.get("maxInputChannels", 0) > 0:
                    self.device_index = i
                    self.device_name = device_info.get("name")
                    self.device_rate = int(device_info.get("defaultSampleRate", self.TARGET_RATE))
                    print(f"找到麦克风: {self.device_name} (设备 {i}, 采样率: {self.device_rate}Hz)")
                    break

        if self.device_index is None:
            print("警告: 未找到任何麦克风设备！")
        self.pa.terminate()

    def _open_microphone(self) -> None:
        """打开麦克风"""
        if self.device_index is None:
            raise RuntimeError("未找到可用的麦克风设备")

        self.pa = pyaudio.PyAudio()
        self.microphone = self.pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.device_rate,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=4096,
        )
        self.microphone.start_stream()

    def _close_microphone(self) -> None:
        """关闭麦克风"""
        if self.microphone is not None:
            try:
                self.microphone.stop_stream()
                self.microphone.close()
            except Exception:
                pass
            self.microphone = None
        if hasattr(self, "pa"):
            try:
                self.pa.terminate()
            except Exception:
                pass

    def _resample_audio(self, audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
        """
        使用 scipy 进行高质量音频重采样
        将设备采样率的音频转换为目标采样率
        """
        if from_rate == to_rate:
            return audio_data

        try:
            import numpy as np
            from scipy.signal import resample

            samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
            num_samples = int(len(samples) * to_rate / from_rate)
            resampled = resample(samples, num_samples).astype(np.int16)
            return resampled.tobytes()
        except ImportError:
            # 如果没有 scipy，使用简单线性插值
            samples = list(struct.unpack("<" + "h" * (len(audio_data) // 2), audio_data))
            ratio = from_rate / to_rate
            new_length = int(len(samples) / ratio)
            resampled = []

            for i in range(new_length):
                idx = int(i * ratio)
                if idx < len(samples):
                    resampled.append(samples[idx])
                else:
                    resampled.append(0)

            return struct.pack("<" + "h" * len(resampled), *resampled)

    def _status(self, msg: str) -> None:
        """发送用户可见的状态消息"""
        print(msg)
        if self._status_callback:
            self._status_callback(msg)

    def _record_audio(self, timeout: float = 10.0) -> Optional[bytes]:
        """
        从麦克风录制音频
        返回: 录制的音频数据 (PCM 16-bit, 16kHz, mono)
        """
        self._open_microphone()

        try:
            self._status("请说话...")

            audio_data = bytearray()
            start_time = time.time()
            silence_start = time.time()
            silence_threshold = 1.5  # 静音 1.5 秒自动停止
            has_voice = False
            voice_start_time = 0.0
            silence_threshold_ms = silence_threshold * self.device_rate / 1000

            while True:
                data = self.microphone.read(4096, exception_on_overflow=False)
                audio_data.extend(data)

                # 检测音量
                samples = struct.unpack("<" + "h" * (len(data) // 2), data)
                avg_volume = sum(abs(s) for s in samples) / len(samples)

                current_time = time.time()

                # 检测是否有声音
                if avg_volume > 50:  # 音量阈值
                    if not has_voice:
                        has_voice = True
                        voice_start_time = current_time
                    silence_start = current_time  # 重置静音计时
                else:
                    if has_voice:
                        # 静音检测：如果已经检测到声音，然后又静音了
                        if current_time - silence_start > silence_threshold:
                            break

                # 超时检测
                if current_time - start_time > timeout:
                    if not has_voice:
                        print("未检测到有效语音。")
                        return None
                    else:
                        break

            if not audio_data:
                print("未录制到音频数据。")
                return None

            duration = current_time - start_time
            print(f"录音完成，时长: {duration:.1f}秒 (采样率: {self.device_rate}Hz)")

            # 如果设备采样率不是 16kHz，需要重采样
            if self.device_rate != self.TARGET_RATE:
                print(f"重采样: {self.device_rate}Hz -> {self.TARGET_RATE}Hz")
                audio_data = self._resample_audio(bytes(audio_data), self.device_rate, self.TARGET_RATE)
            
            # 调试信息
            print(f"最终音频数据大小: {len(audio_data)} 字节")
            import numpy as np
            test_samples = np.frombuffer(audio_data, dtype=np.int16)
            print(f"采样点数: {len(test_samples)}, 平均音量: {np.mean(np.abs(test_samples)):.1f}")

            return bytes(audio_data)

        except Exception as e:
            print(f"录音出错: {e}")
            return None
        finally:
            self._close_microphone()

    def listen(self, timeout: float = 10.0) -> Optional[str]:
        """
        从麦克风录制语音并识别为文本
        参数 timeout: 最大录音时长（秒）
        返回: 识别到的文本，如果识别失败则返回 None
        """
        # 录制音频
        audio_data = self._record_audio(timeout)
        if audio_data is None:
            return None

        # 使用 FunASR 识别
        try:
            import numpy as np
            import tempfile
            import wave

            # 将音频数据保存为临时 wav 文件
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_file:
                wav_path = wav_file.name

            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(self.TARGET_RATE)
                wf.writeframes(audio_data)

            self._status("正在识别语音...")

            # 使用 pipeline 识别 wav 文件（抑制进度条输出）
            with _suppress_output():
                result = self.pipeline(wav_path)

            # 清理临时文件
            try:
                import os
                os.remove(wav_path)
            except Exception:
                pass

            if result is None:
                print("识别结果为空。")
                return None

            # FunASR pipeline 返回格式可能是列表或字典
            text = ""
            if isinstance(result, list) and len(result) > 0:
                # 列表格式: [{'key': 'xxx', 'text': '画一个圆。', ...}]
                text = result[0].get("text", "").strip()
            elif isinstance(result, dict):
                # 字典格式: {'text': '画一个圆。', ...}
                text = result.get("text", "").strip()

            if text:
                self._status(f"识别结果: {text}")
                return text
            else:
                print(f"未识别到有效文本。完整结果: {result}")
                return None

        except Exception as e:
            print(f"语音识别出错: {e}")
            import traceback
            traceback.print_exc()
            return None
