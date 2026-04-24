'use client';

import React, { useState, useRef } from 'react';
import { Sparkles, Play, Settings2, Clock, ArrowRight, Zap, CheckCircle, Trash2, X, Lock, Globe, ListOrdered, Upload, Loader2 } from 'lucide-react';
import clsx from 'clsx';
import { PROMPT_EXAMPLES } from '@/config/examples';
import { LLM_MODELS, T2I_MODELS, I2I_MODELS, VIDEO_MODELS, VLM_MODELS, STYLES, VIDEO_RATIOS, LLM_PROVIDERS, T2I_PROVIDERS, I2I_PROVIDERS, VIDEO_PROVIDERS, VLM_PROVIDERS, ProviderGroup } from '@/config/models';
import { STAGES } from './TopBar';

export interface ProjectParams {
  idea: string;
  file_path?: string; // 上传的文件路径 (由后端返回的文件名)
  style: string;
  video_ratio: string;
  llm_model: string;
  vlm_model: string;
  image_t2i_model: string;
  image_it2i_model: string;
  video_model: string;
  expand_idea?: boolean;
  enable_concurrency?: boolean;
  web_search?: boolean;
  episodes?: number;
}

interface HistoryItem {
  id: string;
  idea: string;
  style?: string;
  date: string;
  status: string;
  stages?: Record<string, string>;
}

interface HomePageProps {
  onStartProject: (params: ProjectParams, autoMode?: boolean) => void;
  onResumeProject: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => Promise<void>;
  history: HistoryItem[];
}

/* 根据 status 映射生成进度文本 */
function stageProgressLabel(statusMap?: Record<string, string>): { text: string; color: string } {
  const map = statusMap || {};
  const completed = Object.keys(map).filter(k => ["completed", "session_completed"].includes(map[k]));
  if (completed.length === 0) return { text: '未开始', color: 'text-gray-400' };
  if (completed.length >= STAGES.length) return { text: '已完成', color: 'text-green-600' };
  
  // 对比 STAGES 获取最后一个已完成的
  const lastStageId = STAGES.filter(s => completed.includes(s.id)).pop()?.id || completed[completed.length - 1];
  const stageDef = STAGES.find(s => s.id === lastStageId);
  const name = stageDef?.shortName || lastStageId;
  return { text: `已完成: ${name} (${completed.length}/${STAGES.length})`, color: 'text-blue-600' };
}

export default function HomePage({ onStartProject, onResumeProject, onDeleteSession, history }: HomePageProps) {
  const [idea, setIdea] = useState('');
  const [showSettings, setShowSettings] = useState(false);
  const [selectedStyle, setSelectedStyle] = useState('realistic');
  const [selectedLLM, setSelectedLLM] = useState(LLM_MODELS.find(m => m.default)?.id || LLM_MODELS[0].id);
  const [selectedVLM, setSelectedVLM] = useState(VLM_MODELS.find(m => m.default)?.id || VLM_MODELS[0].id);
  const [selectedT2I, setSelectedT2I] = useState(T2I_MODELS.find(m => m.default)?.id || T2I_MODELS[0].id);
  const [selectedI2I, setSelectedI2I] = useState(I2I_MODELS.find(m => m.default)?.id || I2I_MODELS[0].id);
  const [selectedVideo, setSelectedVideo] = useState(VIDEO_MODELS.find(m => m.default)?.id || VIDEO_MODELS[0].id);
  const [selectedRatio, setSelectedRatio] = useState('16:9');
  const [enableConcurrency, setEnableConcurrency] = useState(true);
  const [webSearch, setWebSearch] = useState(false);
  const [episodes, setEpisodes] = useState(4);
  const [showEpisodesPanel, setShowEpisodesPanel] = useState(false);

  // 上传相关状态
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<{name: string, path: string} | null>(null);

  // 管理模式状态
  const [manageMode, setManageMode] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState('');
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError('');
    try {
      await onDeleteSession(deleteTarget);
      setDeleteTarget(null);
    } catch (e: any) {
      setDeleteError(e.message || '删除失败');
    } finally {
      setDeleting(false);
    }
  };

  const handleStart = (auto?: boolean) => {
    if (!idea.trim() && !uploadedFile) return;
    onStartProject({
      idea,
      file_path: uploadedFile?.path, // 如果上传了文件，传给后端
      style: selectedStyle,
      video_ratio: selectedRatio,
      llm_model: selectedLLM,
      vlm_model: selectedVLM,
      image_t2i_model: selectedT2I,
      image_it2i_model: selectedI2I,
      video_model: selectedVideo,
      enable_concurrency: enableConcurrency,
      web_search: webSearch,
      episodes,
    }, auto);
  };

  const handleExampleClick = (text: string) => {
    setIdea(text);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const allowedExtensions = ['.doc', '.docx', '.txt', '.md', '.pdf'];
    const extension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    
    if (!allowedExtensions.includes(extension)) {
      alert(`仅支持 ${allowedExtensions.join(', ')} 格式的文件`);
      return;
    }

    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'}/api/upload_file`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error('文件上传失败');
      }

      const data = await response.json();
      if (data.file_path) {
        // 记录已上传的文件信息，不修改输入框
        setUploadedFile({
          name: file.name,
          path: data.file_path
        });
      }
    } catch (error) {
      console.error('上传错误:', error);
      alert('上传提取内容失败，请重试');
    } finally {
      setUploading(false);
      // 清空 input 方便下次选择同一文件
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  return (
    <div className="h-full flex flex-col items-center overflow-y-auto bg-gray-50/50">
      {/* 主区域 - 居中 */}
      <div className="w-full max-w-6xl px-6 pt-16 pb-8 flex-shrink-0">
        {/* 标题 */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 mb-3">
            <Sparkles className="w-7 h-7 text-blue-500" />
            <h1 className="text-2xl font-bold text-gray-800">AIGC-Claw</h1>
          </div>
          <p className="text-sm text-gray-500">
            输入你的创意，AI 将为你分步生成完整短片
          </p>
        </div>

        {/* 输入区域 */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-5 mb-6">
          <textarea
            value={idea}
            onChange={e => setIdea(e.target.value)}
            placeholder="描述你的视频创意... 例如：一只叫Luna的猫意外进入太空站，遇到一个孤独的宇航员"
            className="w-full bg-transparent text-sm text-gray-800 placeholder-gray-400 resize-none outline-none min-h-[100px]"
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey && (idea.trim() || uploadedFile)) {
                e.preventDefault();
                handleStart(false);
              }
            }}
          />

          <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100">
            <div className="flex items-center gap-3">
              <div className="relative">
                <button
                  onClick={() => setShowEpisodesPanel(!showEpisodesPanel)}
                  className={clsx(
                    'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                    showEpisodesPanel
                      ? 'bg-blue-50 text-blue-600'
                      : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50'
                  )}
                >
                  <ListOrdered className="w-3.5 h-3.5" />
                  剧集: {episodes}集
                </button>

                {showEpisodesPanel && (
                  <>
                    <div 
                      className="fixed inset-0 z-10" 
                      onClick={() => setShowEpisodesPanel(false)}
                    />
                    <div className="absolute bottom-full left-0 mb-2 w-48 bg-white rounded-xl shadow-xl border border-gray-100 p-4 z-20 animate-in fade-in slide-in-from-bottom-2">
                      <div className="flex flex-col gap-3">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-gray-700">设置总集数</span>
                          <span className="text-[10px] text-blue-500 font-bold bg-blue-50 px-1.5 py-0.5 rounded-full">
                            {episodes} 集
                          </span>
                        </div>
                        
                        <div className="flex items-center gap-2">
                          <button 
                            onClick={(e) => { e.stopPropagation(); setEpisodes(Math.max(1, episodes - 1)); }}
                            className="w-7 h-7 flex items-center justify-center rounded-lg bg-gray-50 text-gray-600 hover:bg-gray-100 active:scale-95 transition-all text-sm font-bold"
                          >
                            -
                          </button>
                          <input
                            type="range"
                            min={1}
                            max={10}
                            value={episodes}
                            onChange={(e) => setEpisodes(parseInt(e.target.value))}
                            className="flex-1 h-1.5 bg-gray-100 rounded-lg appearance-none cursor-pointer accent-blue-500"
                          />
                          <button 
                            onClick={(e) => { e.stopPropagation(); setEpisodes(Math.min(10, episodes + 1)); }}
                            className="w-7 h-7 flex items-center justify-center rounded-lg bg-gray-50 text-gray-600 hover:bg-gray-100 active:scale-95 transition-all text-sm font-bold"
                          >
                            +
                          </button>
                        </div>

                        <div className="space-y-1 border-t border-gray-50 pt-2">
                          <p className="text-[10px] text-gray-400 leading-tight">
                            • 每集预估时长约 1-2 分钟
                          </p>
                          <p className="text-[10px] text-blue-400/80 leading-tight">
                            • 推荐设置 4-6 集
                          </p>
                        </div>
                      </div>
                    </div>
                  </>
                )}
              </div>

              <button
                onClick={() => setShowSettings(!showSettings)}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                  showSettings
                    ? 'bg-blue-50 text-blue-600'
                    : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50'
                )}
              >
                <Settings2 className="w-3.5 h-3.5" />
                生成配置
              </button>
              <button
                onClick={() => setWebSearch(!webSearch)}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                  webSearch
                    ? 'bg-blue-50 text-blue-600'
                    : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50'
                )}
              >
                <Globe className="w-3.5 h-3.5" />
                联网搜索
              </button>
            </div>
            <div className="flex items-center gap-2">
              {/* 隐藏的文件输入框 */}
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileUpload}
                accept=".doc,.docx,.txt,.md,.pdf"
                className="hidden"
              />
              <button
                onClick={() => {
                  if (uploadedFile) {
                    setUploadedFile(null); // 已有文件则点击取消
                  } else {
                    fileInputRef.current?.click();
                  }
                }}
                disabled={uploading}
                className={clsx(
                  'flex items-center gap-2 px-5 py-2 rounded-xl text-sm font-medium transition-colors border shadow-sm relative',
                  uploading
                    ? 'bg-gray-50 text-gray-400 cursor-not-allowed border-gray-100'
                    : uploadedFile
                    ? 'bg-blue-50 text-blue-600 border-blue-100 hover:bg-blue-100'
                    : 'bg-white text-gray-600 hover:bg-gray-50 border-gray-200'
                )}
                title={uploadedFile ? `已选择: ${uploadedFile.name} (点击取消)` : "上传文档 (Word/TXT/MD)"}
              >
                {uploading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : uploadedFile ? (
                  <CheckCircle className="w-4 h-4" />
                ) : (
                  <Upload className="w-4 h-4" />
                )}
                {uploading ? '上传中...' : uploadedFile ? `已选: ${uploadedFile.name.length > 8 ? uploadedFile.name.substring(0, 8) + '...' : uploadedFile.name}` : '上传文件'}
                {uploadedFile && (
                  <div className="absolute -top-1 -right-1 bg-red-500 text-white rounded-full p-0.5">
                    <X className="w-2.5 h-2.5" />
                  </div>
                )}
              </button>
              <button
                onClick={() => handleStart(false)}
                disabled={!idea.trim() && !uploadedFile}
                className={clsx(
                  'flex items-center gap-2 px-5 py-2 rounded-xl text-sm font-medium transition-colors',
                  (idea.trim() || uploadedFile)
                    ? 'bg-blue-500 text-white hover:bg-blue-600 shadow-sm'
                    : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                )}
              >
                <Play className="w-4 h-4" />
                逐步创作
              </button>
              <button
                onClick={() => handleStart(true)}
                disabled={!idea.trim() && !uploadedFile}
                className={clsx(
                  'flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors',
                  (idea.trim() || uploadedFile)
                    ? 'bg-amber-500 text-white hover:bg-amber-600 shadow-sm'
                    : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                )}
                title="自动执行全部六个阶段，无需手动确认"
              >
                <Zap className="w-4 h-4" />
                一键生成
              </button>
            </div>
          </div>

          {/* 模型设置折叠面板 */}
          {showSettings && (
            <div className="mt-4 p-4 bg-gray-50 rounded-xl space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <label className="flex flex-col gap-1">
                  <span className="text-gray-500 font-medium">风格</span>
                  <select
                    value={selectedStyle}
                    onChange={e => setSelectedStyle(e.target.value)}
                    className="bg-white border border-gray-200 rounded-lg px-2.5 py-2 text-gray-700 outline-none"
                  >
                    {STYLES.map(s => (
                      <option key={s.id} value={s.id}>{s.label}</option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-gray-500 font-medium">视频比例</span>
                  <div className="flex gap-1">
                    {VIDEO_RATIOS.map(r => (
                      <button
                        key={r.id}
                        onClick={() => setSelectedRatio(r.id)}
                        className={`flex flex-col items-center gap-1 p-2 rounded-lg border transition-all ${
                          selectedRatio === r.id
                            ? 'border-indigo-500 bg-indigo-50'
                            : 'border-gray-200 hover:border-gray-300'
                        }`}
                        title={r.label}
                      >
                        <div
                          className="bg-gray-700 rounded-sm"
                          style={{
                            width: r.ratio === '16:9' ? '32px' :
                                   r.ratio === '9:16' ? '18px' :
                                   r.ratio === '1:1' ? '24px' :
                                   r.ratio === '4:3' ? '28px' :
                                   r.ratio === '3:4' ? '20px' :
                                   '36px',
                            height: r.ratio === '16:9' ? '18px' :
                                   r.ratio === '9:16' ? '32px' :
                                   r.ratio === '1:1' ? '24px' :
                                   r.ratio === '4:3' ? '21px' :
                                   r.ratio === '3:4' ? '28px' :
                                   '15px',
                          }}
                        />
                        <span className="text-[10px] text-gray-500">{r.label}</span>
                      </button>
                    ))}
                  </div>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-gray-500 font-medium">LLM 模型</span>
                  <select
                    value={selectedLLM}
                    onChange={e => setSelectedLLM(e.target.value)}
                    className="bg-white border border-gray-200 rounded-lg px-2.5 py-2 text-gray-700 outline-none"
                  >
                    {LLM_PROVIDERS.map(pg => (
                      <optgroup key={pg.provider} label={pg.label}>
                        {pg.models.map(m => (
                          <option key={m.id} value={m.id}>{m.label}</option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-gray-500 font-medium">VLM 评估模型</span>
                  <select
                    value={selectedVLM}
                    onChange={e => setSelectedVLM(e.target.value)}
                    className="bg-white border border-gray-200 rounded-lg px-2.5 py-2 text-gray-700 outline-none"
                  >
                    {VLM_PROVIDERS.map(pg => (
                      <optgroup key={pg.provider} label={pg.label}>
                        {pg.models.map(m => (
                          <option key={m.id} value={m.id}>{m.label}</option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-gray-500 font-medium">文生图</span>
                  <select
                    value={selectedT2I}
                    onChange={e => setSelectedT2I(e.target.value)}
                    className="bg-white border border-gray-200 rounded-lg px-2.5 py-2 text-gray-700 outline-none"
                  >
                    {T2I_PROVIDERS.map(pg => (
                      <optgroup key={pg.provider} label={pg.label}>
                        {pg.models.map(m => (
                          <option key={m.id} value={m.id}>{m.label}</option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-gray-500 font-medium">图生图</span>
                  <select
                    value={selectedI2I}
                    onChange={e => setSelectedI2I(e.target.value)}
                    className="bg-white border border-gray-200 rounded-lg px-2.5 py-2 text-gray-700 outline-none"
                  >
                    {I2I_PROVIDERS.map(pg => (
                      <optgroup key={pg.provider} label={pg.label}>
                        {pg.models.map(m => (
                          <option key={m.id} value={m.id}>{m.label}</option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 col-span-2">
                  <span className="text-gray-500 font-medium">视频模型</span>
                  <select
                    value={selectedVideo}
                    onChange={e => setSelectedVideo(e.target.value)}
                    className="bg-white border border-gray-200 rounded-lg px-2.5 py-2 text-gray-700 outline-none"
                  >
                    {VIDEO_PROVIDERS.map(pg => (
                      <optgroup key={pg.provider} label={pg.label}>
                        {pg.models.map(m => (
                          <option key={m.id} value={m.id}>{m.label}</option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </label>
                <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={enableConcurrency}
                    onChange={e => setEnableConcurrency(e.target.checked)}
                    className="w-4 h-4 rounded border-gray-300 text-blue-500 focus:ring-blue-500/30"
                  />
                  <span className="text-gray-600">并发生成</span>
                </label>
              </div>
            </div>
          )}
        </div>

        {/* 示例卡片 */}
        <div className="mb-10">
          <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-3">
            灵感示例
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2.5">
            {PROMPT_EXAMPLES.map((ex, idx) => (
              <button
                key={idx}
                onClick={() => handleExampleClick(ex.text)}
                className="text-left p-3.5 bg-white rounded-xl border border-gray-200 hover:border-blue-300 hover:shadow-sm transition-all group"
              >
                <div className="text-sm font-medium text-gray-700 group-hover:text-blue-600 transition-colors mb-1">
                  {ex.title}
                </div>
                <div className="text-xs text-gray-400 line-clamp-2">
                  {ex.description}
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 历史记录区域 */}
      {history.length > 0 && (
        <div className="w-full max-w-6xl px-6 pb-12 flex-shrink-0">
          <div className="flex items-center gap-2 mb-4">
            <Clock className="w-4 h-4 text-gray-400" />
            <h3 className="text-sm font-medium text-gray-600">历史记录</h3>
            <button
              onClick={() => setManageMode(m => !m)}
              className={`ml-auto text-xs px-2 py-0.5 rounded transition-colors ${
                manageMode ? 'bg-red-100 text-red-600' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
              }`}
            >
              {manageMode ? '完成' : '管理'}
            </button>
          </div>
          <div className="max-h-[60vh] overflow-y-auto pr-1">
            <div className="grid grid-cols-2 gap-3">
              {history.map(item => {
                const progress = stageProgressLabel(item.stages);
                return (
                <div key={item.id} className="relative group">
                  <div
                    onClick={() => !manageMode && onResumeProject(item.id)}
                    className={`w-full text-left p-4 bg-white rounded-xl border border-gray-200 hover:border-blue-300 hover:shadow-sm transition-all ${!manageMode ? 'cursor-pointer' : ''}`}
                  >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-700 group-hover:text-blue-600 transition-colors truncate">
                        {item.idea}
                      </div>
                      <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                        {item.style && (
                          <span className="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
                            {item.style}
                          </span>
                        )}
                        <span className="text-[10px] text-gray-400">{item.date}</span>
                      </div>
                      <div className={`flex items-center gap-1 mt-1.5 text-[10px] font-medium ${progress.color}`}>
                        {item.stages && Object.keys(item.stages).filter(k => ["completed", "session_completed"].includes(item.stages![k])).length >= STAGES.length ? (
                          <CheckCircle className="w-3 h-3" />
                        ) : (
                          <span className="w-1.5 h-1.5 rounded-full bg-current flex-shrink-0" />
                        )}
                        <span>{progress.text}</span>
                      </div>
                    </div>
                    {manageMode ? (
                      <button
                        onClick={(e) => { e.stopPropagation(); setDeleteTarget(item.id); setDeleteError(''); }}
                        className="w-6 h-6 rounded-full bg-red-500 text-white flex items-center justify-center hover:bg-red-600 transition-colors flex-shrink-0 mt-0.5"
                        title="删除"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    ) : (
                      <ArrowRight className="w-4 h-4 text-gray-300 group-hover:text-blue-400 transition-colors flex-shrink-0 mt-0.5" />
                    )}
                  </div>
                </div>
                </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* 删除确认弹窗 */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-2xl shadow-xl w-80 p-6 relative">
            <button
              onClick={() => { setDeleteTarget(null); setDeleteError(''); }}
              className="absolute top-3 right-3 text-gray-400 hover:text-gray-600"
            >
              <X className="w-4 h-4" />
            </button>
            <div className="flex items-center gap-2 mb-4">
              <Trash2 className="w-4 h-4 text-red-500" />
              <h4 className="text-sm font-semibold text-gray-700">确认删除</h4>
            </div>
            <p className="text-xs text-gray-500 mb-6">删除后不可恢复，确定要删除此项目吗？</p>
            {deleteError && <p className="text-xs text-red-500 mb-2">{deleteError}</p>}
            <div className="flex gap-2">
              <button
                onClick={() => { setDeleteTarget(null); setDeleteError(''); }}
                className="flex-1 text-sm py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50"
              >
                取消
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="flex-1 text-sm py-1.5 rounded-lg bg-red-500 text-white hover:bg-red-600 disabled:opacity-50"
              >
                {deleting ? '删除中…' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
