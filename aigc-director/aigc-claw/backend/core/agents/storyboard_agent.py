# -*- coding: utf-8 -*-
"""
阶段3: 分镜智能体
基于剧本JSON，逐场景拆分为带时长标签的分镜（shots），按幕分组输出。
支持 Segment -> Shots 嵌套结构。
"""

import os
import re
import json
import asyncio
import logging
from datetime import datetime
from typing import Any, Optional, Dict, List

from .base_agent import AgentInterface

logger = logging.getLogger(__name__)

# ─── 幕名 ───
ACT_NAMES = {1: "激励事件", 2: "进入新世界", 3: "灵魂黑夜", 4: "高潮决战"}

def _get_shot_prompt(lang: str = "zh") -> str:
    from prompts.loader import load_prompt_with_fallback
    return load_prompt_with_fallback("storyboard", "shot", lang, "zh")

def _get_continue_prompt(lang: str = "zh") -> str:
    from prompts.loader import load_prompt_with_fallback
    return load_prompt_with_fallback("storyboard", "continue", lang, "zh")

class StoryboardAgent(AgentInterface):
    def __init__(self):
        super().__init__(name="Storyboard")

    @staticmethod
    def _read_script_json(sid: str) -> dict:
        session_path = os.path.join("code/data/sessions", f"{sid}.json")
        if not os.path.exists(session_path):
            return {}
        try:
            with open(session_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("artifacts", {}).get("script_generation", {})
        except Exception:
            return {}

    @staticmethod
    def _extract_json_array(text: str) -> Optional[List[dict]]:
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        try:
            result = json.loads(text)
            if isinstance(result, list): return result
        except json.JSONDecodeError: pass
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            try:
                result = json.loads(m.group())
                if isinstance(result, list): return result
            except json.JSONDecodeError: pass
        return None

    @staticmethod
    def _validate_episodes(episodes: List[dict]) -> List[dict]:
        """验证嵌套的 Episode -> Segment -> Shots 结构"""
        valid_episodes = []
        for ep in episodes:
            if not isinstance(ep, dict): continue
            
            segments = ep.get("segments", [])
            valid_segments = []
            
            for seg in segments:
                if not isinstance(seg, dict): continue
                
                shots = seg.get("shots", [])
                valid_shots = []
                calc_total_duration = 0
                
                for s in shots:
                    if not isinstance(s, dict): continue
                    dur = s.get("duration", 5)
                    calc_total_duration += dur
                    valid_shots.append({
                        "shot_number": s.get("shot_number", len(valid_shots) + 1),
                        "shot_type": s.get("shot_type", "中景"),
                        "duration": dur,
                        "content": s.get("content", "")
                    })
                
                valid_segments.append({
                    "segment_id": seg.get("segment_id", str(uuid.uuid4())[:8]),
                    "segment_number": seg.get("segment_number", len(valid_segments) + 1),
                    "total_duration": seg.get("total_duration", calc_total_duration),
                    "location": seg.get("location", ""),
                    "characters": seg.get("characters", []),
                    "shots": valid_shots
                })
            
            valid_episodes.append({
                "episode_number": ep.get("episode_number", len(valid_episodes) + 1),
                "episode_title": ep.get("episode_title", ""),
                "segments": valid_segments
            })
        return valid_episodes

    async def _continue_story(self, input_data: Dict, continue_info: Dict) -> Dict:
        # TODO: 适配 Segment 结构的续写逻辑（暂留原始逻辑或抛错）
        raise NotImplementedError("续写逻辑尚不支持新的嵌套 Segment 结构，请先完成基础生成。")

    async def process(self, input_data: Any, intervention: Optional[Dict] = None) -> Dict:
        from tool.llm_client import LLM
        input_data = self._merge_session_params(input_data)
        sid = input_data.get("session_id")
        if not sid: raise Exception("Missing session_id")
             
        session_file = os.path.join("code/data/sessions", f"{sid}.json")
        with open(session_file, "r", encoding="utf-8") as f:
            session_data = json.load(f)
            
        llm_model = input_data.get("llm_model") or session_data.get("llm_model") or "qwen-max"
        style = input_data.get("style") or session_data.get("style") or "anime"
        
        # 处理人工干预/修改
        if intervention and "modified_storyboard" in intervention:
            modified_episodes = intervention["modified_storyboard"]
            if isinstance(modified_episodes, str): modified_episodes = json.loads(modified_episodes)
            session_data.setdefault("artifacts", {})["storyboard"] = {
                "session_id": sid,
                "episodes": modified_episodes,
                "user_modified": True,
                "updated_at": datetime.now().isoformat()
            }
            # 更新顶层状态
            session_data["updated_at"] = datetime.now().timestamp()
            with open(session_file, "w", encoding="utf-8") as f: json.dump(session_data, f, indent=2, ensure_ascii=False)
            return {"payload": {"session_id": sid, "episodes": modified_episodes}, "stage_completed": True}
        
        script_data = self._read_script_json(sid)
        if not script_data: raise Exception("未找到剧本数据")
        
        episodes = script_data.get("episodes", [])
        if not episodes:
            raise Exception("剧本数据中不包含有效集数列表(episodes)")
            
        chars = script_data.get("characters", [])
        sets = script_data.get("settings", [])
        is_zh = any("\u4e00" <= c <= "\u9fff" for c in script_data.get("title", ""))
        shot_prompt_tpl = _get_shot_prompt("zh" if is_zh else "en")
        
        self._report_progress("分镜", "解析剧本并生成片段...", 5)
        
        async def proc_ep(ep):
            ep_n = ep.get("episode_number", 1)
            ep_t = ep.get("act_title", f"第{ep_n}集")
            ep_c = ep.get("content", "")
            
            # 清洗剧本内容：按行拆分，用于提示说明“一行一分镜”
            lines = [line.strip() for line in ep_c.split('\n') if line.strip()]
            script_text_with_lines = "\n".join([f"L{idx+1}: {line}" for idx, line in enumerate(lines)])

            prompt = shot_prompt_tpl.format(
                act_number=ep_n, 
                act_title=ep_t, 
                script_text=script_text_with_lines, 
                asset_characters=json.dumps(chars, ensure_ascii=False), 
                asset_settings=json.dumps(sets, ensure_ascii=False),
                style=style
            )
            
            llm = LLM()
            loop = asyncio.get_running_loop()
            
            # 增加重试机制 (Max 3 retries)
            max_retries = 3
            extracted = None
            raw = ""
            
            for attempt in range(max_retries):
                try:
                    self._report_progress("分镜", f"生成集数 {ep_n} (第 {attempt + 1} 次尝试)...", 5 + attempt * 2)
                    raw = await loop.run_in_executor(None, self._cancellable_query, llm, prompt, [], llm_model, False, sid, False)
                    extracted = self._extract_json_array(raw)
                    if extracted:
                        break
                    logger.warning(f"Episode {ep_n} Attempt {attempt + 1}: Failed to extract JSON array. Retrying...")
                except Exception as e:
                    logger.error(f"Episode {ep_n} Attempt {attempt + 1}: LLM query error: {str(e)}")
                    if attempt == max_retries - 1: raise e
            
            if not extracted:
                logger.error(f"LLM output failed to parse as JSON for Episode {ep_n} after {max_retries} attempts. Raw: {raw}")
                return {
                    "episode_number": ep_n,
                    "episode_title": ep_t,
                    "segments": []
                }
                
            # 兼容旧的 _validate_segments 调用（已改名为 _validate_episodes 内部的逻辑）
            # 我们直接手动处理 segments
            valid_segments = []
            for i, seg in enumerate(extracted, 1):
                if not isinstance(seg, dict): continue
                shots = seg.get("shots", [])
                valid_shots = []
                calc_total_duration = 0
                for s in shots:
                    if not isinstance(s, dict): continue
                    dur = s.get("duration", 5)
                    calc_total_duration += dur
                    valid_shots.append({
                        "shot_number": s.get("shot_number", len(valid_shots) + 1),
                        "shot_type": s.get("shot_type", "中景"),
                        "duration": dur,
                        "content": s.get("content", "")
                    })
                valid_segments.append({
                    "segment_id": f"seg_{ep_n:02d}_{i:02d}",
                    "segment_number": i,
                    "location": seg.get("location", ""),
                    "characters": seg.get("characters", []),
                    "total_duration": seg.get("total_duration", calc_total_duration),
                    "shots": valid_shots,
                    "episode_number": ep_n
                })

            return {
                "episode_number": ep_n,
                "episode_title": ep_t,
                "segments": valid_segments
            }

        # 并发处理
        all_episodes = await asyncio.gather(*(proc_ep(ep) for ep in episodes))
        all_episodes.sort(key=lambda x: x["episode_number"])
        
# 核心：将结果持久化到 artifacts.storyboard
        # 现在存储的是嵌套的 episodes 结构
        session_data.setdefault("artifacts", {})["storyboard"] = {
            "session_id": sid, 
            "episodes": all_episodes, 
            "created_at": datetime.now().isoformat()
        }
        
        # 更新会话状态
        if "storyboard" not in session_data.get("stages_completed", []):
            session_data.setdefault("stages_completed", []).append("storyboard")
        session_data["status"] = "stage_completed"
        session_data["updated_at"] = datetime.now().timestamp()

        with open(session_file, "w", encoding="utf-8") as f: 
            json.dump(session_data, f, indent=2, ensure_ascii=False)
            
        self._report_progress("分镜", "完成", 100)
        return {"payload": {"session_id": sid, "episodes": all_episodes}, "stage_completed": True}
