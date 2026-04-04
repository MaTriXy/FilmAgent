# -*- coding: utf-8 -*-
"""
阶段6: 后期制作智能体
拼接用户在阶段5选定的视频片段 → 最终成片
"""

import os
import re
import json
import asyncio
import logging
import subprocess
from typing import Any, Optional, Dict

from .base_agent import AgentInterface

logger = logging.getLogger(__name__)


class VideoEditorAgent(AgentInterface):
    """后期制作：拼接用户选择的视频片段 → 最终成片"""

    def __init__(self):
        super().__init__(name="VideoEditor")

    async def process(self, input_data: Any, intervention: Optional[Dict] = None) -> Dict:
        sid = input_data["session_id"]
        
        # 优先从 session.json 的 artifacts 中读取阶段5的数据
        session_path = os.path.join('code/data/sessions', f'{sid}.json')
        if not os.path.exists(session_path):
            raise Exception(f"Session file not found: {session_path}")
            
        with open(session_path, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
            
        artifacts = session_data.get("artifacts", {})
        video_art = artifacts.get("video_generation", {})
        clips_list = video_art.get("clips", [])
        
        if not clips_list:
            # 兼容旧逻辑：如果 artifacts 里没有，尝试从 input_data 获取
            selected_clips: dict = input_data.get("selected_clips", {})
            if not selected_clips:
                raise Exception("未找到选定的视频片段数据，请先完成阶段5")
        
        self._report_progress("后期制作", "准备视频片段...", 5)

        def run():
            video_dir = os.path.join('code/result/video', str(sid))
            os.makedirs(video_dir, exist_ok=True)
            
            clip_paths = []
            
            # 如果是从新格式读取
            if clips_list:
                for clip in clips_list:
                    path = clip.get("selected")
                    if path and os.path.exists(path):
                        clip_paths.append(path)
                    else:
                        logger.warning(f"[{sid}] Clip missing: {clip.get('id')} → {path}")
            else:
                # 按旧逻辑从 selected_clips (dict) 读取
                def sort_key(k: str) -> tuple:
                    return tuple(int(n) for n in re.findall(r'\d+', k)) or (999,)
                selected_clips = input_data.get("selected_clips", {})
                for shot_id in sorted(selected_clips.keys(), key=sort_key):
                    path = selected_clips[shot_id]
                    if os.path.exists(path):
                        clip_paths.append(path)
                    else:
                        logger.warning(f"[{sid}] Clip missing: {shot_id} → {path}")

            if not clip_paths:
                raise Exception("没有可用于拼接的视频文件，请检查之前阶段是否生成成功并选中了版本")

            logger.info(f"[{sid}] Concat {len(clip_paths)} clips using fast stream copy")
            self._report_progress("后期制作", f"准备拼接 {len(clip_paths)} 个片段...", 15)

            # 导出成片
            output_dir = os.path.join(video_dir, 'output')
            os.makedirs(output_dir, exist_ok=True)
            output = os.path.join(output_dir, f'{sid}_final.mp4')
            
            # 使用列表文件进行 concat
            list_file = os.path.join(video_dir, 'concat_list.txt')
            with open(list_file, 'w', encoding='utf-8') as f:
                for p in clip_paths:
                    # 使用绝对路径并处理 Windows 路径转义
                    abs_p = os.path.abspath(p).replace('\\', '/')
                    f.write(f"file '{abs_p}'\n")

            try:
                self._report_progress("后期制作", "正在拼接视频 (FFmpeg)...", 50)
                
                ffmpeg_exe = 'ffmpeg'
                
                # 为了播放兼容性，我们进行轻量级的重新编码 (Fast Preset)
                # 这样可以处理不同片段间可能存在的微小元数据差异，确保播放时长正常
                cmd = [
                    ffmpeg_exe, '-f', 'concat', '-safe', '0',
                    '-i', list_file, 
                    '-c:v', 'libx264',    # 重新编码视频以保证兼容性
                    '-preset', 'fast',    # 快速平衡速度与质量
                    '-crf', '22',         # 保持高质量
                    '-c:a', 'aac',        # 确保有标准的音频流
                    '-pix_fmt', 'yuv420p', # 确保在所有播放器上都能播放
                    '-movflags', '+faststart',
                    '-y', output
                ]
                
                logger.info(f"[{sid}] Running ffmpeg concat/re-encode: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                logger.info(f"[{sid}] FFmpeg concat success: {output}")
                
            except Exception as e:
                logger.error(f"Fast concat failed: {str(e)}")
                # 如果是权限或路径问题，最后尝试一次 moviepy (虽然慢但兼容性好)
                raise Exception(f"视频快速拼接失败: {str(e)}")
                
            return output

        loop = asyncio.get_running_loop()
        final_path = await loop.run_in_executor(None, run)

        self._report_progress("后期制作", "成片完成", 100)

        # 同样将最终结果写入 artifacts
        session_data.setdefault("artifacts", {})["post_production"] = {
            "session_id": sid,
            "final_video": final_path
        }
        with open(session_path, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=4, ensure_ascii=False)

        return {
            "payload": {"session_id": sid, "final_video": final_path},
            "stage_completed": True,
        }