# -*- coding: utf-8 -*-
"""
阶段1: 编剧智能体 (直出一遍过版本)
"""

import os
import re
import json
import asyncio
import logging
from functools import partial
from datetime import datetime, timezone
from typing import Any, Optional, Dict

from prompts.loader import load_prompt_with_fallback
from .base_agent import AgentInterface

logger = logging.getLogger(__name__)

def _get_script_prompt(name: str, lang: str = "zh") -> str:
    return load_prompt_with_fallback("script", name, lang, "zh")

class ScriptWriterAgent(AgentInterface):
    def __init__(self):
        super().__init__(name="ScriptWriter")

    @staticmethod
    def _extract_json_from_text(text: str) -> Optional[dict]:
        text = text.strip()
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        return None

    def _gen_id(self, prefix: str = "char") -> str:
        import uuid
        return f"{prefix}_{uuid.uuid4().hex[:6]}"

    def _save_result(self, json_data: dict, sid: str, is_zh: bool):
        from config import settings as app_settings
        os.makedirs(os.path.join(app_settings.RESULT_DIR, 'script'), exist_ok=True)
        out_path = os.path.join(app_settings.RESULT_DIR, 'script', f'{sid}.json')
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        logger.info(f"[ScriptWriter] script saved to {out_path}")

    def _save_progress(self, sid: str, phase: str, data: dict):
        pass

    async def process(self, input_data: Any, intervention: Optional[Dict] = None) -> Dict:
        if intervention and "modified_script" in intervention:
            modified = intervention["modified_script"]
            sid = input_data.get("session_id", "")
            if isinstance(modified, str):
                modified = self._extract_json_from_text(modified) or {}
            is_zh = any('\u4e00' <= c <= '\u9fff' for c in modified.get("title", ""))
            modified["session_id"] = sid
            self._save_result(modified, sid, is_zh)
            return {"payload": modified, "requires_intervention": False, "stage_completed": True}

        async def run_logic():
            idea = input_data.get("idea", "")
            sid = input_data.get("session_id", "")
            style = input_data.get("style", "anime")
            llm_model = input_data.get("llm_model", "qwen3.5-plus")
            web_search = input_data.get("web_search", False)
            is_zh = any('\u4e00' <= c <= '\u9fff' for c in idea)

            from config import settings as app_settings
            from tool.llm_client import LLM
            os.makedirs(app_settings.TEMP_DIR, exist_ok=True)
            llm = LLM()

            def _log_progress(pct, msg):
                self._report_progress("剧本生成", msg, pct)
                logger.info(f"[{pct}%] {msg}")

            # 1. Generate full script
            _log_progress(10, "正在生成完整剧本文本...")
            prompt_name = "generate_script"
            prompt = _get_script_prompt(prompt_name, "zh" if is_zh else "en").format(idea=idea, style=style)
            
            loop = asyncio.get_running_loop()
            full_script_text = await loop.run_in_executor(None, self._cancellable_query, llm, prompt, [], llm_model, True, sid, web_search)
            logger.info(f"[ScriptWriter] Full script generated ({len(full_script_text)} chars)")
            _log_progress(40, "原稿生成完成，正在提取元数据...")

            # 2. Extract meta data -> total_episodes, characters, settings
            meta_prompt = _get_script_prompt("meta_extract", "zh" if is_zh else "en").format(script_text=full_script_text, outline=full_script_text)
            meta_raw = await loop.run_in_executor(None, self._cancellable_query, llm, meta_prompt, [], llm_model, True, sid, web_search)
            meta_data = self._extract_json_from_text(meta_raw) or {}
            
            all_characters = meta_data.get("characters", [])
            all_settings = meta_data.get("settings", [])
            for c in all_characters:
                c["character_id"] = c.get("character_id") or self._gen_id("char")
            for s in all_settings:
                s["setting_id"] = s.get("setting_id") or self._gen_id("set")

            asset_chars_str = json.dumps([{"name": c.get("name"), "description": c.get("description"), "role": c.get("role")} for c in all_characters], ensure_ascii=False)
            asset_sets_str = json.dumps([{"name": s.get("name"), "description": s.get("description")} for s in all_settings], ensure_ascii=False)

            _log_progress(50, "正在解析各集数据...")
            
            total_eps = meta_data.get("total_episodes", 4)
            if not isinstance(total_eps, int) or total_eps < 1:
                total_eps = 1
                
            async def extract_one_episode(ep_num):
                self._check_cancel()
                
                extract_prompt = _get_script_prompt("act_extract", "zh" if is_zh else "en").format(
                    act_number=ep_num, scene_start=1, script_text=full_script_text, outline=full_script_text,
                    asset_characters=asset_chars_str, asset_settings=asset_sets_str
                )
                
                # 并行调用 LLM（使用异步包装）
                loop = asyncio.get_running_loop()
                raw_act = await loop.run_in_executor(None, self._cancellable_query, llm, extract_prompt, [], llm_model, True, sid, web_search)
                parsed_act = self._extract_json_from_text(raw_act) or {}

                return ep_num, {
                    "episode_number": ep_num,
                    "act_title": parsed_act.get("episode_title") or parsed_act.get("act_title") or f"第{ep_num}集",
                    "content": parsed_act.get("episode_content") or parsed_act.get("content", "")
                }

            # 创建并发任务
            tasks = [extract_one_episode(i) for i in range(1, total_eps + 1)]
            results = await asyncio.gather(*tasks)

            # 保持原始顺序
            results.sort(key=lambda x: x[0])
            all_episodes = [r[1] for r in results]

            final_json = {
                "project_id": f"proj_{sid}",
                "session_id": sid,
                "version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "generation_model": llm_model,
                    "generation_prompt": idea,
                    "original_text": full_script_text
                },
                "title": meta_data.get("title", "Generated Script"),
                "logline": meta_data.get("logline", ""),
                "genre": meta_data.get("genre", []),
                "mood": meta_data.get("mood", ""),
                "characters": all_characters,
                "settings": all_settings,
                "episodes": all_episodes
            }
            
            self._save_result(final_json, sid, is_zh)
            _log_progress(100, "剧本结构化解析完成！")
            return final_json

        result = await run_logic()
        return {"payload": result, "requires_intervention": False, "stage_completed": True}
